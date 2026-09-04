#!/usr/bin/env python3
"""Build ``experiments/E300_ref_run_set.json`` (preregistration/G3.yaml experiment.run_set_manifest).

    uv run python scripts/build_e300_run_set.py [--artifacts-root artifacts/E300_ref]
                                                [--output experiments/E300_ref_run_set.json]
                                                [--print]

Lists EVERY directory under the E300 artifacts root with its run_id, stem, set_index, role
and SHA256SUMS digest. The rules, applied mechanically so no run can be chosen or dropped by
hand:

* ``stem`` is read from the run's own ``results.json`` (``results.stem``) or, for a run that
  failed before results existed, from ``resolved_config.yaml`` ``runner_params.game``.
* Runs of one stem are ordered by run_id (its UTC prefix). ``set_index`` of a run is one
  more than the number of *completed* runs of that stem that precede it, so the first
  completed run of every stem forms set 1, the second set 2, and a failed attempt belongs
  to the set that was in progress when it ran.
* ``role`` is ``failed`` if and only if ``completion_status`` is not ``completed`` (a
  completed run can never be labelled failed); otherwise ``preflight_graded`` for the three
  games named in the G3 pre-registration ``cost_preflight.games`` and ``graded`` for the rest.
* A set is ``complete`` when it holds exactly one non-failed run per stem for every stem in
  the cache manifest.

The verifier's ``run_set_manifest`` check (G3.8) recomputes all of this from the directories
and compares; this script only writes the file so it can be committed before the verifier
is invoked. Nothing here reads a threshold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from verify_run import load_preregistration, section

ROLE_PREFLIGHT = "preflight_graded"
ROLE_GRADED = "graded"
ROLE_FAILED = "failed"
COMPLETED = "completed"

DEFAULT_ARTIFACTS_ROOT = ROOT / "artifacts" / "E300_ref"
DEFAULT_OUTPUT = ROOT / "experiments" / "E300_ref_run_set.json"
CACHE_MANIFEST = ROOT / "experiments" / "environment_cache_manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def stems_from_cache_manifest(path: Path = CACHE_MANIFEST) -> list[str]:
    doc = _load_json(path) or {}
    return sorted(
        str(g["stem"]) for g in doc.get("games", []) if isinstance(g, dict) and "stem" in g
    )


def preflight_games(root: Path = ROOT) -> list[str]:
    prereg, _, _ = load_preregistration("G3", root)
    games = section(prereg, "cost_preflight").get("games")
    if not isinstance(games, list):
        raise SystemExit("G3 pre-registration cost_preflight.games missing")
    return [str(g) for g in games]


def describe_run(run_dir: Path) -> dict[str, Any]:
    """One run directory as the manifest lists it (before set_index and role are assigned)."""
    manifest = _load_json(run_dir / "manifest.json")
    results = _load_json(run_dir / "results.json")
    stem: str | None = None
    game_id: str | None = None
    if results is not None and isinstance(results.get("results"), dict):
        inner = results["results"]
        stem = inner.get("stem") if isinstance(inner.get("stem"), str) else None
        game_id = inner.get("game_id") if isinstance(inner.get("game_id"), str) else None
    if stem is None:
        resolved = run_dir / "resolved_config.yaml"
        if resolved.is_file():
            cfg = yaml.safe_load(resolved.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and isinstance(cfg.get("runner_params"), dict):
                raw = cfg["runner_params"].get("game")
                stem = raw if isinstance(raw, str) else None
    sums = run_dir / "SHA256SUMS"
    status = manifest.get("completion_status") if manifest else None
    return {
        "run_id": run_dir.name,
        "stem": stem,
        "game_id": game_id,
        "completion_status": status if isinstance(status, str) else None,
        "sealed": sums.is_file(),
        "sha256sums_sha256": _sha256(sums) if sums.is_file() else None,
        "git_commit": manifest.get("git_commit") if manifest else None,
        "git_dirty": manifest.get("git_dirty") if manifest else None,
        "stop_reason": (
            results["results"].get("stop_reason")
            if results and isinstance(results.get("results"), dict)
            else None
        ),
        "rhae_environment_score": (
            results["results"].get("rhae_environment_score")
            if results and isinstance(results.get("results"), dict)
            else None
        ),
    }


def assign_sets_and_roles(runs: list[dict[str, Any]], preflight: list[str]) -> None:
    """In place: ``set_index`` and ``role`` per the rules in the module docstring."""
    completed_before: dict[str, int] = {}
    for run in sorted(runs, key=lambda r: r["run_id"]):
        stem = run["stem"]
        key = stem if isinstance(stem, str) else "?"
        run["set_index"] = completed_before.get(key, 0) + 1
        completed = run["completion_status"] == COMPLETED and run["sealed"]
        if not completed:
            run["role"] = ROLE_FAILED
        else:
            run["role"] = ROLE_PREFLIGHT if stem in preflight else ROLE_GRADED
            completed_before[key] = completed_before.get(key, 0) + 1


def summarize_sets(runs: list[dict[str, Any]], stems_required: list[str]) -> dict[str, Any]:
    sets: dict[int, dict[str, Any]] = {}
    for run in runs:
        entry = sets.setdefault(int(run["set_index"]), {"graded_stems": [], "failed_run_ids": []})
        if run["role"] == ROLE_FAILED:
            entry["failed_run_ids"].append(run["run_id"])
        elif isinstance(run["stem"], str):
            entry["graded_stems"].append(run["stem"])
    out: dict[str, Any] = {}
    for index in sorted(sets):
        graded = sorted(sets[index]["graded_stems"])
        missing = sorted(set(stems_required) - set(graded))
        duplicates = sorted({s for s in graded if graded.count(s) > 1})
        out[str(index)] = {
            "graded_stems": graded,
            "graded_runs": len(graded),
            "missing_stems": missing,
            "duplicate_stems": duplicates,
            "failed_run_ids": sorted(sets[index]["failed_run_ids"]),
            "complete": not missing and not duplicates and len(graded) == len(stems_required),
        }
    return out


def build(
    artifacts_root: Path,
    *,
    stems_required: list[str],
    preflight: list[str],
    root: Path = ROOT,
) -> dict[str, Any]:
    run_dirs = (
        sorted(p for p in artifacts_root.iterdir() if p.is_dir()) if artifacts_root.is_dir() else []
    )
    runs = [describe_run(p) for p in run_dirs]
    assign_sets_and_roles(runs, preflight)
    runs.sort(key=lambda r: r["run_id"])
    rel = (
        str(artifacts_root.relative_to(root))
        if artifacts_root.is_relative_to(root)
        else str(artifacts_root)
    )
    return {
        "schema_version": 1,
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "experiment_id": "E300_ref",
        "artifacts_root": rel,
        "stems_required": list(stems_required),
        "preflight_games": list(preflight),
        "roles": [ROLE_PREFLIGHT, ROLE_GRADED, ROLE_FAILED],
        "rules": (
            "set_index = 1 + completed runs of the stem preceding this run (by run_id); "
            "role failed iff completion_status != completed or unsealed; a completed run is "
            "never labelled failed; preflight_graded for cost_preflight.games, graded otherwise"
        ),
        "runs_total": len(runs),
        "runs": runs,
        "sets": summarize_sets(runs, stems_required),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--artifacts-root", type=Path, default=DEFAULT_ARTIFACTS_ROOT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--print", action="store_true", help="print the manifest to stdout too")
    args = ap.parse_args(argv)
    doc = build(
        args.artifacts_root.resolve(),
        stems_required=stems_from_cache_manifest(),
        preflight=preflight_games(),
    )
    text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    if args.print:
        print(text, end="")
    complete = [i for i, s in doc["sets"].items() if s["complete"]]
    print(
        f"wrote {args.output} runs={doc['runs_total']} sets={list(doc['sets'])} "
        f"complete_sets={complete}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
