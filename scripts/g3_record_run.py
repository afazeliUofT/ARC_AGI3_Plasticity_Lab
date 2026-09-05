"""Verify a finished graded-set run before it is recorded (G3.6b step 19).

Implements items 1 and 2 of the "After every run: record, then account" section of
``docs/G3_GRADED_SET_RECIPE.md`` for the G3b graded set. Given a supervisor job id (default:
the newest ``state/jobs/<id>/`` that has a ``result.json``), it reads the job result, locates
the run directory under the graded artifacts root, and verifies the run independently of its
own summary. Every threshold it applies is read from the hash-locked G3b pre-registration
through ``scripts/verify_run.py``'s ``load_preregistration``; the one operational number that
is not a threshold (the per-call wall-clock allowance that a timed-out call may add to the
run's model time) is read from the graded config itself, whose digest is checked first.

Checks, one printed line each (``PASS``/``FAIL name: detail``):

* the job result exists, its return code is 0, it did not time out, and its wall-clock is
  within ``thresholds.job_wallclock_limit_seconds``;
* the job request (when present) names the graded config and the run's game agrees with it;
* the run directory is located and its name is the run id ``results.json`` records;
* every entry of ``SHA256SUMS`` matches the file on disk (hashlib, never the shell);
* ``results.json`` ``config_file_sha256`` equals ``thresholds.graded_config_sha256`` and its
  ``experiment_id`` equals ``thresholds.experiment_id``;
* ``manifest.json`` ``prompt_hash`` (and ``results.prompt_hash``) equal ``thresholds.prompt_hash``;
* ``manifest.json`` ``wallclock_limit_seconds`` equals ``thresholds.wallclock_per_invocation_seconds``;
* ``results.json`` ``completion_status`` is ``completed``;
* ``stderr.log`` is empty (else its first lines are printed);
* ``model_wallclock_seconds_total`` is at most ``thresholds.model_wallclock_per_run_seconds``
  plus the config's ``model_client.call_wallclock_seconds``;
* ``model_calls`` is at most ``thresholds.calls_per_run_max``;
* ``resumptions`` is at most ``thresholds.resumptions_used_max``, the seed is ``thresholds.seed``
  and the game is one of ``graded_set.games``.

It then prints the run id, game, stop reason, levels completed over win levels, the RHAE
environment score, model calls, model wall-clock seconds and the digests of ``results.json``
and ``SHA256SUMS``, and exits 0 when every check passes, 2 when any fails (the run is then
labelled ``failed`` in the ledger and ``scripts/g3_next_job.py`` offers attempt 2), or 1 on a
usage error. ``--json <path>`` writes the same as a report.

Usage::

    uv run python scripts/g3_record_run.py [--job-id g37-ar25-1] [--json /tmp/report.json]

No LLM, no thresholds of its own, no side effect beyond ``--json``: a bookkeeping script per
the constitution's effort policy. It never writes the ledger; the turn that records the run
does that by hand, citing this script's printed lines.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from g36b_e303_summary import repo_relative, sha256_of
from verify_run import load_preregistration

GATE = "G3b"
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_FAILED = 2
STDERR_LINES_SHOWN = 5


class RecordRunError(Exception):
    """A usage error: the job or run cannot be found at all (exit 1)."""


def load_parameters(root: Path = REPO_ROOT) -> dict[str, Any]:
    """Read every deciding parameter from the hash-locked G3b pre-registration.

    The per-call wall-clock allowance is read from the graded config file named by the
    pre-registration; its digest is reported so the reader can see it matched.
    """
    prereg, path, digest = load_preregistration(GATE, root)
    thresholds = prereg["thresholds"]
    graded_set = prereg.get("graded_set") or {}
    experiment = prereg.get("graded_experiment") or {}
    config_rel = str(experiment["config"])
    config_path = root / config_rel
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    model_client = (config.get("runner_params") or {}).get("model_client") or {}
    return {
        "gate": GATE,
        "preregistration_path": repo_relative(path),
        "preregistration_sha256": digest,
        "experiment_id": str(thresholds["experiment_id"]),
        "config": config_rel,
        "config_sha256_on_disk": sha256_of(config_path),
        "graded_config_sha256": str(thresholds["graded_config_sha256"]),
        "prompt_hash": str(thresholds["prompt_hash"]),
        "games": [str(g) for g in (graded_set.get("games") or [])],
        "seed": int(thresholds["seed"]),
        "wallclock_per_invocation_seconds": int(thresholds["wallclock_per_invocation_seconds"]),
        "job_wallclock_limit_seconds": int(thresholds["job_wallclock_limit_seconds"]),
        "model_wallclock_per_run_seconds": float(thresholds["model_wallclock_per_run_seconds"]),
        "calls_per_run_max": int(thresholds["calls_per_run_max"]),
        "resumptions_used_max": int(thresholds["resumptions_used_max"]),
        "call_wallclock_seconds": float(model_client.get("call_wallclock_seconds") or 0.0),
    }


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str

    def line(self) -> str:
        return f"{'PASS' if self.ok else 'FAIL'} {self.name}: {self.detail}"


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RecordRunError(f"{path} is not a JSON object")
    return data


def newest_finished_job(jobs_dir: Path) -> Path | None:
    """The job directory with a result.json whose finished_utc (then mtime) is newest."""
    if not jobs_dir.exists():
        return None
    candidates = [p for p in jobs_dir.iterdir() if p.is_dir() and (p / "result.json").exists()]
    if not candidates:
        return None

    def key(job_dir: Path) -> tuple[str, float]:
        result_path = job_dir / "result.json"
        finished = ""
        try:
            finished = str(_read_json(result_path).get("finished_utc") or "")
        except (OSError, ValueError, RecordRunError):
            pass
        return finished, result_path.stat().st_mtime

    return max(candidates, key=key)


def locate_run_dir(result: dict[str, Any], root: Path) -> Path | None:
    """The run directory a job result names: model_seconds_source first, stdout_tail second."""
    source = str(result.get("model_seconds_source") or "")
    if source.endswith("results.json"):
        candidate = root / Path(source).parent
        if candidate.is_dir():
            return candidate
    for line in str(result.get("stdout_tail") or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        run_dir = record.get("run_dir") if isinstance(record, dict) else None
        if run_dir:
            candidate = root / str(run_dir)
            if candidate.is_dir():
                return candidate
    return None


def verify_sha256sums(run_dir: Path) -> tuple[int, list[str], list[str]]:
    """Recompute every SHA256SUMS entry; returns (entries, mismatched, missing)."""
    lines = (run_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    entries = 0
    mismatched: list[str] = []
    missing: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        expected, _, name = line.partition("  ")
        name = name.strip()
        if not name or len(expected) != 64:
            raise RecordRunError(f"unparseable SHA256SUMS line: {line!r}")
        entries += 1
        target = run_dir / name
        if not target.exists():
            missing.append(name)
        elif sha256_of(target) != expected:
            mismatched.append(name)
    return entries, mismatched, missing


def _stderr_head(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    head = text.splitlines()[:STDERR_LINES_SHOWN]
    return " | ".join(head)


def check_job(
    result: dict[str, Any], request: dict[str, Any] | None, params: dict[str, Any]
) -> list[Check]:
    checks = [
        Check(
            "job_returncode_zero",
            result.get("returncode") == 0,
            f"returncode {result.get('returncode')!r}",
        ),
        Check(
            "job_not_timed_out",
            result.get("timed_out") is False,
            f"timed_out {result.get('timed_out')!r}",
        ),
    ]
    wallclock = result.get("wallclock_s")
    limit = params["job_wallclock_limit_seconds"]
    checks.append(
        Check(
            "job_wallclock_within_limit",
            isinstance(wallclock, (int, float)) and float(wallclock) <= limit,
            f"wallclock_s {wallclock!r} <= job_wallclock_limit_seconds {limit}",
        )
    )
    if request is not None:
        checks.append(
            Check(
                "job_request_names_graded_config",
                str(request.get("config")) == params["config"],
                f"request config {request.get('config')!r} == {params['config']!r}",
            )
        )
    return checks


def check_run(
    run_dir: Path, request: dict[str, Any] | None, params: dict[str, Any]
) -> tuple[list[Check], dict[str, Any]]:
    """Every run-level check plus the summary the turn cites."""
    checks: list[Check] = []
    for name in ("results.json", "manifest.json", "SHA256SUMS", "stderr.log"):
        if not (run_dir / name).exists():
            raise RecordRunError(f"{repo_relative(run_dir)} lacks {name}")
    results_doc = _read_json(run_dir / "results.json")
    res = results_doc.get("results") or {}
    if not isinstance(res, dict):
        raise RecordRunError(f"{run_dir / 'results.json'} has no 'results' mapping")
    manifest = _read_json(run_dir / "manifest.json")

    run_id = str(results_doc.get("run_id"))
    checks.append(
        Check(
            "run_dir_is_run_id",
            run_dir.name == run_id,
            f"directory {run_dir.name} == results.json run_id {run_id}",
        )
    )
    entries, mismatched, missing = verify_sha256sums(run_dir)
    checks.append(
        Check(
            "sha256sums_verified",
            entries > 0 and not mismatched and not missing,
            f"{entries} entries, {len(mismatched)} mismatched {mismatched[:5]}, "
            f"{len(missing)} missing {missing[:5]}",
        )
    )
    checks.append(
        Check(
            "results_config_digest",
            results_doc.get("config_file_sha256") == params["graded_config_sha256"],
            f"config_file_sha256 {results_doc.get('config_file_sha256')} == "
            f"graded_config_sha256 {params['graded_config_sha256']}",
        )
    )
    checks.append(
        Check(
            "results_experiment_id",
            results_doc.get("experiment_id") == params["experiment_id"],
            f"experiment_id {results_doc.get('experiment_id')!r} == {params['experiment_id']!r}",
        )
    )
    checks.append(
        Check(
            "prompt_hash",
            manifest.get("prompt_hash") == params["prompt_hash"]
            and res.get("prompt_hash") == params["prompt_hash"],
            f"manifest {manifest.get('prompt_hash')} / results {res.get('prompt_hash')} == "
            f"thresholds.prompt_hash {params['prompt_hash']}",
        )
    )
    checks.append(
        Check(
            "manifest_wallclock_limit",
            manifest.get("wallclock_limit_seconds") == params["wallclock_per_invocation_seconds"],
            f"wallclock_limit_seconds {manifest.get('wallclock_limit_seconds')!r} == "
            f"wallclock_per_invocation_seconds {params['wallclock_per_invocation_seconds']}",
        )
    )
    checks.append(
        Check(
            "completion_status_completed",
            results_doc.get("completion_status") == "completed",
            f"completion_status {results_doc.get('completion_status')!r}",
        )
    )
    stderr_path = run_dir / "stderr.log"
    stderr_size = stderr_path.stat().st_size
    checks.append(
        Check(
            "stderr_empty",
            stderr_size == 0,
            "0 bytes" if stderr_size == 0 else f"{stderr_size} bytes: {_stderr_head(stderr_path)}",
        )
    )
    model_seconds = float(res.get("model_wallclock_seconds_total") or 0.0)
    model_cap = params["model_wallclock_per_run_seconds"] + params["call_wallclock_seconds"]
    checks.append(
        Check(
            "model_seconds_within_cap",
            model_seconds <= model_cap,
            f"model_wallclock_seconds_total {model_seconds:.1f} <= "
            f"model_wallclock_per_run_seconds {params['model_wallclock_per_run_seconds']:.0f} + "
            f"call_wallclock_seconds {params['call_wallclock_seconds']:.0f}",
        )
    )
    model_calls = int(res.get("model_calls") or 0)
    checks.append(
        Check(
            "model_calls_within_cap",
            model_calls <= params["calls_per_run_max"],
            f"model_calls {model_calls} <= calls_per_run_max {params['calls_per_run_max']}",
        )
    )
    resumptions = int(res.get("resumptions") or 0)
    checks.append(
        Check(
            "resumptions_within_max",
            resumptions <= params["resumptions_used_max"],
            f"resumptions {resumptions} <= resumptions_used_max {params['resumptions_used_max']}",
        )
    )
    checks.append(
        Check(
            "seed_preregistered",
            results_doc.get("seed") == params["seed"],
            f"seed {results_doc.get('seed')!r} == thresholds.seed {params['seed']}",
        )
    )
    game = str(res.get("stem") or "")
    checks.append(
        Check(
            "game_in_graded_set",
            game in params["games"],
            f"stem {game!r} in graded_set.games ({len(params['games'])})",
        )
    )
    if request is not None:
        checks.append(
            Check(
                "game_matches_job_request",
                game == str(request.get("game")),
                f"stem {game!r} == request game {request.get('game')!r}",
            )
        )
    summary = {
        "run_dir": repo_relative(run_dir),
        "run_id": run_id,
        "experiment_id": results_doc.get("experiment_id"),
        "game": game,
        "game_id": res.get("game_id"),
        "completion_status": results_doc.get("completion_status"),
        "stop_reason": res.get("stop_reason"),
        "model_budget_binding": res.get("model_budget_binding"),
        "levels_completed": res.get("levels_completed"),
        "win_levels": res.get("win_levels"),
        "rhae_environment_score": res.get("rhae_environment_score"),
        "model_calls": model_calls,
        "model_wallclock_seconds_total": round(model_seconds, 1),
        "wallclock_seconds": round(float(results_doc.get("wallclock_seconds") or 0.0), 1),
        "results_json_sha256": sha256_of(run_dir / "results.json"),
        "sha256sums_sha256": sha256_of(run_dir / "SHA256SUMS"),
        "sha256sums_entries": entries,
    }
    return checks, summary


def verify_job(
    job_dir: Path, params: dict[str, Any], root: Path
) -> tuple[list[Check], dict[str, Any]]:
    """All checks for one job directory, and the report the turn cites."""
    result_path = job_dir / "result.json"
    if not result_path.exists():
        raise RecordRunError(f"{repo_relative(job_dir)} has no result.json (job not finished)")
    result = _read_json(result_path)
    request_path = job_dir / "request.json"
    request = _read_json(request_path) if request_path.exists() else None

    checks = check_job(result, request, params)
    run_dir = locate_run_dir(result, root)
    checks.append(
        Check(
            "run_dir_located",
            run_dir is not None,
            repo_relative(run_dir) if run_dir is not None else "no run directory named by result",
        )
    )
    report: dict[str, Any] = {
        "gate": params["gate"],
        "preregistration_path": params["preregistration_path"],
        "preregistration_sha256": params["preregistration_sha256"],
        "config": params["config"],
        "config_sha256_on_disk": params["config_sha256_on_disk"],
        "job_id": job_dir.name,
        "job_result": {
            "returncode": result.get("returncode"),
            "timed_out": result.get("timed_out"),
            "wallclock_s": result.get("wallclock_s"),
            "model_seconds_charged": result.get("model_seconds_charged"),
            "model_seconds_source": result.get("model_seconds_source"),
            "finished_utc": result.get("finished_utc"),
        },
        "run": None,
    }
    if run_dir is not None:
        run_checks, summary = check_run(run_dir, request, params)
        checks.extend(run_checks)
        report["run"] = summary
    report["checks"] = [asdict(c) for c in checks]
    report["passed"] = sum(1 for c in checks if c.ok)
    report["failed"] = sum(1 for c in checks if not c.ok)
    report["ok"] = report["failed"] == 0
    return checks, report


def report_lines(checks: list[Check], report: dict[str, Any]) -> list[str]:
    lines = [
        (
            f"gate {report['gate']} pre-registration {report['preregistration_path']} "
            f"sha256 {report['preregistration_sha256']}"
        ),
        f"job {report['job_id']}: {json.dumps(report['job_result'])}",
    ]
    lines.extend(c.line() for c in checks)
    run = report.get("run")
    if run is not None:
        lines.append(
            f"run {run['run_id']} game {run['game']} stop_reason {run['stop_reason']} "
            f"levels {run['levels_completed']}/{run['win_levels']} "
            f"rhae_environment_score {run['rhae_environment_score']} "
            f"model_calls {run['model_calls']} "
            f"model_wallclock_seconds_total {run['model_wallclock_seconds_total']}"
        )
        lines.append(
            f"results.json sha256 {run['results_json_sha256']}; "
            f"SHA256SUMS sha256 {run['sha256sums_sha256']} ({run['sha256sums_entries']} entries)"
        )
    verdict = "RUN VERIFIED" if report["ok"] else "RUN FAILED VERIFICATION"
    lines.append(f"{verdict}: {report['passed']} passed, {report['failed']} failed")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--jobs-dir", type=Path, default=None)
    parser.add_argument("--job-id", default=None, help="default: newest job with a result.json")
    parser.add_argument("--json", type=Path, default=None, help="write the report here")
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()
    jobs_dir = (args.jobs_dir or root / "state" / "jobs").resolve()
    try:
        params = load_parameters(root)
        if args.job_id:
            job_dir = jobs_dir / args.job_id
            if not job_dir.is_dir():
                raise RecordRunError(f"no job directory {args.job_id} under {jobs_dir}")
        else:
            newest = newest_finished_job(jobs_dir)
            if newest is None:
                raise RecordRunError(f"no job with a result.json under {jobs_dir}")
            job_dir = newest
        checks, report = verify_job(job_dir, params, root)
    except RecordRunError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return EXIT_ERROR
    print("\n".join(report_lines(checks, report)))
    if args.json is not None:
        args.json.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"report written: {args.json} sha256 {sha256_of(args.json)}")
    return EXIT_OK if report["ok"] else EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
