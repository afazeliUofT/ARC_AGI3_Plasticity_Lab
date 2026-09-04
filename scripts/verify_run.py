#!/usr/bin/env python3
"""Gate verifier. Evaluates the script-evaluable exit predicates of a gate.

Authored under AGENT_CONSTITUTION.md section 7 (C2). Design rules that make an editable
verifier safe:

* **Every numeric threshold is read from ``preregistration/<gate>.yaml``.** This module
  contains no gate threshold literal. If the pre-registration lacks a threshold the check
  needs, the verifier raises ``PreregistrationError`` instead of substituting a default.
* The verifier prints the SHA-256 of the pre-registration it read, so a referee can cite it.
* Every check returns an observed value next to the threshold it was compared with, so the
  referee can re-derive each verdict line from the report alone.

Usage::

    uv run python scripts/verify_run.py --gate G0 [--artifacts-root DIR] [--skip-tooling]
                                         [--report PATH]

Exit status is 0 only if every check passed. ``--skip-tooling`` skips the checks that shell
out to ``uv sync``, ``pytest``, ``ruff`` and ``mypy``; it exists so the verifier can be run
from inside pytest without recursion. The report always states which checks were skipped.

Conventions this verifier defines (so that producers can be written against them):

* A run directory under ``artifacts/<experiment_id>/<run_id>/`` must contain every file in
  ``REQUIRED_RUN_FILES`` and its ``manifest.json`` must carry every key in
  ``REQUIRED_MANIFEST_KEYS`` (constitution section 11). ``manifest.json["seed"]`` is the seed
  used to group runs for the determinism check; ``manifest.json["completion_status"]`` must
  equal ``"completed"`` for a run to count.
* ``SHA256SUMS`` uses the ``sha256sum`` text format, one ``<hex>  <relative path>`` per line,
  relative to the run directory, and does not list itself.
* A ``[VERIFY-ON-MACHINE]`` item in ``docs/EVIDENCE_TOOLING.md`` section 11 counts as resolved
  when the text of that numbered item contains ``Resolved YYYY-MM-DD`` or
  ``Not observable YYYY-MM-DD`` (case-insensitive, optional colon). Anything else, including
  a hypothesis, is unresolved.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_RUN_FILES: tuple[str, ...] = (
    "manifest.json",
    "resolved_config.yaml",
    "results.json",
    "metrics.csv",
    "environment_results.csv",
    "transitions.jsonl",
    "hypotheses.jsonl",
    "memory_operations.jsonl",
    "stdout.log",
    "stderr.log",
    "git_state.txt",
    "environment_info.json",
    "SHA256SUMS",
)

REQUIRED_MANIFEST_KEYS: tuple[str, ...] = (
    "experiment_id",
    "run_id",
    "timestamp_utc",
    "git_commit",
    "git_dirty",
    "python_version",
    "dependency_lock_hash",
    "config_hash",
    "environment_generator_version",
    "seed",
    "model_identifier",
    "prompt_hash",
    "action_budget",
    "simulation_budget",
    "token_budget",
    "persistent_state_size_cap",
    "hardware",
    "wallclock_limit_seconds",
    "completion_status",
)

COMPLETED_STATUS = "completed"

RESOLVED_RE = re.compile(r"\b(resolved|not observable)\b:?\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


class PreregistrationError(RuntimeError):
    """The pre-registration is missing something the verifier needs. Never defaulted."""


@dataclass
class CheckResult:
    name: str
    passed: bool
    observed: Any
    threshold: Any
    detail: str = ""
    skipped: bool = False
    evidence: list[str] = field(default_factory=list)


@dataclass
class Report:
    gate: str
    preregistration_path: str
    preregistration_sha256: str
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks if not c.skipped)

    @property
    def skipped(self) -> list[str]:
        return [c.name for c in self.checks if c.skipped]

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "preregistration_path": self.preregistration_path,
            "preregistration_sha256": self.preregistration_sha256,
            "passed": self.passed,
            "skipped": self.skipped,
            "checks": [asdict(c) for c in self.checks],
        }


# --------------------------------------------------------------------------- helpers


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_preregistration(gate: str, root: Path = ROOT) -> tuple[dict[str, Any], Path, str]:
    path = root / "preregistration" / f"{gate}.yaml"
    if not path.exists():
        raise PreregistrationError(f"{path} does not exist; C1 requires it before verification")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise PreregistrationError(f"{path} is not a mapping")
    if data.get("gate") != gate:
        raise PreregistrationError(f"{path} declares gate {data.get('gate')!r}, expected {gate!r}")
    if "thresholds" not in data or not isinstance(data["thresholds"], dict):
        raise PreregistrationError(f"{path} has no 'thresholds' mapping")
    return data, path, sha256_file(path)


def threshold(prereg: dict[str, Any], key: str) -> Any:
    """Fetch a threshold. Raises rather than defaulting: the code never owns a number."""
    try:
        return prereg["thresholds"][key]
    except KeyError as exc:
        raise PreregistrationError(f"pre-registration lacks thresholds.{key}") from exc


def section(prereg: dict[str, Any], key: str) -> dict[str, Any]:
    value = prereg.get(key)
    if not isinstance(value, dict):
        raise PreregistrationError(f"pre-registration lacks mapping {key!r}")
    return value


def strip_keys(obj: Any, excluded: frozenset[str]) -> Any:
    """Remove every key named in ``excluded`` at any nesting depth."""
    if isinstance(obj, dict):
        return {k: strip_keys(v, excluded) for k, v in obj.items() if k not in excluded}
    if isinstance(obj, list):
        return [strip_keys(v, excluded) for v in obj]
    return obj


def canonical_json_bytes(path: Path, excluded: frozenset[str]) -> bytes:
    data = json.loads(path.read_text())
    return json.dumps(strip_keys(data, excluded), sort_keys=True, separators=(",", ":")).encode()


def canonical_csv_rows(path: Path, excluded: frozenset[str]) -> list[list[str]]:
    with path.open(newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return rows
    header = rows[0]
    keep = [i for i, name in enumerate(header) if name not in excluded]
    return [[row[i] for i in keep if i < len(row)] for row in rows]


def _snake(text: str) -> str:
    return re.sub(r"[\s\-]+", "_", text.strip().lower())


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


# --------------------------------------------------------------------------- checks


def check_nondeterministic_fields(
    prereg: dict[str, Any], root: Path = ROOT
) -> tuple[CheckResult, frozenset[str]]:
    """The exclusion list must stay inside the pre-registered category bounds.

    Returns the check and the resolved set of excluded names for the determinism check.
    """
    proto = section(prereg, "determinism_protocol")
    src = proto.get("excluded_fields_source")
    if not src:
        raise PreregistrationError("determinism_protocol.excluded_fields_source missing")
    allowed_cats = [str(c) for c in proto.get("excluded_field_categories_allowed", [])]
    forbidden_cats = [str(c) for c in proto.get("excluded_field_categories_forbidden", [])]
    if not allowed_cats or not forbidden_cats:
        raise PreregistrationError("determinism_protocol category bounds missing")

    path = root / src
    problems: list[str] = []
    names: set[str] = set()
    if not path.exists():
        return (
            CheckResult(
                "nondeterministic_fields_within_bounds",
                False,
                observed=f"{src} missing",
                threshold="present and within category bounds",
                evidence=[src],
            ),
            frozenset(),
        )
    cfg = yaml.safe_load(path.read_text()) or {}
    excluded = cfg.get("excluded_fields")
    if not isinstance(excluded, dict):
        problems.append("excluded_fields is not a mapping of category -> names")
        excluded = {}

    # Forbidden names derived mechanically from the pre-registration's forbidden categories.
    forbidden_names: set[str] = set()
    for cat in forbidden_cats:
        for token in cat.split(","):
            forbidden_names.add(_snake(token))
    for name in cfg.get("never_excluded", []) or []:
        forbidden_names.add(_snake(str(name)))

    allowed_word_sets = [_words(c.split("(")[0]) for c in allowed_cats]
    for category, entries in excluded.items():
        cat_words = _words(str(category).replace("_", " "))
        if not any(cat_words <= aw for aw in allowed_word_sets):
            problems.append(f"category {category!r} is not one of the pre-registered categories")
        for entry in entries or []:
            name = str(entry)
            if _snake(name) in forbidden_names:
                problems.append(f"{name!r} in category {category!r} is a forbidden exclusion")
            names.add(name)

    compared = cfg.get("compared_files")
    if compared != ["results.json", "metrics.csv"]:
        problems.append(f"compared_files is {compared!r}, expected results.json and metrics.csv")

    return (
        CheckResult(
            "nondeterministic_fields_within_bounds",
            passed=not problems,
            observed={"excluded_names": sorted(names), "problems": problems},
            threshold={"allowed_categories": allowed_cats, "forbidden": sorted(forbidden_names)},
            evidence=[src, "preregistration"],
        ),
        frozenset(names),
    )


def _run_dirs(artifacts_root: Path) -> list[Path]:
    if not artifacts_root.exists():
        return []
    return sorted(p for p in artifacts_root.iterdir() if p.is_dir())


def _load_manifest(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "manifest.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return data if isinstance(data, dict) else None


def check_run_completeness(artifacts_root: Path) -> CheckResult:
    """Every run has every contract file and every manifest key (constitution section 11)."""
    problems: list[str] = []
    runs = _run_dirs(artifacts_root)
    for run in runs:
        for name in REQUIRED_RUN_FILES:
            if not (run / name).exists():
                problems.append(f"{run.name}: missing {name}")
        manifest = _load_manifest(run)
        if manifest is None:
            problems.append(f"{run.name}: manifest.json missing or not a mapping")
            continue
        for key in REQUIRED_MANIFEST_KEYS:
            if key not in manifest:
                problems.append(f"{run.name}: manifest lacks {key}")
    return CheckResult(
        "run_artifact_completeness",
        passed=bool(runs) and not problems,
        observed={"runs": len(runs), "problems": problems},
        threshold={"files": list(REQUIRED_RUN_FILES), "manifest_keys": list(REQUIRED_MANIFEST_KEYS)},
        evidence=[str(r.relative_to(ROOT)) if r.is_relative_to(ROOT) else str(r) for r in runs],
    )


def check_sha256sums(prereg: dict[str, Any], artifacts_root: Path) -> CheckResult:
    frac_min = float(threshold(prereg, "sha256sums_verified_fraction_min"))
    must_list_all = bool(threshold(prereg, "sha256sums_must_list_every_artifact_file"))
    total = verified = 0
    problems: list[str] = []
    runs = _run_dirs(artifacts_root)
    for run in runs:
        sums = run / "SHA256SUMS"
        if not sums.exists():
            problems.append(f"{run.name}: SHA256SUMS missing")
            continue
        listed: dict[str, str] = {}
        for lineno, line in enumerate(sums.read_text().splitlines(), 1):
            if not line.strip():
                continue
            m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$", line)
            if not m:
                problems.append(f"{run.name}: SHA256SUMS line {lineno} malformed")
                continue
            listed[m.group(2).strip()] = m.group(1).lower()
        for rel, digest in listed.items():
            total += 1
            target = run / rel
            if not target.exists():
                problems.append(f"{run.name}: listed file {rel} does not exist")
                continue
            if sha256_file(target) == digest:
                verified += 1
            else:
                problems.append(f"{run.name}: hash mismatch for {rel}")
        if must_list_all:
            present = {
                str(p.relative_to(run)) for p in run.rglob("*") if p.is_file() and p != sums
            }
            unlisted = sorted(present - set(listed))
            if unlisted:
                problems.append(f"{run.name}: unlisted files {unlisted}")
    fraction = (verified / total) if total else 0.0
    return CheckResult(
        "sha256sums_verify",
        passed=bool(runs) and fraction >= frac_min and not problems,
        observed={"listed": total, "verified": verified, "fraction": fraction, "problems": problems},
        threshold={"fraction_min": frac_min, "must_list_every_file": must_list_all},
        evidence=[str(r / "SHA256SUMS") for r in runs],
    )


def check_determinism(
    prereg: dict[str, Any], artifacts_root: Path, excluded: frozenset[str]
) -> CheckResult:
    proto = section(prereg, "determinism_protocol")
    identity_min = float(threshold(prereg, "determinism_identity_min"))
    contrast_must_differ = bool(threshold(prereg, "contrast_seed_must_differ"))
    for key in ("fixed_seed", "identical_invocations", "contrast_seed", "contrast_invocations"):
        if key not in proto:
            raise PreregistrationError(f"determinism_protocol.{key} missing")
    fixed_seed = int(proto["fixed_seed"])
    n_identical = int(proto["identical_invocations"])
    contrast_seed = int(proto["contrast_seed"])
    n_contrast = int(proto["contrast_invocations"])

    by_seed: dict[int, list[Path]] = {}
    problems: list[str] = []
    for run in _run_dirs(artifacts_root):
        manifest = _load_manifest(run)
        if manifest is None or "seed" not in manifest:
            problems.append(f"{run.name}: no manifest seed; excluded from grouping")
            continue
        if manifest.get("completion_status") != COMPLETED_STATUS:
            problems.append(f"{run.name}: completion_status != {COMPLETED_STATUS!r}; excluded")
            continue
        by_seed.setdefault(int(manifest["seed"]), []).append(run)

    fixed_runs = by_seed.get(fixed_seed, [])
    contrast_runs = by_seed.get(contrast_seed, [])

    def signature(run: Path) -> tuple[bytes, list[list[str]]]:
        return (
            canonical_json_bytes(run / "results.json", excluded),
            canonical_csv_rows(run / "metrics.csv", excluded),
        )

    identity = 0.0
    contrast_differs = False
    if len(fixed_runs) < n_identical:
        problems.append(
            f"need {n_identical} completed runs at seed {fixed_seed}, found {len(fixed_runs)}"
        )
    else:
        try:
            ref = signature(fixed_runs[0])
            mismatches = [r.name for r in fixed_runs[1:] if signature(r) != ref]
            identity = 0.0 if mismatches else 1.0
            if mismatches:
                problems.append(f"same-seed runs differ from {fixed_runs[0].name}: {mismatches}")
            if contrast_must_differ:
                if len(contrast_runs) < n_contrast:
                    problems.append(
                        f"need {n_contrast} completed runs at contrast seed {contrast_seed}, "
                        f"found {len(contrast_runs)}"
                    )
                else:
                    same = [r.name for r in contrast_runs if signature(r) == ref]
                    contrast_differs = not same
                    if same:
                        problems.append(f"contrast-seed runs identical to fixed seed: {same}")
        except (OSError, ValueError) as exc:
            problems.append(f"could not read result files: {exc}")

    passed = identity >= identity_min and (contrast_differs or not contrast_must_differ)
    return CheckResult(
        "determinism_identity",
        passed=passed and not problems,
        observed={
            "identity": identity,
            "contrast_differs": contrast_differs,
            "fixed_seed_runs": [r.name for r in fixed_runs],
            "contrast_seed_runs": [r.name for r in contrast_runs],
            "excluded_fields": sorted(excluded),
            "problems": problems,
        },
        threshold={
            "identity_min": identity_min,
            "contrast_must_differ": contrast_must_differ,
            "fixed_seed": fixed_seed,
            "identical_invocations": n_identical,
            "contrast_seed": contrast_seed,
            "contrast_invocations": n_contrast,
        },
        evidence=[str(r / f) for r in fixed_runs + contrast_runs for f in ("results.json", "metrics.csv")],
    )


def check_git_clean(prereg: dict[str, Any], root: Path = ROOT) -> CheckResult:
    max_lines = int(threshold(prereg, "git_status_porcelain_lines_max"))
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return CheckResult(
        "git_status_clean",
        passed=proc.returncode == 0 and len(lines) <= max_lines,
        observed={"lines": len(lines), "sample": lines[:10], "exit": proc.returncode},
        threshold={"lines_max": max_lines},
    )


def check_licence(prereg: dict[str, Any], root: Path = ROOT) -> CheckResult:
    required = str(threshold(prereg, "licence_required_text"))
    path = root / "LICENSE"
    text = path.read_text() if path.exists() else ""
    return CheckResult(
        "licence_text",
        passed=required in text,
        observed=text.splitlines()[0] if text else "LICENSE missing",
        threshold=required,
        evidence=["LICENSE"],
    )


def parse_verify_on_machine(markdown: str) -> tuple[int, int, list[str]]:
    """Return (items_total, items_resolved, unresolved item headlines) for section 11."""
    m = re.search(r"^## 11\..*?$", markdown, re.MULTILINE)
    if not m:
        return 0, 0, ["section 11 heading not found"]
    body = markdown[m.end():]
    nxt = re.search(r"^## ", body, re.MULTILINE)
    if nxt:
        body = body[: nxt.start()]
    starts = [mm for mm in re.finditer(r"^(\d+)\.\s", body, re.MULTILINE)]
    total = resolved = 0
    unresolved: list[str] = []
    for i, mm in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(body)
        item = body[mm.start():end]
        total += 1
        if RESOLVED_RE.search(item):
            resolved += 1
        else:
            unresolved.append(item.splitlines()[0].strip())
    return total, resolved, unresolved


def check_verify_on_machine(prereg: dict[str, Any], root: Path = ROOT) -> CheckResult:
    total_expected = int(threshold(prereg, "verify_on_machine_items_total"))
    resolved_min = int(threshold(prereg, "verify_on_machine_items_resolved_min"))
    path = root / "docs" / "EVIDENCE_TOOLING.md"
    text = path.read_text() if path.exists() else ""
    total, resolved, unresolved = parse_verify_on_machine(text)
    return CheckResult(
        "verify_on_machine_resolved",
        passed=total == total_expected and resolved >= resolved_min,
        observed={"items_total": total, "items_resolved": resolved, "unresolved": unresolved},
        threshold={"items_total": total_expected, "items_resolved_min": resolved_min},
        evidence=["docs/EVIDENCE_TOOLING.md"],
    )


def _shell(cmd: list[str], root: Path, timeout: int = 1800) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=root, capture_output=True, text=True, check=False, timeout=timeout
        )
    except FileNotFoundError as exc:
        return 127, f"{cmd[0]} not found: {exc}"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    return proc.returncode, (proc.stdout + proc.stderr)[-4000:]


def check_tooling(prereg: dict[str, Any], root: Path = ROOT) -> list[CheckResult]:
    results: list[CheckResult] = []

    code, out = _shell(["uv", "sync", "--frozen"], root)
    results.append(
        CheckResult(
            "uv_sync_exit_code",
            passed=code == int(threshold(prereg, "uv_sync_exit_code")),
            observed=code,
            threshold=int(threshold(prereg, "uv_sync_exit_code")),
            detail=out[-500:],
        )
    )

    code, out = _shell(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"], root)
    m = re.search(r"(\d+) passed", out)
    collected = int(m.group(1)) if m else 0
    results.append(
        CheckResult(
            "pytest_exit_code",
            passed=code == int(threshold(prereg, "pytest_exit_code")),
            observed=code,
            threshold=int(threshold(prereg, "pytest_exit_code")),
            detail=out[-500:],
        )
    )
    results.append(
        CheckResult(
            "pytest_min_tests_collected",
            passed=collected >= int(threshold(prereg, "pytest_min_tests_collected")),
            observed=collected,
            threshold=int(threshold(prereg, "pytest_min_tests_collected")),
        )
    )

    code, out = _shell(["uv", "run", "ruff", "check", "."], root)
    results.append(
        CheckResult(
            "ruff_exit_code",
            passed=code == int(threshold(prereg, "ruff_exit_code")),
            observed=code,
            threshold=int(threshold(prereg, "ruff_exit_code")),
            detail=out[-500:],
        )
    )

    code, out = _shell(["uv", "run", "mypy"], root)
    results.append(
        CheckResult(
            "mypy_exit_code",
            passed=code == int(threshold(prereg, "mypy_exit_code")),
            observed=code,
            threshold=int(threshold(prereg, "mypy_exit_code")),
            detail=out[-500:],
        )
    )
    return results


# --------------------------------------------------------------------------- gates


def evaluate_g0(
    prereg: dict[str, Any], artifacts_root: Path, root: Path = ROOT, skip_tooling: bool = False
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    nd_check, excluded = check_nondeterministic_fields(prereg, root)
    checks.append(nd_check)
    checks.append(check_run_completeness(artifacts_root))
    checks.append(check_sha256sums(prereg, artifacts_root))
    checks.append(check_determinism(prereg, artifacts_root, excluded))
    checks.append(check_git_clean(prereg, root))
    checks.append(check_licence(prereg, root))
    checks.append(check_verify_on_machine(prereg, root))
    if skip_tooling:
        for name in (
            "uv_sync_exit_code",
            "pytest_exit_code",
            "pytest_min_tests_collected",
            "ruff_exit_code",
            "mypy_exit_code",
        ):
            checks.append(
                CheckResult(name, passed=False, observed=None, threshold=threshold(prereg, name),
                            skipped=True, detail="skipped by --skip-tooling")
            )
    else:
        checks.extend(check_tooling(prereg, root))
    return checks


GATE_EVALUATORS = {"G0": evaluate_g0}


def evaluate(
    gate: str, artifacts_root: Path | None = None, root: Path = ROOT, skip_tooling: bool = False
) -> Report:
    prereg, path, digest = load_preregistration(gate, root)
    if gate not in GATE_EVALUATORS:
        raise PreregistrationError(f"no evaluator implemented for gate {gate}")
    if artifacts_root is None:
        declared = section(prereg, "verification").get("artifacts_root")
        if not declared:
            raise PreregistrationError("verification.artifacts_root missing")
        artifacts_root = root / str(declared)
    checks = GATE_EVALUATORS[gate](prereg, artifacts_root, root, skip_tooling)
    return Report(gate, str(path.relative_to(root)), digest, checks)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gate", required=True)
    ap.add_argument("--artifacts-root", type=Path, default=None)
    ap.add_argument("--skip-tooling", action="store_true")
    ap.add_argument("--report", type=Path, default=None, help="also write the JSON report here")
    args = ap.parse_args(argv)

    try:
        report = evaluate(args.gate, args.artifacts_root, ROOT, args.skip_tooling)
    except PreregistrationError as exc:
        print(f"FAIL pre-registration: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(report.to_dict(), indent=2, default=str)
    print(payload)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload + "\n")
    verdict = "PASS" if report.passed and not report.skipped else "FAIL"
    if report.passed and report.skipped:
        verdict = "INCOMPLETE"
    print(
        f"{verdict} gate={report.gate} prereg_sha256={report.preregistration_sha256} "
        f"checks={sum(c.passed for c in report.checks)}/{len(report.checks)} "
        f"skipped={len(report.skipped)}",
        file=sys.stderr,
    )
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
