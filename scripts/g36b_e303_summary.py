"""Summarise the E300/E301/E302/E303 reference-agent runs for the E303 finding (G3.6b step 12).

Reads, for every run directory given (default: all runs under ``artifacts/E300_ref``,
``E301_ref``, ``E302_ref`` and ``E303_ref``), the files the finding cites and derives the
numbers it quotes: stop reason and binding limit, levels and RHAE, plan-search outcomes,
prediction accuracy (mismatches over compared predictions), hypothesis counts, model time,
tokens and the list-price USD equivalent, plus the SHA-256 of every cited file (C4). The
supervisor's gitignored ``state/jobs/<id>/result.json`` is attached when it names the run.

Usage::

    uv run python scripts/g36b_e303_summary.py [--out /path/report.json] [run_dir ...]

Prints a Markdown table per experiment to stdout and writes the full JSON report to
``--out``. No LLM, no thresholds, no side effects beyond the report file: a bookkeeping
script per the constitution's effort policy. Prices come from
``scripts/g36_preflight_totals.py`` so the USD figures agree with the pre-flight totals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from g36_preflight_totals import PRICES_USD_PER_MILLION, usd_equivalent

DEFAULT_EXPERIMENTS: tuple[str, ...] = ("E300_ref", "E301_ref", "E302_ref", "E303_ref")

CITED_FILES: tuple[str, ...] = (
    "results.json",
    "manifest.json",
    "plans.jsonl",
    "hypotheses.jsonl",
    "transitions.jsonl",
    "model_calls.jsonl",
    "level_accounting.json",
    "rhae.json",
    "SHA256SUMS",
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def repo_relative(path: Path) -> str:
    """Path relative to the repository root when inside it, else the absolute path."""
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


def job_result_for(run_dir: Path, jobs_dir: Path) -> dict[str, Any] | None:
    """Return the supervisor job result that names this run, if any (gitignored)."""
    if not jobs_dir.exists():
        return None
    wanted = repo_relative(run_dir)
    for result_path in sorted(jobs_dir.glob("*/result.json")):
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source = str(result.get("model_seconds_source", ""))
        if source.startswith(wanted):
            return {
                "path": repo_relative(result_path) + " (gitignored)",
                "id": result.get("id"),
                "accepted": result.get("accepted"),
                "returncode": result.get("returncode"),
                "timed_out": result.get("timed_out"),
                "wallclock_s": result.get("wallclock_s"),
                "model_seconds_charged": result.get("model_seconds_charged"),
                "finished_utc": result.get("finished_utc"),
            }
    return None


def summarise_run(run_dir: Path, jobs_dir: Path) -> dict[str, Any]:
    results_doc = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    res = results_doc["results"]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    plans = read_jsonl(run_dir / "plans.jsonl")
    hypotheses = read_jsonl(run_dir / "hypotheses.jsonl")
    model_calls = read_jsonl(run_dir / "model_calls.jsonl")

    outcomes = Counter(str(p.get("outcome")) for p in plans)
    found = [p for p in plans if p.get("outcome") == "found"]
    decertified = [h for h in hypotheses if h.get("event") == "decertified"]
    decertified_on_plan = [h for h in decertified if h.get("plan_index") is not None]
    predicted_level_max = max(
        (int(p.get("predicted_levels_completed_max") or 0) for p in plans), default=0
    )
    nodes_max = max((int(p.get("nodes_expanded") or 0) for p in plans), default=0)
    tokens = dict(res.get("tokens_by_kind", {}))
    compared = int(res.get("predictions_compared", 0))
    mismatches = int(res.get("prediction_mismatches", 0))
    levels = res.get("levels", [])
    per_call_wallclock = [round(float(c.get("wallclock_seconds", 0.0)), 1) for c in model_calls]

    digests = {name: sha256_of(run_dir / name) for name in CITED_FILES if (run_dir / name).exists()}
    return {
        "run_dir": repo_relative(run_dir),
        "experiment_id": results_doc.get("experiment_id"),
        "run_id": results_doc.get("run_id"),
        "game": res.get("stem"),
        "game_id": res.get("game_id"),
        "seed": results_doc.get("seed"),
        "completion_status": results_doc.get("completion_status"),
        "config_file_sha256": results_doc.get("config_file_sha256"),
        "prompt_hash": res.get("prompt_hash"),
        "manifest_git_commit": str(manifest.get("git_commit", ""))[:7],
        "manifest_git_dirty": manifest.get("git_dirty"),
        "model_identifier": res.get("model_identifier"),
        "planner": res.get("planner"),
        "spend_control": res.get("spend_control"),
        "simulation_budget": res.get("simulation_budget"),
        "wallclock_limit_seconds": manifest.get("wallclock_limit_seconds"),
        "stop_reason": res.get("stop_reason"),
        "model_budget_binding": res.get("model_budget_binding"),
        "levels_completed": res.get("levels_completed"),
        "win_levels": res.get("win_levels"),
        "completion_action_indices": [
            lv.get("completion_action_index") for lv in levels if lv.get("completed")
        ],
        "level_1_official_baseline_actions": levels[0].get("official_baseline_actions")
        if levels
        else None,
        "rhae_environment_score": res.get("rhae_environment_score"),
        "rhae_level_scores": res.get("rhae_level_scores"),
        "actions_total": res.get("actions_total"),
        "action_budget_total": res.get("action_budget_total"),
        "exploration_actions": res.get("exploration_actions"),
        "plan_actions": res.get("plan_actions"),
        "reset_actions": res.get("reset_actions"),
        "model_calls": res.get("model_calls"),
        "calls_without_program": res.get("calls_without_program"),
        "model_wallclock_seconds_total": round(
            float(res.get("model_wallclock_seconds_total", 0.0)), 1
        ),
        "per_call_wallclock_seconds": per_call_wallclock,
        "wallclock_seconds": round(float(results_doc.get("wallclock_seconds", 0.0)), 1),
        "tokens_by_kind": tokens,
        "tokens_total": res.get("tokens_total"),
        "usd_equivalent_prereg_prices": round(usd_equivalent(tokens), 4),
        "usd_cli_total_cost_sum": round(
            sum(float(c.get("total_cost_usd") or 0.0) for c in model_calls), 4
        ),
        "plans_searched": res.get("plans_searched"),
        "plan_outcomes": dict(outcomes),
        "plans_found": len(found),
        "plans_found_detail": [
            {
                "plan_index": p.get("plan_index"),
                "hypothesis_id": p.get("hypothesis_id"),
                "depth": p.get("max_depth_reached"),
                "nodes": p.get("nodes_expanded"),
                "actions": len(p.get("actions") or []),
            }
            for p in found
        ],
        "plans_executed": res.get("plans_executed"),
        "nodes_expanded_max": nodes_max,
        "predicted_levels_completed_max": predicted_level_max,
        "predictions_compared": compared,
        "prediction_mismatches": mismatches,
        "prediction_mismatch_rate": round(mismatches / compared, 4) if compared else None,
        "hypotheses_proposed": res.get("hypotheses_proposed"),
        "hypotheses_certified": res.get("hypotheses_certified"),
        "hypotheses_decertified": len(decertified),
        "hypotheses_decertified_on_planned_action": len(decertified_on_plan),
        "supervisor_job": job_result_for(run_dir, jobs_dir),
        "sha256": digests,
    }


def aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "runs": len(runs),
        "plans_searched": sum(int(r.get("plans_searched") or 0) for r in runs),
        "plans_found": sum(int(r["plans_found"]) for r in runs),
        "plans_executed": sum(int(r.get("plans_executed") or 0) for r in runs),
        "plan_actions": sum(int(r.get("plan_actions") or 0) for r in runs),
        "levels_completed": sum(int(r.get("levels_completed") or 0) for r in runs),
        "win_levels": sum(int(r.get("win_levels") or 0) for r in runs),
        "predictions_compared": sum(int(r["predictions_compared"]) for r in runs),
        "prediction_mismatches": sum(int(r["prediction_mismatches"]) for r in runs),
        "model_wallclock_seconds_total": round(
            sum(float(r["model_wallclock_seconds_total"]) for r in runs), 1
        ),
        "wallclock_seconds": round(sum(float(r["wallclock_seconds"]) for r in runs), 1),
        "usd_equivalent_prereg_prices": round(
            sum(float(r["usd_equivalent_prereg_prices"]) for r in runs), 4
        ),
        "usd_cli_total_cost_sum": round(sum(float(r["usd_cli_total_cost_sum"]) for r in runs), 4),
        "hypotheses_certified": sum(int(r.get("hypotheses_certified") or 0) for r in runs),
        "hypotheses_decertified_on_planned_action": sum(
            int(r["hypotheses_decertified_on_planned_action"]) for r in runs
        ),
    }


def markdown_table(runs: list[dict[str, Any]]) -> str:
    header = (
        "| run | game | stop | levels | RHAE env | searched | found | plan acts | "
        "mismatch/compared | model s | wall s | USD eq | results.json |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    rows = [header]
    for r in runs:
        rows.append(
            f"| {r['run_id']} | {r['game']} | {r['stop_reason']} | "
            f"{r['levels_completed']}/{r['win_levels']} | {float(r['rhae_environment_score'] or 0):.2f} | "
            f"{r['plans_searched']} | {r['plans_found']} | {r['plan_actions']} | "
            f"{r['prediction_mismatches']}/{r['predictions_compared']} | "
            f"{r['model_wallclock_seconds_total']:.0f} | {r['wallclock_seconds']:.0f} | "
            f"{r['usd_equivalent_prereg_prices']:.2f} | {r['sha256']['results.json'][:8]} |"
        )
    return "\n".join(rows)


def discover_runs(experiments: tuple[str, ...]) -> list[Path]:
    runs: list[Path] = []
    for experiment in experiments:
        base = REPO_ROOT / "artifacts" / experiment
        if base.exists():
            runs.extend(sorted(p for p in base.iterdir() if (p / "results.json").exists()))
    return runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "run_dirs", nargs="*", type=Path, help="run directories (default: all E300-E303 runs)"
    )
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    parser.add_argument(
        "--jobs-dir", type=Path, default=REPO_ROOT / "state" / "jobs", help="supervisor job results"
    )
    args = parser.parse_args(argv)

    run_dirs = [p.resolve() for p in args.run_dirs] or discover_runs(DEFAULT_EXPERIMENTS)
    if not run_dirs:
        print("no run directories found", file=sys.stderr)
        return 2
    runs = [summarise_run(run_dir, args.jobs_dir) for run_dir in run_dirs]

    by_experiment: dict[str, list[dict[str, Any]]] = {}
    for r in runs:
        by_experiment.setdefault(str(r["experiment_id"]), []).append(r)
    pre_e303 = [r for r in runs if r["experiment_id"] != "E303_ref"]
    report = {
        "script": "scripts/g36b_e303_summary.py",
        "script_sha256": sha256_of(Path(__file__).resolve()),
        "prices_usd_per_million": PRICES_USD_PER_MILLION,
        "runs": runs,
        "totals_by_experiment": {k: aggregate(v) for k, v in by_experiment.items()},
        "totals_before_e303": aggregate(pre_e303),
        "totals_all": aggregate(runs),
    }
    for experiment, exp_runs in by_experiment.items():
        print(f"\n### {experiment}\n")
        print(markdown_table(exp_runs))
    print("\n### totals\n")
    print(json.dumps({k: v for k, v in report.items() if k.startswith("totals")}, indent=1))
    if args.out is not None:
        args.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\nreport written: {args.out} sha256 {sha256_of(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
