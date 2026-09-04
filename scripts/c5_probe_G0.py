"""C5 adversarial probe for Gate G0 (AGENT_CONSTITUTION.md section 7, control C5).

Before the referee is asked for a verdict, the builder must write the three strongest
arguments that the G0 pass is an artifact of something other than a working laboratory, and
test the strongest one. This script tests the two of them that are testable by machine and
writes a JSON report the referee can read alongside state/verify_G0.json.

Argument A (strongest, a flaw in the ruler): configs/nondeterministic_fields.yaml says
``matching: exact_name_any_depth`` and scripts/verify_run.py implements that with
``strip_keys``, which removes a matching key at any depth *together with its whole value*. A
result value nested under an excluded name (``{"hardware": {"steps": 12}}``) is therefore
invisible to the identity check, so a runner could hide nondeterminism there and still score
determinism_identity 1.0. Two tests:
  A1  demonstrate the hole synthetically (two files differing only inside a nested excluded
      key compare identical);
  A2  scan the three graded runs' results.json and metrics.csv for any excluded key whose
      value is a container or that sits below top level, i.e. whether the hole is exploited
      in the artifacts actually under verdict.

Argument B (git_dirty): every graded manifest records git_dirty true, so the artifacts do not
describe a committed tree exactly and the verifier's git_status_clean check runs on today's
tree, not the tree at run time. Test: re-run the smoke experiment at the fixed seed from the
current commit into a temporary root and compare its canonical signature with the committed
seed-12345 runs. Identity across commits and sessions is a stronger reproducibility claim
than the two same-session runs the gate required.

Argument C (untestable by machine, left for the referee): the verifier and the
pre-registration share an author, so a weak threshold chosen in good faith is not caught
mechanically. Candidates: pytest_min_tests_collected 1; a dated "Not observable" line counts
as a resolved VERIFY-ON-MACHINE item; the smoke experiment has no model call, so identity 1.0
says nothing about model-call nondeterminism, which G1 onward must handle separately.

Usage: uv run python scripts/c5_probe_G0.py [--report state/c5_probe_G0.json]
Exit 0 when the graded artifacts do not exploit the hole and cross-commit identity holds;
exit 1 otherwise. The synthetic hole (A1) is reported, not treated as a failure: it is a
property of the frozen verifier and can only be closed by escalation.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
E000 = ROOT / "configs" / "experiments" / "E000_bootstrap.yaml"
ARTIFACTS = ROOT / "artifacts" / "E000_bootstrap"


def _script(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(name)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def excluded_names() -> frozenset[str]:
    data = yaml.safe_load((ROOT / "configs" / "nondeterministic_fields.yaml").read_text())
    names: set[str] = set()
    for group in data["excluded_fields"].values():
        names.update(group)
    return frozenset(names)


def probe_a1(vr: ModuleType, excluded: frozenset[str]) -> dict[str, Any]:
    """Synthetic: nondeterminism hidden under an excluded key is invisible to the ruler."""
    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "a.json"
        b = Path(td) / "b.json"
        a.write_text(json.dumps({"results": {"steps": 12}, "hardware": {"steps": 12}}))
        b.write_text(json.dumps({"results": {"steps": 12}, "hardware": {"steps": 99}}))
        hidden_equal = vr.canonical_json_bytes(a, excluded) == vr.canonical_json_bytes(b, excluded)
        a.write_text(json.dumps({"results": {"steps": 12}}))
        b.write_text(json.dumps({"results": {"steps": 99}}))
        visible_equal = vr.canonical_json_bytes(a, excluded) == vr.canonical_json_bytes(b, excluded)
    return {
        "hole_exists": bool(hidden_equal and not visible_equal),
        "nested_result_under_excluded_key_compares_identical": hidden_equal,
        "top_level_result_difference_detected": not visible_equal,
    }


def _walk(obj: Any, path: str, excluded: frozenset[str], hits: list[dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}/{k}"
            if k in excluded:
                hits.append(
                    {
                        "path": here,
                        "depth": here.count("/"),
                        "value_is_container": isinstance(v, (dict, list)),
                        "value_type": type(v).__name__,
                    }
                )
            _walk(v, here, excluded, hits)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk(v, f"{path}[{i}]", excluded, hits)


def probe_a2(excluded: frozenset[str]) -> dict[str, Any]:
    """Graded artifacts: is any excluded key nested or container-valued?"""
    per_run: dict[str, Any] = {}
    exploited = False
    for run in sorted(p for p in ARTIFACTS.iterdir() if p.is_dir()):
        hits: list[dict[str, Any]] = []
        _walk(json.loads((run / "results.json").read_text()), "", excluded, hits)
        with (run / "metrics.csv").open(newline="") as fh:
            header = next(csv.reader(fh), [])
        csv_excluded = [h for h in header if h in excluded]
        suspicious = [h for h in hits if h["value_is_container"] or h["depth"] > 1]
        exploited = exploited or bool(suspicious)
        per_run[run.name] = {
            "results_json_excluded_keys": hits,
            "metrics_csv_excluded_columns": csv_excluded,
            "metrics_csv_header": header,
            "suspicious": suspicious,
        }
    return {"hole_exploited_in_graded_artifacts": exploited, "runs": per_run}


def probe_b(vr: ModuleType, excluded: frozenset[str], fixed_seed: int) -> dict[str, Any]:
    """Re-run at HEAD into a temp root; compare with the committed fixed-seed runs."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    committed = []
    for run in sorted(p for p in ARTIFACTS.iterdir() if p.is_dir()):
        manifest = json.loads((run / "manifest.json").read_text())
        if int(manifest["seed"]) == fixed_seed and manifest["completion_status"] == "completed":
            committed.append(run)
    if not committed:
        raise RuntimeError(f"no committed completed run at seed {fixed_seed}")

    def signature(run: Path) -> tuple[bytes, list[list[str]]]:
        return (
            vr.canonical_json_bytes(run / "results.json", excluded),
            vr.canonical_csv_rows(run / "metrics.csv", excluded),
        )

    with tempfile.TemporaryDirectory() as td:
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_experiment.py"),
                "--config",
                str(E000),
                "--seed",
                str(fixed_seed),
                "--artifacts-root",
                td,
                "--run-id",
                "c5_probe_rerun",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        fresh = Path(td) / "E000_bootstrap" / "c5_probe_rerun"
        fresh_manifest = json.loads((fresh / "manifest.json").read_text())
        fresh_sig = signature(fresh)
        comparisons = {
            run.name: {
                "manifest_git_commit": json.loads((run / "manifest.json").read_text())["git_commit"],
                "manifest_git_dirty": json.loads((run / "manifest.json").read_text())["git_dirty"],
                "identical_to_fresh": signature(run) == fresh_sig,
            }
            for run in committed
        }
    return {
        "rerun_exit_code": proc.returncode,
        "rerun_git_commit": head,
        "rerun_git_dirty_paths": porcelain,
        "rerun_manifest_git_commit": fresh_manifest["git_commit"],
        "rerun_manifest_git_dirty": fresh_manifest["git_dirty"],
        "rerun_completion_status": fresh_manifest["completion_status"],
        "committed_fixed_seed_runs": comparisons,
        "cross_commit_identity": proc.returncode == 0
        and all(c["identical_to_fresh"] for c in comparisons.values()),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path, default=ROOT / "state" / "c5_probe_G0.json")
    args = ap.parse_args(argv)

    vr = _script("verify_run")
    prereg = yaml.safe_load((ROOT / "preregistration" / "G0.yaml").read_text())
    excluded = excluded_names()
    fixed_seed = int(prereg["determinism_protocol"]["fixed_seed"])

    report: dict[str, Any] = {
        "gate": "G0",
        "probe": "C5 adversarial self-review",
        "verifier_sha256": vr.sha256_file(ROOT / "scripts" / "verify_run.py")
        if hasattr(vr, "sha256_file")
        else None,
        "excluded_names": sorted(excluded),
        "A1_synthetic_exclusion_hole": probe_a1(vr, excluded),
        "A2_graded_artifacts_scan": probe_a2(excluded),
        "B_cross_commit_rerun": probe_b(vr, excluded, fixed_seed),
    }
    ok = (
        not report["A2_graded_artifacts_scan"]["hole_exploited_in_graded_artifacts"]
        and report["B_cross_commit_rerun"]["cross_commit_identity"]
    )
    report["verdict_proposal"] = (
        "graded artifacts do not exploit the exclusion hole; cross-commit identity holds"
        if ok
        else "FAIL: see A2/B"
    )
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    a1 = report["A1_synthetic_exclusion_hole"]["hole_exists"]
    print(
        f"{'OK' if ok else 'FAIL'} gate=G0 A1_hole_exists={a1} "
        f"A2_exploited={report['A2_graded_artifacts_scan']['hole_exploited_in_graded_artifacts']} "
        f"B_cross_commit_identity={report['B_cross_commit_rerun']['cross_commit_identity']} "
        f"report={args.report}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
