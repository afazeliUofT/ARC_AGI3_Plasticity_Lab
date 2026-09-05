"""Queue the next graded-set job (G3.6b step 18): the mechanised step of the run recipe.

Implements the "Order" and "One job per turn" sections of ``docs/G3_GRADED_SET_RECIPE.md``
for the G3b graded set. It reads every deciding parameter from the hash-locked G3b
pre-registration through ``scripts/verify_run.py``'s ``load_preregistration`` (the games
list, experiment id, graded config digest, job wall-clock limit, runner wall-clock limit, the
margin between them, the failed-rerun allowance and the earliest local start time), works out
the next game in the pre-registered order, and either refuses with a reason or writes the
supervisor job request ``state/job_request.json``.

The next game is the first game in order with no *completed* run under the graded artifacts
root (a run is completed when its ``results.json`` has ``completion_status == "completed"``).
Its attempt number is one plus the number of earlier runs for that game, and a second attempt
is only allowed under ``thresholds.failed_reruns_per_game_max``.

Refusals (exit 2, reason printed, nothing written):

* the machine's local time is before ``thresholds.earliest_start_local`` (both printed);
* the graded config file's sha256 differs from ``thresholds.graded_config_sha256``;
* the config's ``wallclock_limit_seconds`` plus the pre-registered margin exceeds
  ``thresholds.job_wallclock_limit_seconds`` (the runner must stop before the supervisor);
* ``state/job_request.json`` already exists (a request is pending);
* the newest ``state/jobs/<id>/request.json`` has no ``result.json`` yet (one in flight);
* a job directory for the id that would be written already exists;
* the game's rerun allowance is spent, or every game has a completed run (set complete).

Usage::

    uv run python scripts/g3_next_job.py [--dry-run]

``--dry-run`` prints the request it would write and writes nothing. No LLM, no thresholds
of its own, one side effect (the request file): a bookkeeping script per the constitution's
effort policy. It never starts a run; the supervisor does that between turns.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from verify_run import load_preregistration

GATE = "G3b"
JOB_ID_PREFIX = "g37"
RUNNER = "run_experiment"
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_parameters(root: Path = REPO_ROOT) -> dict[str, Any]:
    """Read every deciding parameter from the hash-locked G3b pre-registration."""
    prereg, path, digest = load_preregistration(GATE, root)
    thresholds = prereg["thresholds"]
    graded_set = prereg.get("graded_set") or {}
    experiment = prereg.get("graded_experiment") or {}
    games = [str(g) for g in (graded_set.get("games") or [])]
    required = int(thresholds["graded_games_required"])
    if len(games) != required:
        raise ValueError(
            f"{GATE}: graded_set.games lists {len(games)} games but "
            f"thresholds.graded_games_required is {required}"
        )
    if len(set(games)) != len(games):
        raise ValueError(f"{GATE}: graded_set.games repeats a game")
    return {
        "gate": GATE,
        "preregistration_path": str(path.relative_to(root)),
        "preregistration_sha256": digest,
        "experiment_id": str(thresholds["experiment_id"]),
        "config": str(experiment["config"]),
        "graded_config_sha256": str(thresholds["graded_config_sha256"]),
        "games": games,
        "job_wallclock_limit_seconds": int(thresholds["job_wallclock_limit_seconds"]),
        "wallclock_per_invocation_seconds": int(thresholds["wallclock_per_invocation_seconds"]),
        "job_margin_over_runner_limit_seconds_min": int(
            thresholds["job_margin_over_runner_limit_seconds_min"]
        ),
        "failed_reruns_per_game_max": int(thresholds["failed_reruns_per_game_max"]),
        "earliest_start_local": str(thresholds["earliest_start_local"]),
    }


@dataclass(frozen=True)
class RunInfo:
    """What the queue step needs to know about one run directory."""

    run_dir: str
    game: str | None
    completion_status: str | None
    source: str


def _game_of(results: dict[str, Any]) -> str | None:
    inner = results.get("results")
    if isinstance(inner, dict) and inner.get("stem"):
        return str(inner["stem"])
    if results.get("stem"):
        return str(results["stem"])
    return None


def discover_runs(artifacts_root: Path) -> list[RunInfo]:
    """Every run directory under the graded root, in id order.

    A run's game is read from ``results.json`` (``results.stem``); a directory without one
    (a run the supervisor killed writes neither manifest nor results) is attributed through
    ``resolved_config.yaml`` ``runner_params.game`` so that it still counts as an attempt.
    """
    if not artifacts_root.exists():
        return []
    runs: list[RunInfo] = []
    for run_dir in sorted(p for p in artifacts_root.iterdir() if p.is_dir()):
        results_path = run_dir / "results.json"
        if results_path.exists():
            results = json.loads(results_path.read_text(encoding="utf-8"))
            status = results.get("completion_status")
            runs.append(
                RunInfo(
                    run_dir=run_dir.name,
                    game=_game_of(results),
                    completion_status=str(status) if status is not None else None,
                    source="results.json",
                )
            )
            continue
        config_path = run_dir / "resolved_config.yaml"
        game: str | None = None
        if config_path.exists():
            resolved = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            params = resolved.get("runner_params") or {}
            if isinstance(params, dict) and params.get("game"):
                game = str(params["game"])
        runs.append(
            RunInfo(
                run_dir=run_dir.name,
                game=game,
                completion_status=None,
                source="resolved_config.yaml" if game else "unattributed",
            )
        )
    return runs


@dataclass(frozen=True)
class GameChoice:
    game: str | None
    attempt: int
    reason: str
    completed_games: list[str] = field(default_factory=list)


def choose_game(runs: list[RunInfo], games: list[str], reruns_max: int) -> GameChoice:
    """The first game in order without a completed run, and its attempt number."""
    completed = {r.game for r in runs if r.completion_status == "completed" and r.game}
    counts = {g: sum(1 for r in runs if r.game == g) for g in games}
    done = [g for g in games if g in completed]
    for game in games:
        if game in completed:
            continue
        attempt = 1 + counts[game]
        if attempt > 1 + reruns_max:
            return GameChoice(
                game=None,
                attempt=attempt,
                reason=(
                    f"{game} has {counts[game]} run(s) and none completed; attempt {attempt} "
                    f"would exceed 1 + failed_reruns_per_game_max ({1 + reruns_max}); "
                    "a defect handled under the ladder, not a third run"
                ),
                completed_games=done,
            )
        return GameChoice(
            game=game,
            attempt=attempt,
            reason=f"first game in order without a completed run; {counts[game]} earlier run(s)",
            completed_games=done,
        )
    return GameChoice(
        game=None,
        attempt=0,
        reason=f"every one of the {len(games)} games has a completed run; the set is complete",
        completed_games=done,
    )


def parse_local(stamp: str, tz: dt.tzinfo) -> dt.datetime:
    """A naive pre-registration time stamp interpreted in the machine's local zone."""
    return dt.datetime.fromisoformat(stamp).replace(tzinfo=tz)


def _request_time(job_dir: Path) -> tuple[str, float]:
    request = job_dir / "request.json"
    received = ""
    try:
        data = json.loads(request.read_text(encoding="utf-8"))
        received = str(data.get("received_utc") or "")
    except (OSError, ValueError):
        pass
    return received, request.stat().st_mtime


def newest_job(jobs_dir: Path) -> Path | None:
    """The job directory whose request.json is newest (received_utc, then mtime)."""
    if not jobs_dir.exists():
        return None
    candidates = [p for p in jobs_dir.iterdir() if p.is_dir() and (p / "request.json").exists()]
    if not candidates:
        return None
    return max(candidates, key=_request_time)


def in_flight(jobs_dir: Path) -> str | None:
    """The id of a job whose request exists but whose result does not, else None."""
    newest = newest_job(jobs_dir)
    if newest is None:
        return None
    if (newest / "result.json").exists():
        return None
    return newest.name


@dataclass(frozen=True)
class Decision:
    ok: bool
    reason: str
    request: dict[str, Any] | None
    now_local: str
    earliest_start_local: str
    config_sha256: str | None
    runs_seen: int
    completed_games: list[str]


def decide(
    params: dict[str, Any],
    *,
    root: Path,
    now: dt.datetime,
    artifacts_root: Path | None = None,
    jobs_dir: Path | None = None,
    request_path: Path | None = None,
) -> Decision:
    """Apply every refusal rule in order and build the request when none fires."""
    artifacts_root = artifacts_root or root / "artifacts" / params["experiment_id"]
    jobs_dir = jobs_dir or root / "state" / "jobs"
    request_path = request_path or root / "state" / "job_request.json"
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (the machine's local zone)")
    earliest = parse_local(params["earliest_start_local"], now.tzinfo)
    now_text = now.isoformat(timespec="seconds")
    earliest_text = earliest.isoformat(timespec="seconds")

    runs = discover_runs(artifacts_root)
    choice = choose_game(runs, params["games"], params["failed_reruns_per_game_max"])

    def refuse(reason: str, config_sha256: str | None = None) -> Decision:
        return Decision(
            ok=False,
            reason=reason,
            request=None,
            now_local=now_text,
            earliest_start_local=earliest_text,
            config_sha256=config_sha256,
            runs_seen=len(runs),
            completed_games=choice.completed_games,
        )

    if now < earliest:
        return refuse(
            f"local time {now_text} is before earliest_start_local {earliest_text} "
            "(human budget directive 2026-09-05T19:19:50Z)"
        )

    config_path = root / params["config"]
    if not config_path.exists():
        return refuse(f"graded config {params['config']} does not exist")
    config_sha256 = sha256_of(config_path)
    if config_sha256 != params["graded_config_sha256"]:
        return refuse(
            f"{params['config']} sha256 {config_sha256} != graded_config_sha256 "
            f"{params['graded_config_sha256']}",
            config_sha256,
        )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    runner_limit = int(config.get("wallclock_limit_seconds") or 0)
    if runner_limit != params["wallclock_per_invocation_seconds"]:
        return refuse(
            f"config wallclock_limit_seconds {runner_limit} != "
            f"wallclock_per_invocation_seconds {params['wallclock_per_invocation_seconds']}",
            config_sha256,
        )
    margin = params["job_margin_over_runner_limit_seconds_min"]
    job_limit = params["job_wallclock_limit_seconds"]
    if runner_limit + margin > job_limit:
        return refuse(
            f"config wallclock_limit_seconds {runner_limit} + margin {margin} > "
            f"job_wallclock_limit_seconds {job_limit}: the supervisor would kill before "
            "the runner stops",
            config_sha256,
        )

    if request_path.exists():
        return refuse(
            f"{request_path.name} already exists (a request is pending); read it first",
            config_sha256,
        )
    flying = in_flight(jobs_dir)
    if flying is not None:
        return refuse(
            f"job {flying} has a request.json but no result.json yet (one in flight)",
            config_sha256,
        )

    if choice.game is None:
        return refuse(choice.reason, config_sha256)
    job_id = f"{JOB_ID_PREFIX}-{choice.game}-{choice.attempt}"
    if (jobs_dir / job_id).exists():
        return refuse(
            f"job directory {job_id} already exists under {jobs_dir.name}; the attempt "
            "count from the artifacts root disagrees with the job history",
            config_sha256,
        )
    request = {
        "id": job_id,
        "runner": RUNNER,
        "config": params["config"],
        "game": choice.game,
        "wallclock_limit_s": job_limit,
    }
    return Decision(
        ok=True,
        reason=f"{choice.game} attempt {choice.attempt}: {choice.reason}",
        request=request,
        now_local=now_text,
        earliest_start_local=earliest_text,
        config_sha256=config_sha256,
        runs_seen=len(runs),
        completed_games=choice.completed_games,
    )


def write_request(request_path: Path, request: dict[str, Any]) -> None:
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")


def report_lines(decision: Decision, params: dict[str, Any]) -> list[str]:
    lines = [
        (
            f"gate {params['gate']} pre-registration {params['preregistration_path']} "
            f"sha256 {params['preregistration_sha256']}"
        ),
        f"now (local) {decision.now_local}; earliest_start_local {decision.earliest_start_local}",
        (
            f"runs under artifacts/{params['experiment_id']}: {decision.runs_seen}; "
            f"completed games {len(decision.completed_games)} of {len(params['games'])}"
        ),
    ]
    if decision.config_sha256 is not None:
        lines.append(f"config {params['config']} sha256 {decision.config_sha256}")
    lines.append(("QUEUE " if decision.ok else "REFUSED ") + decision.reason)
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--artifacts-root", type=Path, default=None)
    parser.add_argument("--jobs-dir", type=Path, default=None)
    parser.add_argument("--request-path", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="print the request; write nothing")
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()
    params = load_parameters(root)
    now = dt.datetime.now().astimezone()
    decision = decide(
        params,
        root=root,
        now=now,
        artifacts_root=args.artifacts_root.resolve() if args.artifacts_root else None,
        jobs_dir=args.jobs_dir.resolve() if args.jobs_dir else None,
        request_path=args.request_path.resolve() if args.request_path else None,
    )
    print("\n".join(report_lines(decision, params)))
    if not decision.ok:
        return EXIT_REFUSED
    assert decision.request is not None
    print(json.dumps(decision.request, indent=2))
    if args.dry_run:
        print("dry run: nothing written")
        return EXIT_OK
    request_path = (args.request_path or root / "state" / "job_request.json").resolve()
    write_request(request_path, decision.request)
    print(f"request written: {request_path}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
