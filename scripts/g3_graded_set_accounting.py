"""Cost accounting for the G3b graded set (G3.6b step 17).

Implements the ``graded_set.cost_accounting`` clause of the G3b pre-registration: after
every E304_ref run the agent records the run id, stop reason, model wall-clock seconds, the
supervisor's charged seconds, tokens by kind, the list-price USD equivalent at the G3
pre-flight prices, the cumulative totals, the linear projection to the required number of
games, and whether the cumulative model time has crossed
``thresholds.set_model_seconds_escalate_above`` (an escalation under constitution section 6
item 10 before any further job).

Every parameter that decides anything is read from the hash-locked pre-registration through
``scripts/verify_run.py``'s ``load_preregistration``; nothing numeric is embedded here except
the token prices, which the G3 pre-registration states in prose and which
``scripts/g36_preflight_totals.py`` already carries (the two are printed side by side in the
output so a reader can compare them). Per-run numbers come from
``scripts/g36b_e303_summary.py``'s reader, so the graded set is measured with the same code
that measured the E303 finding.

Usage::

    uv run python scripts/g3_graded_set_accounting.py [--artifacts-root artifacts/E304_ref]
        [--budget state/BUDGET.json] [--jobs-dir state/jobs] [--out report.json] [--dry-run]

Exit code 0 normally, 3 when the escalate flag is set (the budget file is still written), 2 on
a usage error. No LLM, no thresholds of its own, no side effects beyond ``--budget`` and
``--out``: a bookkeeping script per the constitution's effort policy.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from g36_preflight_totals import PRICES_USD_PER_MILLION
from g36b_e303_summary import repo_relative, sha256_of, summarise_run
from verify_run import load_preregistration

GATE = "G3b"
BUDGET_KEY = "g3_graded_set"
EXIT_ESCALATE = 3
TOKEN_KINDS: tuple[str, ...] = ("input", "output", "cache_read", "cache_creation")


def load_parameters(root: Path = REPO_ROOT) -> dict[str, Any]:
    """Read every deciding parameter from the hash-locked G3b pre-registration."""
    prereg, path, digest = load_preregistration(GATE, root)
    thresholds = prereg["thresholds"]
    graded_set = prereg.get("graded_set") or {}
    games = list(graded_set.get("games") or [])
    required = int(thresholds["graded_games_required"])
    if len(games) != required:
        raise ValueError(
            f"{GATE}: graded_set.games lists {len(games)} games but "
            f"thresholds.graded_games_required is {required}"
        )
    return {
        "gate": GATE,
        "preregistration_path": repo_relative(path),
        "preregistration_sha256": digest,
        "experiment_id": str(thresholds["experiment_id"]),
        "graded_config_sha256": str(thresholds["graded_config_sha256"]),
        "games": games,
        "games_required": required,
        "runs_per_game": int(thresholds["graded_runs_per_game"]),
        "set_model_seconds_escalate_above": float(thresholds["set_model_seconds_escalate_above"]),
        "set_model_seconds_hard_bound": float(thresholds["set_model_seconds_hard_bound"]),
        "model_wallclock_per_run_seconds": float(thresholds["model_wallclock_per_run_seconds"]),
        "cost_accounting_clause": str(graded_set.get("cost_accounting", "")),
    }


def discover_runs(artifacts_root: Path) -> list[Path]:
    """Every run directory under the graded root that has a results.json, in id order."""
    if not artifacts_root.exists():
        return []
    return sorted(p for p in artifacts_root.iterdir() if (p / "results.json").exists())


def run_record(run_dir: Path, jobs_dir: Path) -> dict[str, Any]:
    """The per-run record the pre-registration asks for, narrowed from the E303 reader."""
    full = summarise_run(run_dir, jobs_dir)
    job = full.get("supervisor_job") or {}
    tokens = {kind: int(full["tokens_by_kind"].get(kind, 0)) for kind in TOKEN_KINDS}
    return {
        "run_dir": full["run_dir"],
        "run_id": full["run_id"],
        "experiment_id": full["experiment_id"],
        "game": full["game"],
        "game_id": full["game_id"],
        "completion_status": full["completion_status"],
        "config_file_sha256": full["config_file_sha256"],
        "stop_reason": full["stop_reason"],
        "model_budget_binding": full["model_budget_binding"],
        "levels_completed": full["levels_completed"],
        "win_levels": full["win_levels"],
        "rhae_environment_score": full["rhae_environment_score"],
        "model_calls": full["model_calls"],
        "model_wallclock_seconds_total": full["model_wallclock_seconds_total"],
        "wallclock_seconds": full["wallclock_seconds"],
        "supervisor_job_id": job.get("id"),
        "supervisor_charged_seconds": job.get("model_seconds_charged"),
        "supervisor_job_wallclock_s": job.get("wallclock_s"),
        "supervisor_job_returncode": job.get("returncode"),
        "tokens_by_kind": tokens,
        "tokens_total": sum(tokens.values()),
        "usd_equivalent_prereg_prices": full["usd_equivalent_prereg_prices"],
        "usd_cli_total_cost_sum": full["usd_cli_total_cost_sum"],
        "results_json_sha256": full["sha256"].get("results.json"),
        "sha256sums_sha256": full["sha256"].get("SHA256SUMS"),
    }


def cumulative(runs: list[dict[str, Any]]) -> dict[str, Any]:
    charged = [
        r["supervisor_charged_seconds"] for r in runs if r["supervisor_charged_seconds"] is not None
    ]
    tokens = {
        kind: sum(int(r["tokens_by_kind"].get(kind, 0)) for r in runs) for kind in TOKEN_KINDS
    }
    return {
        "runs": len(runs),
        "games_distinct": len({r["game"] for r in runs}),
        "model_calls": sum(int(r["model_calls"] or 0) for r in runs),
        "model_wallclock_seconds_total": round(
            sum(float(r["model_wallclock_seconds_total"]) for r in runs), 1
        ),
        "supervisor_charged_seconds_total": int(sum(int(c) for c in charged)),
        "supervisor_charged_runs": len(charged),
        "wallclock_seconds": round(sum(float(r["wallclock_seconds"]) for r in runs), 1),
        "tokens_by_kind": tokens,
        "tokens_total": sum(tokens.values()),
        "usd_equivalent_prereg_prices": round(
            sum(float(r["usd_equivalent_prereg_prices"]) for r in runs), 4
        ),
        "usd_cli_total_cost_sum": round(sum(float(r["usd_cli_total_cost_sum"]) for r in runs), 4),
        "levels_completed": sum(int(r["levels_completed"] or 0) for r in runs),
        "win_levels": sum(int(r["win_levels"] or 0) for r in runs),
    }


def linear_projection(totals: dict[str, Any], games_required: int) -> dict[str, Any] | None:
    """Scale the cumulative totals from the runs seen so far to the full set, linearly."""
    basis = int(totals["runs"])
    if basis == 0:
        return None
    factor = games_required / basis
    return {
        "basis_runs": basis,
        "target_runs": games_required,
        "factor": round(factor, 4),
        "model_wallclock_seconds_total": round(totals["model_wallclock_seconds_total"] * factor, 1),
        "supervisor_charged_seconds_total": round(
            totals["supervisor_charged_seconds_total"] * factor, 1
        ),
        "wallclock_seconds": round(totals["wallclock_seconds"] * factor, 1),
        "tokens_total": round(totals["tokens_total"] * factor),
        "usd_equivalent_prereg_prices": round(totals["usd_equivalent_prereg_prices"] * factor, 2),
        "usd_cli_total_cost_sum": round(totals["usd_cli_total_cost_sum"] * factor, 2),
    }


def account(
    runs: list[dict[str, Any]],
    params: dict[str, Any],
    artifacts_root: Path,
    recorded_utc: str,
) -> dict[str, Any]:
    """Assemble the ``g3_graded_set`` section: runs, totals, projection and the flags."""
    totals = cumulative(runs)
    model_seconds = float(totals["model_wallclock_seconds_total"])
    escalate_above = float(params["set_model_seconds_escalate_above"])
    hard_bound = float(params["set_model_seconds_hard_bound"])
    games_seen = [r["game"] for r in runs]
    games = list(params["games"])
    counts = {g: games_seen.count(g) for g in games}
    return {
        "recorded_utc": recorded_utc,
        "script": "scripts/g3_graded_set_accounting.py",
        "script_sha256": sha256_of(Path(__file__).resolve()),
        "gate": params["gate"],
        "preregistration_path": params["preregistration_path"],
        "preregistration_sha256": params["preregistration_sha256"],
        "experiment_id": params["experiment_id"],
        "graded_config_sha256": params["graded_config_sha256"],
        "artifacts_root": repo_relative(artifacts_root),
        "prices_usd_per_million": dict(PRICES_USD_PER_MILLION),
        "prices_source": (
            "preregistration G3 cost_preflight.measurement (prose: 10 / 50 / 0.25 / 12.50 USD "
            "per million input / output / cache-read / cache-creation tokens), carried by "
            "scripts/g36_preflight_totals.py PRICES_USD_PER_MILLION"
        ),
        "model_seconds_measure": (
            "sum of results.json results.model_wallclock_seconds_total over the runs (the "
            "runner's own clock); the supervisor's charged seconds are reported beside it"
        ),
        "set_model_seconds_escalate_above": escalate_above,
        "set_model_seconds_hard_bound": hard_bound,
        "games_required": params["games_required"],
        "runs": runs,
        "cumulative": totals,
        "projection_linear": linear_projection(totals, int(params["games_required"])),
        "games_remaining": [g for g in games if counts[g] == 0],
        "games_run_more_than_once": [g for g in games if counts[g] > 1],
        "games_outside_graded_set": sorted({g for g in games_seen if g not in counts}),
        "runs_with_other_experiment_id": [
            r["run_id"] for r in runs if r["experiment_id"] != params["experiment_id"]
        ],
        "set_complete": all(counts[g] >= 1 for g in games),
        "escalate": model_seconds > escalate_above,
        "hard_bound_exceeded": model_seconds > hard_bound,
        "escalation_rule": (
            "section 6 item 10 escalation before any further job when cumulative model "
            "seconds exceed set_model_seconds_escalate_above; the set never stops by itself"
        ),
    }


def write_budget(budget_path: Path, section: dict[str, Any]) -> None:
    """Replace the ``g3_graded_set`` key of the budget file, keeping every other key."""
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    if not isinstance(budget, dict):
        raise TypeError(f"{budget_path} is not a JSON object")
    budget[BUDGET_KEY] = section
    budget_path.write_text(json.dumps(budget, indent=2) + "\n", encoding="utf-8")


def summary_lines(section: dict[str, Any]) -> list[str]:
    totals = section["cumulative"]
    lines = [
        (
            f"{section['experiment_id']} graded set under {section['artifacts_root']}: "
            f"{totals['runs']} run(s), {totals['games_distinct']} distinct game(s), "
            f"{len(section['games_remaining'])} remaining of {section['games_required']}"
        ),
        (
            f"cumulative model seconds {totals['model_wallclock_seconds_total']:.1f} "
            f"(supervisor charged {totals['supervisor_charged_seconds_total']} over "
            f"{totals['supervisor_charged_runs']} run(s)); escalate above "
            f"{section['set_model_seconds_escalate_above']:.0f}, hard bound "
            f"{section['set_model_seconds_hard_bound']:.0f}"
        ),
        (
            f"cumulative USD equivalent {totals['usd_equivalent_prereg_prices']:.2f} "
            f"(CLI {totals['usd_cli_total_cost_sum']:.2f}); levels {totals['levels_completed']}"
            f"/{totals['win_levels']}"
        ),
    ]
    projection = section["projection_linear"]
    if projection is not None:
        lines.append(
            f"linear projection to {projection['target_runs']} runs: "
            f"{projection['model_wallclock_seconds_total']:.0f} model s, "
            f"{projection['usd_equivalent_prereg_prices']:.2f} USD equivalent"
        )
    lines.append(
        f"escalate: {section['escalate']}  hard_bound_exceeded: {section['hard_bound_exceeded']}"
    )
    for key in (
        "games_run_more_than_once",
        "games_outside_graded_set",
        "runs_with_other_experiment_id",
    ):
        if section[key]:
            lines.append(f"WARNING {key}: {section[key]}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--artifacts-root", type=Path, default=None)
    parser.add_argument("--budget", type=Path, default=None)
    parser.add_argument("--jobs-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None, help="also write the section here")
    parser.add_argument("--dry-run", action="store_true", help="print only; write nothing")
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()
    params = load_parameters(root)
    artifacts_root = (args.artifacts_root or root / "artifacts" / params["experiment_id"]).resolve()
    budget_path = (args.budget or root / "state" / "BUDGET.json").resolve()
    jobs_dir = (args.jobs_dir or root / "state" / "jobs").resolve()
    recorded_utc = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    runs = [run_record(run_dir, jobs_dir) for run_dir in discover_runs(artifacts_root)]
    section = account(runs, params, artifacts_root, recorded_utc)
    print("\n".join(summary_lines(section)))
    if not args.dry_run:
        write_budget(budget_path, section)
        print(f"budget written: {repo_relative(budget_path)} key {BUDGET_KEY}")
        if args.out is not None:
            args.out.write_text(
                json.dumps(section, indent=1, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(f"report written: {args.out} sha256 {sha256_of(args.out)}")
    return EXIT_ESCALATE if section["escalate"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
