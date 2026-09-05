#!/usr/bin/env python3
"""G3.6 cost pre-flight totals over the three pre-registered E300_ref game-runs.

Reads each run's ``results.json``, ``model_calls.jsonl`` and ``SHA256SUMS`` and prints, per run
and summed, the absolute numbers the G3 pre-registration's ``cost_preflight`` block asks for
(``measurement``, ``extrapolation_rule``, ``no_denominator_rule``): model calls, model
wall-clock, run wall-clock, tokens by kind, the list-price USD equivalent, both 25-game
extrapolations and the per-call wall-clock distribution. No LLM is involved (constitution
section 8: aggregation is a script's job). Writes the same figures as JSON when ``--out`` is
given so they can be copied into ``state/BUDGET.json`` without retyping.

Prices are the ones the pre-registration names (docs/EVIDENCE_TOOLING.md section 1,
claude-fable-5-1, USD per million tokens at the 5-minute cache tier). The runs' own
``total_cost_usd`` (the CLI's figure, 1-hour cache tier) is reported alongside, never mixed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

PRICES_USD_PER_MILLION: dict[str, float] = {
    "input": 10.0,
    "output": 50.0,
    "cache_read": 0.25,
    "cache_creation": 12.50,
}
# cost_preflight.game_selection_rule: budget actions of the three games and of all 25.
PREFLIGHT_BUDGET_ACTIONS = 13260
ALL_GAMES_BUDGET_ACTIONS = 85675
GAMES_TOTAL = 25
GAMES_MEASURED = 3


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def usd_equivalent(tokens: dict[str, int]) -> float:
    return sum(tokens.get(kind, 0) * price / 1e6 for kind, price in PRICES_USD_PER_MILLION.items())


def summarise_run(run_dir: Path) -> dict[str, Any]:
    results = json.loads((run_dir / "results.json").read_text())
    inner = results["results"]
    calls = [
        json.loads(line)
        for line in (run_dir / "model_calls.jsonl").read_text().splitlines()
        if line.strip()
    ]
    wall = [float(c["wallclock_seconds"]) for c in calls]
    outputs = [int(c["tokens_by_kind"]["output"]) for c in calls]
    prompt_bytes = [(run_dir / c["prompt_path"]).stat().st_size for c in calls]
    tokens = {k: int(v) for k, v in inner["tokens_by_kind"].items()}
    return {
        "run_id": results["run_id"],
        "game": inner["game_id"],
        "completion_status": results["completion_status"],
        "stop_reason": inner["stop_reason"],
        "model_budget_binding": inner.get("model_budget_binding"),
        "levels_completed": inner["levels_completed"],
        "rhae_environment_score": inner["rhae_environment_score"],
        "actions_total": inner["actions_total"],
        "model_calls": inner["model_calls"],
        "calls_without_program": inner["calls_without_program"],
        "model_wallclock_seconds_total": round(float(inner["model_wallclock_seconds_total"]), 2),
        "wallclock_seconds": round(float(results["wallclock_seconds"]), 1),
        "engine_seconds_outside_model_calls": round(
            float(results["wallclock_seconds"]) - float(inner["model_wallclock_seconds_total"]), 1
        ),
        "tokens_by_kind": tokens,
        "tokens_total": sum(tokens.values()),
        "usd_equivalent_prereg_prices": round(usd_equivalent(tokens), 4),
        "usd_cli_total_cost_sum": round(
            sum(float(c["total_cost_usd"]) for c in calls if c.get("total_cost_usd") is not None), 4
        ),
        "calls_with_null_total_cost_usd": sum(1 for c in calls if c.get("total_cost_usd") is None),
        "per_call_wallclock_seconds": {
            "n": len(wall),
            "min": round(min(wall), 1),
            "median": round(statistics.median(wall), 1),
            "mean": round(statistics.fmean(wall), 1),
            "max": round(max(wall), 1),
            "values": [round(w, 1) for w in wall],
        },
        "per_call_output_tokens": {"mean": round(statistics.fmean(outputs)), "values": outputs},
        "per_call_prompt_bytes": prompt_bytes,
        "history_length_at_call": [c["history_length_at_call"] for c in calls],
        "cache_read_tokens_any_call": any(
            int(c["tokens_by_kind"]["cache_read"]) > 0 for c in calls
        ),
        "config_file_sha256": results["config_file_sha256"],
        "results_json_sha256": sha256_of(run_dir / "results.json"),
        "model_calls_jsonl_sha256": sha256_of(run_dir / "model_calls.jsonl"),
        "sha256sums_sha256": sha256_of(run_dir / "SHA256SUMS"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="write the JSON summary here")
    args = parser.parse_args()

    runs = [summarise_run(d) for d in args.run_dirs]
    all_wall = [w for r in runs for w in r["per_call_wallclock_seconds"]["values"]]
    all_out = [o for r in runs for o in r["per_call_output_tokens"]["values"]]
    tokens_sum: dict[str, int] = {}
    for r in runs:
        for k, v in r["tokens_by_kind"].items():
            tokens_sum[k] = tokens_sum.get(k, 0) + v
    usd_sum = sum(r["usd_equivalent_prereg_prices"] for r in runs)
    model_s = sum(r["model_wallclock_seconds_total"] for r in runs)
    wall_s = sum(r["wallclock_seconds"] for r in runs)
    calls = sum(r["model_calls"] for r in runs)
    count_weighted = usd_sum * GAMES_TOTAL / GAMES_MEASURED
    budget_weighted = usd_sum * ALL_GAMES_BUDGET_ACTIONS / PREFLIGHT_BUDGET_ACTIONS
    summary = {
        "games_measured": len(runs),
        "runs": runs,
        "totals": {
            "model_calls": calls,
            "model_wallclock_seconds_total": round(model_s, 2),
            "wallclock_seconds": round(wall_s, 1),
            "engine_seconds_outside_model_calls": round(wall_s - model_s, 1),
            "tokens_by_kind": tokens_sum,
            "tokens_total": sum(tokens_sum.values()),
            "usd_equivalent_prereg_prices": round(usd_sum, 4),
            "usd_cli_total_cost_sum": round(sum(r["usd_cli_total_cost_sum"] for r in runs), 4),
        },
        "per_call_wallclock_seconds_all_runs": {
            "n": len(all_wall),
            "min": round(min(all_wall), 1),
            "median": round(statistics.median(all_wall), 1),
            "mean": round(statistics.fmean(all_wall), 1),
            "max": round(max(all_wall), 1),
            "stdev": round(statistics.stdev(all_wall), 1),
            "over_170s": sum(1 for w in all_wall if w >= 170.0),
            "sorted": sorted(round(w, 1) for w in all_wall),
        },
        "per_call_output_tokens_all_runs": {
            "n": len(all_out),
            "min": min(all_out),
            "median": statistics.median(all_out),
            "mean": round(statistics.fmean(all_out)),
            "max": max(all_out),
        },
        "extrapolation_25_games": {
            "count_weighted_usd": round(count_weighted, 2),
            "budget_weighted_usd": round(budget_weighted, 2),
            "projected_usd_25": round(max(count_weighted, budget_weighted), 2),
            "count_weighted_model_seconds": round(model_s * GAMES_TOTAL / GAMES_MEASURED),
            "budget_weighted_model_seconds": round(
                model_s * ALL_GAMES_BUDGET_ACTIONS / PREFLIGHT_BUDGET_ACTIONS
            ),
            "cap_bound_model_seconds_at_1200": 1200 * GAMES_TOTAL,
            "cap_bound_model_seconds_at_2400": 2400 * GAMES_TOTAL,
            "count_weighted_wallclock_seconds": round(wall_s * GAMES_TOTAL / GAMES_MEASURED),
            "budget_weighted_wallclock_seconds": round(
                wall_s * ALL_GAMES_BUDGET_ACTIONS / PREFLIGHT_BUDGET_ACTIONS
            ),
            "five_hour_windows_at_5000s": {
                "count_weighted": round(model_s * GAMES_TOTAL / GAMES_MEASURED / 5000, 2),
                "cap_bound_1200": round(1200 * GAMES_TOTAL / 5000, 2),
                "cap_bound_2400": round(2400 * GAMES_TOTAL / 5000, 2),
            },
        },
        "prices_usd_per_million": PRICES_USD_PER_MILLION,
    }
    text = json.dumps(summary, indent=2)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
