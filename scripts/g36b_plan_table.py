"""Tabulate the REF planner diagnostics of one or more run directories (G3.6b).

Reads ``plans.jsonl`` (and ``plan_traces.jsonl`` when present) from each run directory
given on the command line and prints one JSON object per run with the counts the G3.6b
diagnostic asks for: how every search stopped, how often the depth cap dropped new states,
how many distinct states the certified program reached, and whether any search predicted a
level completion. Runs made before the planner instrumentation (E300_ref pre-flight) lack the
diagnostic fields; those read as ``null`` rather than failing.

Usage::

    uv run python scripts/g36b_plan_table.py artifacts/E301_ref/<run_id> [...]

No LLM, no thresholds, no side effects: a bookkeeping script per the constitution's effort
policy. Every number printed cites the ``plans.jsonl`` digest printed alongside it (C4).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

DIAGNOSTIC_FIELDS: tuple[str, ...] = (
    "nodes_expanded",
    "steps_simulated",
    "distinct_states",
    "duplicate_predictions",
    "successors_dropped_at_depth_cap",
    "frame_unchanged_predictions",
    "planned_from_history_length",
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise TypeError(f"{path}:{line_number}: record is not a JSON object")
            rows.append(record)
    return rows


def summarise_numeric(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    if not values:
        return None
    return {
        "n": len(values),
        "min": min(values),
        "max": max(values),
        "sum": sum(values),
        "mean": round(sum(values) / len(values), 2),
    }


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter = Counter(json.dumps(row.get(key), sort_keys=True) for row in rows)
    return {label: count for label, count in sorted(counter.items())}


def tabulate_run(run_dir: Path) -> dict[str, Any]:
    plans_path = run_dir / "plans.jsonl"
    if not plans_path.is_file():
        raise FileNotFoundError(f"{plans_path} does not exist")
    plans = read_jsonl(plans_path)
    table: dict[str, Any] = {
        "run_dir": str(run_dir),
        "plans_jsonl_sha256": sha256_of(plans_path),
        "plans": len(plans),
        "outcome": count_by(plans, "outcome"),
        "reason": count_by(plans, "reason"),
        "queue_exhausted": count_by(plans, "queue_exhausted"),
        "max_depth_reached": count_by(plans, "max_depth_reached"),
        "predicted_levels_completed_max": count_by(plans, "predicted_levels_completed_max"),
        "target_levels_completed": count_by(plans, "target_levels_completed"),
        "hypothesis_id": count_by(plans, "hypothesis_id"),
        "traced": count_by(plans, "traced"),
    }
    for field in DIAGNOSTIC_FIELDS:
        table[field] = summarise_numeric(plans, field)
    dropped = [row.get("successors_dropped_at_depth_cap") for row in plans]
    table["searches_with_states_dropped_at_depth_cap"] = (
        sum(1 for value in dropped if value)
        if any(value is not None for value in dropped)
        else None
    )
    state_counts: Counter[str] = Counter()
    for row in plans:
        counts = row.get("predicted_state_counts")
        if isinstance(counts, dict):
            for state, count in counts.items():
                state_counts[str(state)] += int(count)
    table["predicted_state_counts_total"] = dict(sorted(state_counts.items())) or None
    traces_path = run_dir / "plan_traces.jsonl"
    if traces_path.is_file():
        traces = read_jsonl(traces_path)
        table["plan_traces"] = {
            "sha256": sha256_of(traces_path),
            "records": len(traces),
            "plan_index": count_by(traces, "plan_index"),
            "found": count_by(traces, "found"),
            "depth": count_by(traces, "depth"),
        }
    else:
        table["plan_traces"] = None
    results_path = run_dir / "results.json"
    if results_path.is_file():
        with results_path.open("r", encoding="utf-8") as handle:
            results = json.load(handle)
        inner = results.get("results", results)
        table["results"] = {
            key: inner.get(key)
            for key in (
                "game_id",
                "stop_reason",
                "levels_completed",
                "model_calls",
                "model_wallclock_seconds_total",
                "hypotheses_certified",
                "plans_searched",
                "plans_executed",
                "plan_actions",
                "exploration_actions",
                "actions_total",
                "official_baseline_actions",
                "planner",
                "plan_trace_sampling",
            )
        }
        table["results_json_sha256"] = sha256_of(results_path)
    return table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dirs", nargs="+", type=Path, help="run directories to tabulate")
    args = parser.parse_args(argv)
    for run_dir in args.run_dirs:
        print(json.dumps(tabulate_run(run_dir), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
