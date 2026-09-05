"""Why did every REF plan search return ``not_found`` while hypotheses were certified? (G3.6b)

Answers the human's four-candidate question (docs/DECISION_LOG.md 2026-09-05T08:20:01Z) over
the six REF runs made so far (three E300_ref pre-flight, three E301_ref diagnostic) with three
mechanical analyses and no model call:

1. **Search accounting** over ``plans.jsonl``, ``plan_traces.jsonl``, ``transitions.jsonl``
   and ``hypotheses.jsonl``: outcomes, stop reasons, node and depth usage, the largest
   ``levels_completed`` any prediction carried, and whether the real history ever showed a
   level transition (candidates a and b).
2. **Static program analysis** (``ast``) of every certified program under ``world_models/``:
   how each ``predict`` sets ``levels_completed`` in the observation it returns - copied from
   an input history record, a literal, or computed (candidates c and d).
3. **Dynamic probe** in the real sandbox: every program is asked to predict every planner
   candidate action (the available ids fanned out over the config's click lattice, plus RESET)
   from the run's last recorded observation twice, once as recorded and once with the last
   record's ``levels_completed`` raised to a sentinel value. A program whose predictions never
   exceed the largest ``levels_completed`` present in its input can never satisfy the planner's
   goal ``predicted.levels_completed >= start + 1`` at any depth, because every BFS node
   inherits the start history's values by induction.

Optionally (``--deep-search``) re-runs :func:`ref_planner.plan_to_next_level` offline over one
certified program with a larger depth and node cap, to show that a deeper search changes
nothing where the reachable set is small.

The reset observation is not stored raw in ``transitions.jsonl`` (only its digests are), so the
probe history is built with the first recorded post-action observation as ``history[0]``; the
probe reads only the last observation and the level fields, so this substitution is recorded
and harmless for what is measured.

Usage::

    uv run python scripts/g36b_plan_diagnosis.py --out /tmp/g36b_plan_diagnosis.json \\
        artifacts/E300_ref/<run> [...] artifacts/E301_ref/<run> [...] \\
        [--deep-search artifacts/E301_ref/<run>:h005:24:200000:51]

Every number in the report cites the sha256 of the file it was read from (C4).
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arc_plasticity.agents.ref_world_model import click_points_for_step
from arc_plasticity.core.guards import Deadline
from arc_plasticity.environments.arc_interface import ActionRecord
from arc_plasticity.hypotheses.interface import (
    History,
    Observation,
    Transition,
    WorldModelError,
)
from arc_plasticity.hypotheses.sandbox import (
    SandboxedProgram,
    SandboxLimits,
    default_guards,
)
from arc_plasticity.planning import ref_planner as rp

LEVEL_KEY = "levels_completed"
SENTINEL_LEVELS = 3
RECORD_NAMES = ("history", "last", "prev", "first", "base", "last_rec", "rec", "obs", "record")


# ----------------------------------------------------------------------------- helpers


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


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter = Counter(json.dumps(row.get(key), sort_keys=True) for row in rows)
    return {label: count for label, count in sorted(counter.items())}


def numeric(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
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


# ----------------------------------------------------------------------------- 1. accounting


def search_accounting(run_dir: Path) -> dict[str, Any]:
    plans = read_jsonl(run_dir / "plans.jsonl")
    transitions = read_jsonl(run_dir / "transitions.jsonl")
    hypotheses = read_jsonl(run_dir / "hypotheses.jsonl")
    levels_seen = Counter(int(row[LEVEL_KEY]) for row in transitions)
    dropped = [row.get("successors_dropped_at_depth_cap") for row in plans]
    out: dict[str, Any] = {
        "plans_jsonl_sha256": sha256_of(run_dir / "plans.jsonl"),
        "transitions_jsonl_sha256": sha256_of(run_dir / "transitions.jsonl"),
        "hypotheses_jsonl_sha256": sha256_of(run_dir / "hypotheses.jsonl"),
        "searches": len(plans),
        "outcome": count_by(plans, "outcome"),
        "reason": count_by(plans, "reason"),
        "queue_exhausted": count_by(plans, "queue_exhausted"),
        "target_levels_completed": count_by(plans, "target_levels_completed"),
        "predicted_levels_completed_max": count_by(plans, "predicted_levels_completed_max"),
        "nodes_expanded": numeric(plans, "nodes_expanded"),
        "steps_simulated": numeric(plans, "steps_simulated"),
        "distinct_states": numeric(plans, "distinct_states"),
        "max_depth_reached": count_by(plans, "max_depth_reached"),
        "successors_dropped_at_depth_cap": numeric(plans, "successors_dropped_at_depth_cap"),
        "searches_with_states_dropped_at_depth_cap": (
            sum(1 for v in dropped if v) if any(v is not None for v in dropped) else None
        ),
        "transitions": len(transitions),
        "transition_levels_completed_counts": {str(k): v for k, v in sorted(levels_seen.items())},
        "transition_states": count_by(transitions, "state"),
        "win_levels": count_by(transitions, "win_levels"),
        "hypotheses_events": count_by(hypotheses, "event"),
        "hypotheses_certified": sum(
            1 for h in hypotheses if h.get("event") == "proposed" and h.get("certified")
        ),
        "decertify_reasons": count_by(
            [h for h in hypotheses if h.get("event") == "decertified"], "reason"
        ),
    }
    traces_path = run_dir / "plan_traces.jsonl"
    if traces_path.is_file():
        traces = read_jsonl(traces_path)
        out["plan_traces"] = {
            "sha256": sha256_of(traces_path),
            "records": len(traces),
            "found": count_by(traces, "found"),
            "levels_completed": count_by(traces, LEVEL_KEY),
            "depth": count_by(traces, "depth"),
        }
    else:
        out["plan_traces"] = None
    results_path = run_dir / "results.json"
    with results_path.open("r", encoding="utf-8") as handle:
        results = json.load(handle)
    inner = results.get("results", results)
    out["results_json_sha256"] = sha256_of(results_path)
    out["results"] = {
        key: inner.get(key)
        for key in (
            "game_id",
            "stop_reason",
            "levels_completed",
            "win_levels",
            "model_calls",
            "hypotheses_proposed",
            "hypotheses_certified",
            "plans_searched",
            "plans_executed",
            "plan_actions",
            "exploration_actions",
            "actions_total",
            "planner",
        )
    }
    return out


# ----------------------------------------------------------------------------- 2. static


def _is_record_read(node: ast.AST) -> bool:
    """``x["levels_completed"]`` or ``x.get("levels_completed", ...)`` for any ``x``."""
    if isinstance(node, ast.Subscript):
        return isinstance(node.slice, ast.Constant) and node.slice.value == LEVEL_KEY
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return (
            node.func.attr == "get"
            and bool(node.args)
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == LEVEL_KEY
        )
    return False


def _classify_value(node: ast.AST, assignments: dict[str, list[ast.AST]]) -> str:
    if isinstance(node, ast.Constant):
        return f"literal:{node.value!r}"
    if _is_record_read(node):
        return "copied_from_input_record"
    if isinstance(node, ast.Name):
        sources = assignments.get(node.id)
        if not sources:
            return f"name_unresolved:{node.id}"
        kinds = {_classify_value(src, assignments) for src in sources}
        if len(kinds) == 1:
            return f"via_name:{kinds.pop()}"
        return "via_name:mixed:" + "|".join(sorted(kinds))
    return f"computed:{type(node).__name__}"


def analyse_program(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    assignments: dict[str, list[ast.AST]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments.setdefault(target.id, []).append(node.value)
    returned: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == LEVEL_KEY:
                    returned.append(
                        {"line": value.lineno, "kind": _classify_value(value, assignments)}
                    )
    # Any other write to the key (subscript assignment, augmented assignment) or arithmetic
    # on a value read from it would be a computed level; record them so nothing hides.
    other_writes: list[int] = []
    arithmetic: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign | ast.AugAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Subscript) and _is_record_read(target):
                    other_writes.append(node.lineno)
        if isinstance(node, ast.BinOp) and (
            _is_record_read(node.left) or _is_record_read(node.right)
        ):
            arithmetic.append(node.lineno)
    kinds = sorted({r["kind"] for r in returned})
    mentions_win = "WIN" in source
    return {
        "file": str(path.relative_to(PROJECT_ROOT))
        if path.is_relative_to(PROJECT_ROOT)
        else str(path),
        "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "bytes": len(source.encode("utf-8")),
        "returned_levels_completed": returned,
        "kinds": kinds,
        "other_writes_to_key": other_writes,
        "arithmetic_on_key": arithmetic,
        "mentions_WIN_state": mentions_win,
        "occurrences_of_key": source.count(LEVEL_KEY),
        "never_computes_levels": all(
            k.startswith(
                ("copied_from_input_record", "literal:", "via_name:copied", "via_name:literal")
            )
            for k in kinds
        )
        and not other_writes
        and not arithmetic
        and bool(kinds),
    }


# ----------------------------------------------------------------------------- 3. dynamic


def _observation_from_transition(row: dict[str, Any]) -> Observation:
    return Observation(
        frame=tuple(tuple(tuple(int(c) for c in line) for line in grid) for grid in row["frame"]),
        state=str(row["state"]),
        levels_completed=int(row[LEVEL_KEY]),
        available_actions=tuple(int(a) for a in row["available_actions"]),
    )


def probe_history(run_dir: Path) -> tuple[History, dict[str, Any]]:
    rows = read_jsonl(run_dir / "transitions.jsonl")
    initial = _observation_from_transition(rows[0])
    transitions = tuple(
        Transition(
            ActionRecord(
                int(row["action"]), {k: int(v) for k, v in (row.get("data") or {}).items()}
            ),
            _observation_from_transition(row),
        )
        for row in rows[1:]
    )
    note = {
        "history_0": "first recorded post-action observation (reset frame is not stored raw)",
        "transitions_used": len(transitions),
        "last_state": rows[-1]["state"],
        "last_levels_completed": int(rows[-1][LEVEL_KEY]),
        "last_available_actions": rows[-1]["available_actions"],
    }
    return History(initial, transitions), note


def with_last_levels(history: History, levels: int) -> History:
    last = history.transitions[-1]
    replaced = Transition(
        last.action, dataclasses.replace(last.observation, levels_completed=levels)
    )
    return History(history.initial, history.transitions[:-1] + (replaced,))


def probe_program(
    path: Path,
    history: History,
    limits: SandboxLimits,
    click_points: tuple[tuple[int, int], ...],
) -> dict[str, Any]:
    last = history.last_observation()
    actions = rp.candidate_actions(last.available_actions, click_points)
    if all(a.action != rp.RESET_ACTION_ID for a in actions):
        actions.append(ActionRecord(rp.RESET_ACTION_ID))
    probes: dict[str, Any] = {}
    for label, hist in (
        ("as_recorded", history),
        (f"last_levels_{SENTINEL_LEVELS}", with_last_levels(history, SENTINEL_LEVELS)),
    ):
        input_levels = {history.initial.levels_completed} | {
            t.observation.levels_completed for t in hist.transitions
        }
        input_max = max(input_levels)
        predicted: Counter[int] = Counter()
        states: Counter[str] = Counter()
        violations: list[str] = []
        started = time.monotonic()
        program = SandboxedProgram(path, limits, default_guards(PROJECT_ROOT))
        try:
            program.start()
            for action in actions:
                try:
                    obs = program.predict(hist, action)
                except WorldModelError as exc:
                    violations.append(f"{action.action}:{type(exc).__name__}: {exc}"[:200])
                    break
                predicted[obs.levels_completed] += 1
                states[obs.state] += 1
        except WorldModelError as exc:
            violations.append(f"start: {type(exc).__name__}: {exc}"[:200])
        finally:
            program.close()
        probes[label] = {
            "actions_probed": len(actions),
            "predictions": sum(predicted.values()),
            "input_levels_completed_values": sorted(input_levels),
            "predicted_levels_completed_counts": {str(k): v for k, v in sorted(predicted.items())},
            "predicted_states": dict(sorted(states.items())),
            "predicted_max_minus_input_max": (max(predicted) - input_max) if predicted else None,
            "violations": violations,
            "seconds": round(time.monotonic() - started, 2),
        }
    exceeds = [
        p["predicted_max_minus_input_max"]
        for p in probes.values()
        if p["predicted_max_minus_input_max"] is not None
    ]
    copies_sentinel = (
        str(SENTINEL_LEVELS)
        in probes[f"last_levels_{SENTINEL_LEVELS}"]["predicted_levels_completed_counts"]
    )
    return {
        "probes": probes,
        "ever_exceeds_input_levels": any(v > 0 for v in exceeds) if exceeds else None,
        "copies_last_levels": copies_sentinel,
    }


# ----------------------------------------------------------------------------- deep search


def deep_search(
    run_dir: Path,
    hypothesis_id: str,
    max_depth: int,
    max_nodes: int,
    click_points: tuple[tuple[int, int], ...],
    limits: SandboxLimits,
    steps_max: int,
    seconds_max: float,
    prefix: int | None = None,
) -> dict[str, Any]:
    history, note = probe_history(run_dir)
    if prefix is not None:
        history = history.prefix(prefix)
        note = {**note, "prefix_transitions": prefix}
    path = run_dir / "world_models" / f"{hypothesis_id}.py"
    budget = rp.SimulationBudget(steps_max)
    program = SandboxedProgram(path, limits, default_guards(PROJECT_ROOT))
    started = time.monotonic()
    with program:
        plan = rp.plan_to_next_level(
            program,
            history,
            hypothesis_id=hypothesis_id,
            certification_history_length=len(history),
            budget=budget,
            limits=rp.PlannerLimits(
                max_depth=max_depth, max_nodes=max_nodes, click_points=click_points
            ),
            deadline=Deadline(seconds_max),
        )
    record = plan.to_dict()
    record.pop("actions", None)
    record["found_actions"] = len(plan.actions)
    return {
        "run_dir": str(run_dir),
        "program": str(path.relative_to(PROJECT_ROOT)),
        "program_sha256": sha256_of(path),
        "history_note": note,
        "limits": {
            "max_depth": max_depth,
            "max_nodes": max_nodes,
            "steps_max": steps_max,
            "seconds_max": seconds_max,
        },
        "seconds": round(time.monotonic() - started, 1),
        "plan": record,
    }


# ----------------------------------------------------------------------------- main


def diagnose_run(
    run_dir: Path, limits: SandboxLimits, click_points: tuple[tuple[int, int], ...], probe: bool
) -> dict[str, Any]:
    programs = sorted((run_dir / "world_models").glob("h*.py"))
    certified_ids = {
        h["hypothesis_id"]
        for h in read_jsonl(run_dir / "hypotheses.jsonl")
        if h.get("event") == "proposed" and h.get("certified")
    }
    static = [{**analyse_program(p), "certified": p.stem in certified_ids} for p in programs]
    report: dict[str, Any] = {
        "run_dir": str(run_dir),
        "accounting": search_accounting(run_dir),
        "programs": len(programs),
        "static": static,
        "static_summary": {
            "kinds": dict(Counter(k for s in static for k in s["kinds"])),
            "never_computes_levels": sum(1 for s in static if s["never_computes_levels"]),
            "certified": sum(1 for s in static if s["certified"]),
            "certified_never_computing_levels": sum(
                1 for s in static if s["certified"] and s["never_computes_levels"]
            ),
            "other_writes_or_arithmetic": sum(
                1 for s in static if s["other_writes_to_key"] or s["arithmetic_on_key"]
            ),
            "mentions_WIN_state": sum(1 for s in static if s["mentions_WIN_state"]),
        },
    }
    if probe:
        history, note = probe_history(run_dir)
        report["probe_history"] = note
        dynamic = {}
        for path in programs:
            dynamic[path.stem] = probe_program(path, history, limits, click_points)
        report["dynamic"] = dynamic
        report["dynamic_summary"] = {
            "programs_probed": len(dynamic),
            "programs_ever_exceeding_input_levels": sum(
                1 for d in dynamic.values() if d["ever_exceeds_input_levels"]
            ),
            "programs_copying_last_levels": sum(
                1 for d in dynamic.values() if d["copies_last_levels"]
            ),
            "programs_with_violations": sum(
                1 for d in dynamic.values() if any(p["violations"] for p in d["probes"].values())
            ),
            "predictions_total": sum(
                p["predictions"] for d in dynamic.values() for p in d["probes"].values()
            ),
        }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dirs", nargs="+", type=lambda s: Path(s).resolve())
    parser.add_argument("--out", type=Path, required=True, help="JSON report path")
    parser.add_argument("--click-grid-step", type=int, default=16)
    parser.add_argument("--predict-seconds-max", type=float, default=5.0)
    parser.add_argument("--no-probe", action="store_true", help="skip the sandbox probe")
    parser.add_argument(
        "--deep-search",
        action="append",
        default=[],
        metavar="RUN_DIR:HYP:DEPTH:NODES[:PREFIX]",
        help="offline plan_to_next_level over one certified program with larger limits",
    )
    parser.add_argument("--deep-steps-max", type=int, default=500_000)
    parser.add_argument("--deep-seconds-max", type=float, default=300.0)
    args = parser.parse_args(argv)

    limits = SandboxLimits(
        backtest_seconds_max=120.0,
        predict_seconds_max=args.predict_seconds_max,
        address_space_bytes_max=2 * 1024**3,
    )
    click_points = click_points_for_step(args.click_grid_step)
    report: dict[str, Any] = {
        "script": str(Path(__file__).resolve().relative_to(PROJECT_ROOT)),
        "script_sha256": sha256_of(Path(__file__).resolve()),
        "ref_planner_sha256": sha256_of(
            PROJECT_ROOT / "src/arc_plasticity/planning/ref_planner.py"
        ),
        "click_grid_step": args.click_grid_step,
        "click_points": len(click_points),
        "sentinel_levels": SENTINEL_LEVELS,
        "runs": [
            diagnose_run(run_dir, limits, click_points, probe=not args.no_probe)
            for run_dir in args.run_dirs
        ],
    }
    all_static = [s for r in report["runs"] for s in r["static"]]
    totals: dict[str, Any] = {
        "runs": len(report["runs"]),
        "searches": sum(r["accounting"]["searches"] for r in report["runs"]),
        "outcomes": dict(
            sum(
                (Counter(r["accounting"]["outcome"]) for r in report["runs"]),
                Counter(),
            )
        ),
        "predicted_levels_completed_max": dict(
            sum(
                (
                    Counter(r["accounting"]["predicted_levels_completed_max"])
                    for r in report["runs"]
                ),
                Counter(),
            )
        ),
        "transitions": sum(r["accounting"]["transitions"] for r in report["runs"]),
        "transition_levels_completed_counts": dict(
            sum(
                (
                    Counter(r["accounting"]["transition_levels_completed_counts"])
                    for r in report["runs"]
                ),
                Counter(),
            )
        ),
        "programs": len(all_static),
        "program_kinds": dict(Counter(k for s in all_static for k in s["kinds"])),
        "programs_never_computing_levels": sum(1 for s in all_static if s["never_computes_levels"]),
        "programs_certified": sum(1 for s in all_static if s["certified"]),
        "certified_programs_never_computing_levels": sum(
            1 for s in all_static if s["certified"] and s["never_computes_levels"]
        ),
        "programs_mentioning_WIN": sum(1 for s in all_static if s["mentions_WIN_state"]),
    }
    if not args.no_probe:
        totals["dynamic"] = {
            key: sum(r["dynamic_summary"][key] for r in report["runs"])
            for key in (
                "programs_probed",
                "programs_ever_exceeding_input_levels",
                "programs_copying_last_levels",
                "programs_with_violations",
                "predictions_total",
            )
        }
    report["totals"] = totals
    report["deep_search"] = []
    for spec in args.deep_search:
        parts = spec.split(":")
        if len(parts) not in (4, 5):
            raise SystemExit(
                f"--deep-search expects RUN_DIR:HYP:DEPTH:NODES[:PREFIX], got {spec!r}"
            )
        run_dir_s, hyp, depth_s, nodes_s = parts[:4]
        prefix = int(parts[4]) if len(parts) == 5 else None
        report["deep_search"].append(
            deep_search(
                Path(run_dir_s).resolve(),
                hyp,
                int(depth_s),
                int(nodes_s),
                click_points,
                limits,
                args.deep_steps_max,
                args.deep_seconds_max,
                prefix,
            )
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"out": str(args.out), "out_sha256": sha256_of(args.out), "totals": totals}, indent=1
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
