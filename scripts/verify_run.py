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

G1 conventions (``preregistration/G1.yaml`` ``replay_protocol``, ``cache_warming``,
``determinism_protocol``), which the E100 runner must produce and this verifier consumes:

* ``results.json["results"]`` (the runner's own mapping) carries ``operation_mode``,
  ``network_guard`` and ``games``: one record per attempted game with ``game_id``, ``seed``,
  ``steps_taken``, ``final_state``, ``levels_completed``, ``win_levels``, ``terminal``,
  ``final_frame_sha256`` and ``step_failed``.
* ``transitions.jsonl`` holds one record per action with ``game_index``, ``game_id``,
  ``step_index`` (1-based), ``action`` (0-7), ``data`` and ``frame_sha256``; replay groups by
  ``game_id`` and orders by ``step_index``.
* ``throughput.json["aggregate"]`` carries ``steps``, ``step_seconds`` and ``fps``; the
  verifier recomputes ``fps = steps / step_seconds`` and grades the recomputed value.
* ``experiments/environment_cache_manifest.json`` carries ``games``: one record per stem with
  ``stem``, ``game_id``, ``local_dir``, ``date_downloaded``, ``baseline_actions_count`` and
  ``files`` (``{relative path: sha256}``, paths relative to ``environments_dir``). Derived
  bytecode (``__pycache__``, ``*.pyc``) is never listed and never counted as drift.
* The canonical frame digest and the replay live in
  ``arc_plasticity.environments.arc_interface`` so runner and verifier share one definition.

G2 conventions (``preregistration/G2.yaml`` ``experiment``, ``human_baselines``,
``determinism_protocol``), which the E020 runner
(``arc_plasticity.evaluation.human_baseline_run``) produces and this verifier consumes:

* ``results.json["results"]`` carries every field of the pre-registration's
  ``results_json_contract`` (``G2_RESULTS_KEYS``); ``operation`` equals the runner's
  ``OPERATION`` constant, which the verifier also requires the contract text to name.
* ``human_baselines.json`` is the derived table: ``games[]`` each with ``game_id``, ``stem``
  and ``levels[]`` (``level``, ``official_baseline_actions``, ``derived_baseline_actions``,
  ``n_participants_with_completion``, ``per_participant_best_counts_sorted``,
  ``exact_agreement``, ``relative_difference``) plus ``totals``. Coverage is recomputed here
  as derived levels over the pre-registered ``public_levels_total``.
* ``input_manifest.json["raw_files"]`` maps every raw file read to its SHA-256 and must equal
  the committed dataset manifest's ``files`` digests.
* ``experiments/human_replays_manifest.json`` is the dataset manifest
  (``scripts/build_human_replays_manifest.py``); drift against ``data/human_replays/raw/`` is
  computed by ``human_replays.manifest_drift`` in both directions.
* The RHAE vectors run through ``rhae.score_vector_case`` and the derivation vectors through
  ``human_replays.derive_vector_case``, the same paths the unit tests use.
* The determinism check compares every file in ``determinism_protocol.compared_files`` across
  the fixed-seed runs and has no contrast group (``contrast_runs_required`` 0).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from arc_plasticity.core.guards import NetworkGuard
from arc_plasticity.environments import arc_interface
from arc_plasticity.evaluation import human_baseline_run, human_replays, rhae

G2_RESULTS_KEYS: tuple[str, ...] = (
    "dataset_manifest_sha256",
    "replay_units_ingested",
    "replay_parse_failures",
    "participant_ids_available",
    "session_order_source",
    "public_games_total",
    "public_levels_total_from_metadata",
    "derived_levels",
    "human_baseline_level_coverage",
    "exact_agreement_fraction",
    "median_abs_relative_difference",
    "network_guard",
    "operation",
)

G2_LEVEL_KEYS: tuple[str, ...] = (
    "level",
    "official_baseline_actions",
    "derived_baseline_actions",
    "n_participants_with_completion",
    "per_participant_best_counts_sorted",
    "exact_agreement",
    "relative_difference",
)

G2_INPUT_KEYS: tuple[str, ...] = (
    "raw_replays_dir",
    "dataset_manifest",
    "environments_dir",
    "cache_manifest",
)

G1_GAME_RECORD_KEYS: tuple[str, ...] = (
    "game_id",
    "seed",
    "steps_taken",
    "final_state",
    "levels_completed",
    "win_levels",
    "terminal",
    "final_frame_sha256",
    "step_failed",
)

G1_CACHE_GAME_KEYS: tuple[str, ...] = (
    "stem",
    "game_id",
    "local_dir",
    "date_downloaded",
    "baseline_actions_count",
    "files",
)

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
    prereg: dict[str, Any], root: Path = ROOT, bounds: dict[str, Any] | None = None
) -> tuple[CheckResult, frozenset[str]]:
    """The exclusion list must stay inside the pre-registered category bounds.

    ``bounds`` is the ``determinism_protocol`` mapping that supplies the category bounds; it
    defaults to the gate's own. A gate that pre-registers "the G0 exclusions" (G2) passes the
    G0 protocol here and records its digest. Returns the check and the resolved set of
    excluded names for the determinism check.
    """
    proto = section(prereg, "determinism_protocol")
    src = proto.get("excluded_fields_source")
    if not src:
        raise PreregistrationError("determinism_protocol.excluded_fields_source missing")
    bounds = proto if bounds is None else bounds
    allowed_cats = [str(c) for c in bounds.get("excluded_field_categories_allowed", [])]
    forbidden_cats = [str(c) for c in bounds.get("excluded_field_categories_forbidden", [])]
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


def check_run_completeness(
    artifacts_root: Path, extra_files: tuple[str, ...] = ()
) -> CheckResult:
    """Every run has every contract file and every manifest key (constitution section 11).

    ``extra_files`` are the gate's ``verification.additional_run_artifacts``.
    """
    problems: list[str] = []
    runs = _run_dirs(artifacts_root)
    for run in runs:
        for name in REQUIRED_RUN_FILES + tuple(extra_files):
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
        threshold={
            "files": list(REQUIRED_RUN_FILES) + list(extra_files),
            "manifest_keys": list(REQUIRED_MANIFEST_KEYS),
        },
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


# --------------------------------------------------------------------------- G1 checks


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _runner_results(doc: Any) -> dict[str, Any]:
    """The runner's own mapping inside results.json (``results`` key), or an empty mapping."""
    if isinstance(doc, dict) and isinstance(doc.get("results"), dict):
        return dict(doc["results"])
    return {}


def _game_records(run: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Per-game records from a run's results.json plus any structural problems found."""
    problems: list[str] = []
    path = run / "results.json"
    if not path.exists():
        return [], [f"{run.name}: results.json missing"]
    try:
        doc = _load_json(path)
    except ValueError as exc:
        return [], [f"{run.name}: results.json unreadable: {exc}"]
    games = _runner_results(doc).get("games")
    if not isinstance(games, list):
        return [], [f"{run.name}: results.json results.games is not a list"]
    records: list[dict[str, Any]] = []
    for i, rec in enumerate(games):
        if not isinstance(rec, dict):
            problems.append(f"{run.name}: game record {i} is not a mapping")
            continue
        missing = [k for k in G1_GAME_RECORD_KEYS if k not in rec]
        if missing:
            problems.append(f"{run.name}: game record {i} lacks {missing}")
            continue
        records.append(rec)
    return records, problems


def _completed_runs(artifacts_root: Path, problems: list[str]) -> list[Path]:
    runs: list[Path] = []
    for run in _run_dirs(artifacts_root):
        manifest = _load_manifest(run)
        if manifest is None:
            problems.append(f"{run.name}: manifest.json missing or not a mapping")
            continue
        if manifest.get("completion_status") != COMPLETED_STATUS:
            problems.append(f"{run.name}: completion_status != {COMPLETED_STATUS!r}")
            continue
        runs.append(run)
    return runs


def check_arc_agi_version_pinned(prereg: dict[str, Any], root: Path = ROOT) -> CheckResult:
    """uv.lock pins arc-agi at the pre-registered version; arcengine is recorded as observed."""
    locked = str(threshold(prereg, "arc_agi_locked_version"))
    lock_path = root / "uv.lock"
    versions: dict[str, str] = {}
    problems: list[str] = []
    if not lock_path.exists():
        problems.append("uv.lock missing")
    else:
        try:
            data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            problems.append(f"uv.lock unparseable: {exc}")
            data = {}
        for pkg in data.get("package", []) or []:
            if isinstance(pkg, dict) and pkg.get("name") in ("arc-agi", "arcengine"):
                versions[str(pkg["name"])] = str(pkg.get("version"))
    installed: dict[str, str | None] = {}
    for name in ("arc-agi", "arcengine"):
        try:
            installed[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed[name] = None
    if versions.get("arc-agi") != locked:
        problems.append(f"uv.lock arc-agi version {versions.get('arc-agi')!r} != {locked!r}")
    if installed.get("arc-agi") != locked:
        problems.append(f"installed arc-agi {installed.get('arc-agi')!r} != {locked!r}")
    return CheckResult(
        "arc_agi_version_pinned",
        passed=not problems,
        observed={"uv_lock": versions, "installed": installed, "problems": problems},
        threshold={"arc_agi_locked_version": locked},
        evidence=["uv.lock"],
    )


def check_environment_cache_manifest(prereg: dict[str, Any], root: Path = ROOT) -> CheckResult:
    """The committed cache manifest describes environment_files/ exactly (no drift either way)."""
    games_required = int(threshold(prereg, "cached_games_required"))
    drift_max = int(threshold(prereg, "cache_manifest_drift_files_max"))
    warming = section(prereg, "cache_warming")
    manifest_rel = str(warming.get("manifest_path") or "")
    env_rel = str(section(prereg, "experiment").get("environments_dir") or "")
    if not manifest_rel or not env_rel:
        raise PreregistrationError("cache_warming.manifest_path or experiment.environments_dir missing")
    manifest_path = root / manifest_rel
    env_dir = root / env_rel
    expected_stems = arc_interface.public_game_stems(root)

    problems: list[str] = []
    observed: dict[str, Any] = {
        "manifest": manifest_rel,
        "expected_stems": len(expected_stems),
        "listed_stems": 0,
        "drift": {"missing": [], "mismatched": [], "unlisted": []},
        "drift_files": 0,
        "committed": False,
        "baseline_actions_count": {},
    }
    if len(expected_stems) != games_required:
        problems.append(
            f"evidence base lists {len(expected_stems)} public stems, pre-registration "
            f"requires {games_required}"
        )
    if not manifest_path.exists():
        problems.append(f"{manifest_rel} missing")
        observed["problems"] = problems
        return CheckResult(
            "environment_cache_manifest",
            passed=False,
            observed=observed,
            threshold={"cached_games_required": games_required, "drift_files_max": drift_max},
            evidence=[manifest_rel, env_rel],
        )
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", manifest_rel],
        cwd=root, capture_output=True, text=True, check=False,
    )
    observed["committed"] = proc.returncode == 0
    if proc.returncode != 0:
        problems.append(f"{manifest_rel} is not tracked by git")

    try:
        manifest = _load_json(manifest_path)
    except ValueError as exc:
        problems.append(f"{manifest_rel} unreadable: {exc}")
        manifest = {}
    games = manifest.get("games") if isinstance(manifest, dict) else None
    if not isinstance(games, list):
        problems.append(f"{manifest_rel} has no 'games' list")
        games = []
    if manifest.get("environments_dir") != env_rel:
        problems.append(
            f"manifest environments_dir {manifest.get('environments_dir')!r} != {env_rel!r}"
        )

    listed_files: dict[str, str] = {}
    stems: list[str] = []
    for i, game in enumerate(games):
        if not isinstance(game, dict):
            problems.append(f"game entry {i} is not a mapping")
            continue
        missing = [k for k in G1_CACHE_GAME_KEYS if k not in game]
        if missing:
            problems.append(f"game entry {i} lacks {missing}")
            continue
        stem = str(game["stem"])
        stems.append(stem)
        if arc_interface.game_stem(str(game["game_id"])) != stem:
            problems.append(f"{stem}: game_id {game['game_id']!r} does not start with the stem")
        game_dir = root / str(game["local_dir"])
        if not game_dir.is_dir():
            problems.append(f"{stem}: local_dir {game['local_dir']} is not a directory")
        else:
            if not (game_dir / "metadata.json").is_file():
                problems.append(f"{stem}: metadata.json missing")
            else:
                try:
                    meta = _load_json(game_dir / "metadata.json")
                    if meta.get("game_id") != game["game_id"]:
                        problems.append(
                            f"{stem}: metadata game_id {meta.get('game_id')!r} != manifest "
                            f"{game['game_id']!r}"
                        )
                except ValueError as exc:
                    problems.append(f"{stem}: metadata.json unreadable: {exc}")
            py_files = [p for p in game_dir.iterdir() if p.is_file() and p.suffix == ".py"]
            if len(py_files) != 1:
                problems.append(f"{stem}: expected exactly one .py file, found {len(py_files)}")
        observed["baseline_actions_count"][stem] = game["baseline_actions_count"]
        files = game["files"]
        if not isinstance(files, dict) or not files:
            problems.append(f"{stem}: files is not a non-empty mapping")
            continue
        for rel, digest in files.items():
            listed_files[str(rel)] = str(digest).lower()

    observed["listed_stems"] = len(stems)
    if len(stems) != len(set(stems)):
        problems.append("duplicate stems in manifest")
    if set(stems) != set(expected_stems):
        problems.append(
            f"manifest stems differ from the evidence base: missing "
            f"{sorted(set(expected_stems) - set(stems))}, extra {sorted(set(stems) - set(expected_stems))}"
        )
    if len(set(stems)) != games_required:
        problems.append(f"manifest lists {len(set(stems))} stems, required {games_required}")

    actual = arc_interface.hash_environment_files(env_dir)
    missing_files = sorted(set(listed_files) - set(actual))
    unlisted = sorted(set(actual) - set(listed_files))
    mismatched = sorted(r for r in set(listed_files) & set(actual) if listed_files[r] != actual[r])
    observed["drift"] = {"missing": missing_files, "mismatched": mismatched, "unlisted": unlisted}
    drift = len(missing_files) + len(unlisted) + len(mismatched)
    observed["drift_files"] = drift
    observed["files_on_disk"] = len(actual)
    observed["files_listed"] = len(listed_files)
    if drift > drift_max:
        problems.append(f"{drift} files drifted from the manifest (max {drift_max})")
    observed["problems"] = problems
    return CheckResult(
        "environment_cache_manifest",
        passed=not problems,
        observed=observed,
        threshold={"cached_games_required": games_required, "drift_files_max": drift_max},
        evidence=[manifest_rel, env_rel],
    )


def check_offline_run(
    prereg: dict[str, Any],
    artifacts_root: Path,
    *,
    mode_key: str = "operation_mode",
    expected_mode: str | None = None,
) -> CheckResult:
    """Every run declared zero network and zero model calls, attempted none, ran offline.

    ``mode_key`` names the results.json field carrying the mode (G1 ``operation_mode``, G2
    ``operation``); ``expected_mode`` defaults to ``experiment.operation_mode`` of the
    pre-registration.
    """
    net_allowed = int(threshold(prereg, "network_calls_allowed"))
    attempts_max = int(threshold(prereg, "network_attempts_max"))
    model_allowed = int(threshold(prereg, "model_calls_allowed"))
    if expected_mode is None:
        expected_mode = str(section(prereg, "experiment").get("operation_mode") or "")
    if not expected_mode:
        raise PreregistrationError("experiment.operation_mode missing")
    expected_guard = NetworkGuard.__name__
    problems: list[str] = []
    per_run: dict[str, dict[str, Any]] = {}
    runs = _run_dirs(artifacts_root)
    for run in runs:
        manifest = _load_manifest(run) or {}
        try:
            results = _runner_results(_load_json(run / "results.json"))
        except (OSError, ValueError) as exc:
            problems.append(f"{run.name}: results.json unreadable: {exc}")
            results = {}
        row = {
            "network_calls_allowed": manifest.get("network_calls_allowed"),
            "network_attempts": manifest.get("network_attempts"),
            "model_calls_allowed": manifest.get("model_calls_allowed"),
            "model_calls": manifest.get("model_calls"),
            mode_key: results.get(mode_key),
            "network_guard": results.get("network_guard"),
        }
        per_run[run.name] = row
        if row["network_calls_allowed"] != net_allowed:
            problems.append(f"{run.name}: network_calls_allowed {row['network_calls_allowed']!r}")
        if not isinstance(row["network_attempts"], int) or row["network_attempts"] > attempts_max:
            problems.append(f"{run.name}: network_attempts {row['network_attempts']!r}")
        if row["model_calls_allowed"] != model_allowed:
            problems.append(f"{run.name}: model_calls_allowed {row['model_calls_allowed']!r}")
        if not isinstance(row["model_calls"], int) or row["model_calls"] > model_allowed:
            problems.append(f"{run.name}: model_calls {row['model_calls']!r}")
        if row[mode_key] != expected_mode:
            problems.append(f"{run.name}: {mode_key} {row[mode_key]!r}")
        if row["network_guard"] != expected_guard:
            problems.append(f"{run.name}: network_guard {row['network_guard']!r}")
    return CheckResult(
        "offline_run",
        passed=bool(runs) and not problems,
        observed={"runs": per_run, "problems": problems},
        threshold={
            "network_calls_allowed": net_allowed,
            "network_attempts_max": attempts_max,
            "model_calls_allowed": model_allowed,
            mode_key: expected_mode,
            "network_guard": expected_guard,
        },
        evidence=[_rel(r / f) for r in runs for f in ("manifest.json", "results.json")],
    )


def check_games_attempted_and_terminal(prereg: dict[str, Any], artifacts_root: Path) -> CheckResult:
    """Per run: enough games attempted, at least one terminal, no swallowed step failures."""
    attempted_min = int(threshold(prereg, "games_attempted_min"))
    terminal_min = int(threshold(prereg, "terminal_games_min"))
    failures_max = int(threshold(prereg, "step_failures_max"))
    problems: list[str] = []
    per_run: dict[str, dict[str, Any]] = {}
    runs = _run_dirs(artifacts_root)
    for run in runs:
        records, rec_problems = _game_records(run)
        problems.extend(rec_problems)
        ids = [str(r["game_id"]) for r in records]
        terminal = [str(r["game_id"]) for r in records if bool(r["terminal"])]
        failed = [str(r["game_id"]) for r in records if bool(r["step_failed"])]
        for r in records:
            state_terminal = str(r["final_state"]) in arc_interface.TERMINAL_STATES
            if bool(r["terminal"]) != state_terminal:
                problems.append(
                    f"{run.name}: {r['game_id']} terminal flag {r['terminal']!r} disagrees with "
                    f"final_state {r['final_state']!r}"
                )
        if len(set(ids)) != len(ids):
            problems.append(f"{run.name}: duplicate game_id in results")
        per_run[run.name] = {
            "attempted": len(set(ids)),
            "terminal": terminal,
            "step_failed": failed,
            "stems": sorted(arc_interface.game_stem(g) for g in set(ids)),
        }
        if len(set(ids)) < attempted_min:
            problems.append(f"{run.name}: {len(set(ids))} games attempted, min {attempted_min}")
        if len(terminal) < terminal_min:
            problems.append(f"{run.name}: {len(terminal)} terminal games, min {terminal_min}")
        if len(failed) > failures_max:
            problems.append(f"{run.name}: {len(failed)} step failures, max {failures_max}")
    return CheckResult(
        "games_attempted_and_terminal",
        passed=bool(runs) and not problems,
        observed={"runs": per_run, "problems": problems},
        threshold={
            "games_attempted_min": attempted_min,
            "terminal_games_min": terminal_min,
            "step_failures_max": failures_max,
        },
        evidence=[_rel(r / "results.json") for r in runs],
    )


def excluded_key_hits(obj: Any, excluded: frozenset[str], depth: int = 1) -> list[dict[str, Any]]:
    """Every occurrence of an excluded name: its depth (top level is 1) and whether its value is a container."""
    hits: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in excluded:
                hits.append(
                    {"key": key, "depth": depth, "container": isinstance(value, (dict, list))}
                )
            hits.extend(excluded_key_hits(value, excluded, depth + 1))
    elif isinstance(obj, list):
        for value in obj:
            hits.extend(excluded_key_hits(value, excluded, depth + 1))
    return hits


def check_exclusion_nesting(
    prereg: dict[str, Any],
    artifacts_root: Path,
    excluded: frozenset[str],
    files: tuple[str, ...] = ("results.json",),
) -> CheckResult:
    """G1 exclusion_nesting_rule: excluded names only at top level and only with scalar values.

    ``files`` are the JSON files of each run to inspect (G1: results.json; G2 adds
    human_baselines.json because it is compared for identity too).
    """
    max_depth = int(threshold(prereg, "excluded_key_max_depth"))
    containers_ok = bool(threshold(prereg, "excluded_key_container_values_allowed"))
    problems: list[str] = []
    per_run: dict[str, list[dict[str, Any]]] = {}
    runs = _run_dirs(artifacts_root)
    for run in runs:
        per_run[run.name] = []
        for name in files:
            path = run / name
            if not path.exists():
                problems.append(f"{run.name}: {name} missing")
                continue
            try:
                hits = [{**h, "file": name} for h in excluded_key_hits(_load_json(path), excluded)]
            except ValueError as exc:
                problems.append(f"{run.name}: {name} unreadable: {exc}")
                continue
            per_run[run.name].extend(hits)
            for hit in hits:
                if hit["depth"] > max_depth:
                    problems.append(
                        f"{run.name}: {name}: excluded key {hit['key']!r} at depth "
                        f"{hit['depth']} > {max_depth}"
                    )
                if hit["container"] and not containers_ok:
                    problems.append(
                        f"{run.name}: {name}: excluded key {hit['key']!r} has a container value"
                    )
    return CheckResult(
        "exclusion_nesting",
        passed=bool(runs) and not problems,
        observed={"hits": per_run, "excluded_fields": sorted(excluded), "problems": problems},
        threshold={
            "excluded_key_max_depth": max_depth,
            "excluded_key_container_values_allowed": containers_ok,
            "files": list(files),
        },
        evidence=[_rel(r / f) for r in runs for f in files],
    )


def _transitions_by_game(run: Path) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    problems: list[str] = []
    by_game: dict[str, list[dict[str, Any]]] = {}
    path = run / "transitions.jsonl"
    if not path.exists():
        return {}, [f"{run.name}: transitions.jsonl missing"]
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError as exc:
            problems.append(f"{run.name}: transitions.jsonl line {lineno}: {exc}")
            continue
        if not isinstance(rec, dict) or "game_id" not in rec or "step_index" not in rec:
            problems.append(f"{run.name}: transitions.jsonl line {lineno} lacks game_id/step_index")
            continue
        by_game.setdefault(str(rec["game_id"]), []).append(rec)
    for game_id, recs in by_game.items():
        recs.sort(key=lambda r: int(r["step_index"]))
        indices = [int(r["step_index"]) for r in recs]
        if indices != list(range(1, len(recs) + 1)):
            problems.append(f"{run.name}: {game_id} step_index sequence is not 1..n")
    return by_game, problems


def check_replay_final_frame_identity(
    prereg: dict[str, Any], artifacts_root: Path, root: Path = ROOT
) -> CheckResult:
    """Re-execute every recorded game in this process and compare the final frame digest."""
    identity_min = float(threshold(prereg, "replay_final_frame_identity_min"))
    divergent_max = int(threshold(prereg, "replay_divergent_games_max"))
    net_allowed = int(threshold(prereg, "network_calls_allowed"))
    env_rel = str(section(prereg, "experiment").get("environments_dir") or "")
    if not env_rel:
        raise PreregistrationError("experiment.environments_dir missing")
    env_dir = root / env_rel
    problems: list[str] = []
    runs = _completed_runs(artifacts_root, problems)
    attempted = 0
    divergent: list[str] = []
    per_run: dict[str, dict[str, Any]] = {}
    with NetworkGuard(net_allowed) as guard:
        for run in runs:
            records, rec_problems = _game_records(run)
            problems.extend(rec_problems)
            by_game, tr_problems = _transitions_by_game(run)
            problems.extend(tr_problems)
            row: dict[str, Any] = {"games": 0, "divergent": [], "replayed_steps": 0}
            for rec in records:
                game_id = str(rec["game_id"])
                attempted += 1
                row["games"] += 1
                recs = by_game.get(game_id, [])
                if len(recs) != int(rec["steps_taken"]):
                    problems.append(
                        f"{run.name}: {game_id} has {len(recs)} transitions but steps_taken "
                        f"{rec['steps_taken']}"
                    )
                try:
                    actions = [arc_interface.ActionRecord.from_mapping(r) for r in recs]
                    result = arc_interface.replay_actions(env_dir, game_id, int(rec["seed"]), actions)
                except (arc_interface.EnvironmentLoadError, arc_interface.ReplayError) as exc:
                    divergent.append(f"{run.name}/{game_id}")
                    row["divergent"].append({"game_id": game_id, "reason": str(exc)})
                    continue
                row["replayed_steps"] += result.steps_applied
                if not result.succeeded or result.final_digest != rec["final_frame_sha256"]:
                    divergent.append(f"{run.name}/{game_id}")
                    row["divergent"].append(
                        {
                            "game_id": game_id,
                            "recorded": rec["final_frame_sha256"],
                            "replayed": result.final_digest,
                            "failed_at_step": result.failed_at_step,
                        }
                    )
            per_run[run.name] = row
        attempts = guard.attempts
    fraction = ((attempted - len(divergent)) / attempted) if attempted else 0.0
    if attempts > net_allowed:
        problems.append(f"replay made {attempts} network attempts")
    passed = (
        bool(runs)
        and attempted > 0
        and fraction >= identity_min
        and len(divergent) <= divergent_max
        and not problems
    )
    return CheckResult(
        "replay_final_frame_identity",
        passed=passed,
        observed={
            "games_attempted": attempted,
            "divergent": divergent,
            "identity": fraction,
            "network_attempts": attempts,
            "runs": per_run,
            "problems": problems,
        },
        threshold={
            "replay_final_frame_identity_min": identity_min,
            "replay_divergent_games_max": divergent_max,
            "environments_dir": env_rel,
        },
        evidence=[_rel(r / f) for r in runs for f in ("results.json", "transitions.jsonl")],
    )


def check_throughput(prereg: dict[str, Any], artifacts_root: Path) -> CheckResult:
    """Aggregate steps / summed step() seconds, recomputed from throughput.json, per run."""
    fps_min = float(threshold(prereg, "throughput_fps_min"))
    steps_min = int(threshold(prereg, "throughput_min_steps_measured"))
    problems: list[str] = []
    per_run: dict[str, dict[str, Any]] = {}
    runs = _run_dirs(artifacts_root)
    for run in runs:
        path = run / "throughput.json"
        if not path.exists():
            problems.append(f"{run.name}: throughput.json missing")
            continue
        try:
            agg = _load_json(path).get("aggregate")
        except (ValueError, AttributeError) as exc:
            problems.append(f"{run.name}: throughput.json unreadable: {exc}")
            continue
        if not isinstance(agg, dict):
            problems.append(f"{run.name}: throughput.json has no 'aggregate' mapping")
            continue
        steps = agg.get("steps")
        seconds = agg.get("step_seconds")
        stated = agg.get("fps")
        if not isinstance(steps, int) or not isinstance(seconds, (int, float)) or seconds <= 0:
            problems.append(f"{run.name}: aggregate steps/step_seconds invalid: {agg!r}")
            continue
        fps = steps / float(seconds)
        per_run[run.name] = {"steps": steps, "step_seconds": seconds, "fps": fps, "stated_fps": stated}
        if not isinstance(stated, (int, float)) or abs(float(stated) - fps) > 1e-6 * max(1.0, fps):
            problems.append(f"{run.name}: stated fps {stated!r} != recomputed {fps:.3f}")
        if steps < steps_min:
            problems.append(f"{run.name}: {steps} steps measured, min {steps_min}")
        if fps < fps_min:
            problems.append(f"{run.name}: {fps:.1f} fps below {fps_min}")
    return CheckResult(
        "throughput",
        passed=bool(runs) and not problems,
        observed={"runs": per_run, "problems": problems},
        threshold={"throughput_fps_min": fps_min, "throughput_min_steps_measured": steps_min},
        evidence=[_rel(r / "throughput.json") for r in runs],
    )


def _tooling_checks(
    prereg: dict[str, Any], root: Path, skip_tooling: bool
) -> list[CheckResult]:
    if not skip_tooling:
        return check_tooling(prereg, root)
    return [
        CheckResult(name, passed=False, observed=None, threshold=threshold(prereg, name),
                    skipped=True, detail="skipped by --skip-tooling")
        for name in (
            "uv_sync_exit_code",
            "pytest_exit_code",
            "pytest_min_tests_collected",
            "ruff_exit_code",
            "mypy_exit_code",
        )
    ]


def evaluate_g1(
    prereg: dict[str, Any], artifacts_root: Path, root: Path = ROOT, skip_tooling: bool = False
) -> list[CheckResult]:
    """G1 checks in the order ``verification.checks_in_order`` lists them."""
    extra = tuple(str(f) for f in section(prereg, "verification").get("additional_run_artifacts", []))
    checks: list[CheckResult] = []
    checks.append(check_arc_agi_version_pinned(prereg, root))
    checks.append(check_environment_cache_manifest(prereg, root))
    checks.append(check_run_completeness(artifacts_root, extra))
    checks.append(check_sha256sums(prereg, artifacts_root))
    checks.append(check_offline_run(prereg, artifacts_root))
    checks.append(check_games_attempted_and_terminal(prereg, artifacts_root))
    nd_check, excluded = check_nondeterministic_fields(prereg, root)
    checks.append(check_exclusion_nesting(prereg, artifacts_root, excluded))
    checks.append(nd_check)
    checks.append(check_determinism(prereg, artifacts_root, excluded))
    checks.append(check_replay_final_frame_identity(prereg, artifacts_root, root))
    checks.append(check_throughput(prereg, artifacts_root))
    checks.append(check_git_clean(prereg, root))
    checks.append(check_licence(prereg, root))
    checks.extend(_tooling_checks(prereg, root, skip_tooling))
    return checks


# --------------------------------------------------------------------------- G2 checks


def _g2_inputs(prereg: dict[str, Any]) -> dict[str, str]:
    inputs = section(prereg, "experiment").get("inputs")
    if not isinstance(inputs, dict):
        raise PreregistrationError("experiment.inputs missing")
    out: dict[str, str] = {}
    for key in G2_INPUT_KEYS:
        value = inputs.get(key)
        if not isinstance(value, str) or not value:
            raise PreregistrationError(f"experiment.inputs.{key} missing")
        out[key] = value
    return out


def check_public_level_count(prereg: dict[str, Any], root: Path = ROOT) -> CheckResult:
    """25 cached games whose metadata baseline_actions lengths sum to public_levels_total."""
    games_total = int(threshold(prereg, "public_games_total"))
    levels_total = int(threshold(prereg, "public_levels_total"))
    must_equal = bool(threshold(prereg, "metadata_baseline_levels_must_equal_public_levels_total"))
    inputs = _g2_inputs(prereg)
    problems: list[str] = []
    per_game: dict[str, int] = {}
    try:
        games = human_baseline_run.load_official_games(
            root / inputs["cache_manifest"], root / inputs["environments_dir"]
        )
    except (human_baseline_run.OfficialBaselineError, ValueError, OSError) as exc:
        problems.append(str(exc))
        games = []
    for game in games:
        per_game[game.stem] = game.levels
    levels_sum = sum(per_game.values())
    if len(games) != games_total:
        problems.append(f"{len(games)} cached games, required {games_total}")
    if must_equal and levels_sum != levels_total:
        problems.append(f"metadata baselines cover {levels_sum} levels, required {levels_total}")
    return CheckResult(
        "public_level_count",
        passed=not problems,
        observed={"games": len(games), "levels_sum": levels_sum, "per_game": per_game, "problems": problems},
        threshold={
            "public_games_total": games_total,
            "public_levels_total": levels_total,
            "metadata_baseline_levels_must_equal_public_levels_total": must_equal,
        },
        evidence=[inputs["cache_manifest"], inputs["environments_dir"]],
    )


def check_rhae_synthetic_vectors(prereg: dict[str, Any], root: Path = ROOT) -> CheckResult:
    """Every embedded RHAE vector reproduces through the adapter; the adapter delegates."""
    cases_min = int(threshold(prereg, "rhae_synthetic_cases_min"))
    cases_max = int(threshold(prereg, "rhae_synthetic_cases_max"))
    tol = float(threshold(prereg, "rhae_synthetic_abs_tolerance"))
    required_tags = [str(t) for t in threshold(prereg, "rhae_synthetic_required_tags")]
    all_must_pass = bool(threshold(prereg, "rhae_synthetic_all_cases_must_pass"))
    must_delegate = bool(threshold(prereg, "rhae_adapter_must_delegate_to_toolkit"))
    rhae_section = section(prereg, "rhae")
    cases = rhae_section.get("synthetic_vectors")
    if not isinstance(cases, list):
        raise PreregistrationError("rhae.synthetic_vectors missing")
    impl = rhae_section.get("implementation")
    module_rel = str(impl.get("module") or "") if isinstance(impl, dict) else ""
    if not module_rel:
        raise PreregistrationError("rhae.implementation.module missing")

    problems: list[str] = []
    per_case: list[dict[str, Any]] = []
    tags_seen: set[str] = set()
    failing = 0
    for i, case in enumerate(cases):
        case_id = str(case.get("id", f"case_{i}"))
        tags_seen.update(str(t) for t in case.get("tags", []) or [])
        expected_envs = [float(x) for x in case.get("expected_environment_scores", [])]
        expected_total = float(case.get("expected_total"))
        try:
            got_envs, got_total = rhae.score_vector_case(case)
        except (rhae.RhaeInputError, KeyError, TypeError) as exc:
            problems.append(f"{case_id}: adapter raised {exc!r}")
            failing += 1
            per_case.append({"id": case_id, "ok": False, "error": repr(exc)})
            continue
        ok = len(got_envs) == len(expected_envs) and all(
            abs(g - e) <= tol for g, e in zip(got_envs, expected_envs, strict=True)
        ) and abs(got_total - expected_total) <= tol
        per_case.append(
            {"id": case_id, "ok": ok, "expected": [*expected_envs, expected_total],
             "got": [*got_envs, got_total]}
        )
        if not ok:
            failing += 1
            problems.append(f"{case_id}: got {got_envs} total {got_total}, expected {expected_envs} total {expected_total}")
    if not (cases_min <= len(cases) <= cases_max):
        problems.append(f"{len(cases)} synthetic cases, required {cases_min}..{cases_max}")
    missing_tags = [t for t in required_tags if t not in tags_seen]
    if missing_tags:
        problems.append(f"required tags absent from every case: {missing_tags}")
    module_path = root / module_rel
    text = module_path.read_text(encoding="utf-8") if module_path.is_file() else ""
    delegates = "EnvironmentScoreCalculator" in text and bool(
        re.search(r"^\s*(from|import)\s+arc_agi", text, re.MULTILINE)
    )
    if must_delegate and not delegates:
        problems.append(f"{module_rel} does not delegate to arc_agi EnvironmentScoreCalculator")
    if all_must_pass and failing:
        problems.append(f"{failing} case(s) failed")
    return CheckResult(
        "rhae_synthetic_vectors",
        passed=not problems,
        observed={
            "cases": len(cases), "failing": failing, "tags_seen": sorted(tags_seen),
            "delegates": delegates, "per_case": per_case, "problems": problems,
        },
        threshold={
            "rhae_synthetic_cases_min": cases_min, "rhae_synthetic_cases_max": cases_max,
            "rhae_synthetic_abs_tolerance": tol, "rhae_synthetic_required_tags": required_tags,
            "rhae_synthetic_all_cases_must_pass": all_must_pass,
            "rhae_adapter_must_delegate_to_toolkit": must_delegate,
        },
        evidence=[module_rel, "preregistration"],
    )


def check_baseline_derivation_vectors(prereg: dict[str, Any]) -> CheckResult:
    """Every embedded derivation vector reproduces exactly through the derivation module."""
    cases_min = int(threshold(prereg, "derivation_vectors_min"))
    all_must_pass = bool(threshold(prereg, "derivation_vectors_all_must_pass"))
    cases = section(prereg, "baseline_derivation_vectors").get("cases")
    if not isinstance(cases, list):
        raise PreregistrationError("baseline_derivation_vectors.cases missing")
    problems: list[str] = []
    per_case: list[dict[str, Any]] = []
    failing = 0
    for i, case in enumerate(cases):
        case_id = str(case.get("id", f"case_{i}"))
        if "expected_attributed_actions_per_level" in case:
            expected: Any = [int(x) for x in case["expected_attributed_actions_per_level"]]
        elif "expected_baseline" in case:
            expected = case["expected_baseline"]
        else:
            problems.append(f"{case_id}: no expected value")
            failing += 1
            continue
        try:
            got = human_replays.derive_vector_case(case)
        except (human_replays.HumanReplayError, KeyError, TypeError, ValueError) as exc:
            problems.append(f"{case_id}: derivation raised {exc!r}")
            failing += 1
            per_case.append({"id": case_id, "ok": False, "error": repr(exc)})
            continue
        ok = got == expected and type(got) is type(expected)
        per_case.append({"id": case_id, "ok": ok, "expected": expected, "got": got})
        if not ok:
            failing += 1
            problems.append(f"{case_id}: got {got!r}, expected {expected!r}")
    if len(cases) < cases_min:
        problems.append(f"{len(cases)} derivation cases, required at least {cases_min}")
    if all_must_pass and failing:
        problems.append(f"{failing} case(s) failed")
    return CheckResult(
        "baseline_derivation_vectors",
        passed=not problems,
        observed={"cases": len(cases), "failing": failing, "per_case": per_case, "problems": problems},
        threshold={"derivation_vectors_min": cases_min, "derivation_vectors_all_must_pass": all_must_pass},
        evidence=["src/arc_plasticity/evaluation/human_replays.py", "preregistration"],
    )


def _dataset_manifest(prereg: dict[str, Any], root: Path) -> tuple[Path, dict[str, Any] | None, str]:
    """The committed dataset manifest: path, parsed mapping (or None) and the load problem."""
    path = root / _g2_inputs(prereg)["dataset_manifest"]
    if not path.is_file():
        return path, None, f"{_rel(path)} missing"
    try:
        data = _load_json(path)
    except ValueError as exc:
        return path, None, f"{_rel(path)} unreadable: {exc}"
    if not isinstance(data, dict):
        return path, None, f"{_rel(path)} is not a mapping"
    return path, data, ""


def _manifest_digests(manifest: dict[str, Any]) -> dict[str, str]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        return {}
    return {
        str(rel): str(entry.get("sha256")).lower()
        for rel, entry in files.items()
        if isinstance(entry, dict)
    }


def check_dataset_manifest(prereg: dict[str, Any], root: Path = ROOT) -> CheckResult:
    """The committed provenance manifest exists, is complete and matches the raw directory."""
    required = [str(f) for f in threshold(prereg, "dataset_manifest_required_fields")]
    min_files = int(threshold(prereg, "dataset_manifest_min_files"))
    drift_max = int(threshold(prereg, "dataset_manifest_drift_files_max"))
    inputs = _g2_inputs(prereg)
    raw_dir = root / inputs["raw_replays_dir"]
    _, manifest, problem = _dataset_manifest(prereg, root)
    problems: list[str] = [problem] if problem else []
    observed: dict[str, Any] = {
        "manifest": inputs["dataset_manifest"], "raw_dir": inputs["raw_replays_dir"],
        "committed": False, "files": 0, "drift": [], "provenance": {},
    }
    if manifest is not None:
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", inputs["dataset_manifest"]],
            cwd=root, capture_output=True, text=True, check=False,
        )
        observed["committed"] = proc.returncode == 0
        if proc.returncode != 0:
            problems.append(f"{inputs['dataset_manifest']} is not tracked by git")
        for key in required:
            if manifest.get(key) in (None, "", {}, []):
                problems.append(f"manifest lacks {key}")
        observed["provenance"] = {
            k: manifest.get(k) for k in ("source_url", "retrieval_utc", "retrieval_method", "revision")
        }
        files = manifest.get("files")
        n_files = len(files) if isinstance(files, dict) else 0
        observed["files"] = n_files
        if n_files < min_files:
            problems.append(f"manifest lists {n_files} files, required at least {min_files}")
        drift = human_replays.manifest_drift(files, raw_dir)
        observed["drift"] = drift
        if len(drift) > drift_max:
            problems.append(f"{len(drift)} file(s) drift (max {drift_max})")
    observed["problems"] = problems
    return CheckResult(
        "dataset_manifest",
        passed=not problems,
        observed=observed,
        threshold={
            "dataset_manifest_required_fields": required,
            "dataset_manifest_min_files": min_files,
            "dataset_manifest_drift_files_max": drift_max,
        },
        evidence=[inputs["dataset_manifest"], inputs["raw_replays_dir"]],
    )


def check_replay_ingestion(
    prereg: dict[str, Any], artifacts_root: Path, root: Path = ROOT
) -> CheckResult:
    """Enough replay units, no parse failure, and the run read exactly the manifest's bytes."""
    units_min = int(threshold(prereg, "replay_units_min"))
    failures_max = int(threshold(prereg, "replay_parse_failures_max"))
    must_equal = bool(threshold(prereg, "input_manifest_must_equal_dataset_manifest"))
    manifest_path, manifest, problem = _dataset_manifest(prereg, root)
    problems: list[str] = [problem] if problem else []
    manifest_sha = sha256_file(manifest_path) if manifest is not None else None
    manifest_digests = _manifest_digests(manifest) if manifest is not None else {}
    per_run: dict[str, dict[str, Any]] = {}
    runs = _run_dirs(artifacts_root)
    for run in runs:
        try:
            results = _runner_results(_load_json(run / "results.json"))
        except (OSError, ValueError) as exc:
            problems.append(f"{run.name}: results.json unreadable: {exc}")
            continue
        missing = [k for k in G2_RESULTS_KEYS if k not in results]
        if missing:
            problems.append(f"{run.name}: results lack {missing}")
        units = results.get("replay_units_ingested")
        failures = results.get("replay_parse_failures")
        row: dict[str, Any] = {
            "replay_units_ingested": units, "replay_parse_failures": failures,
            "participant_ids_available": results.get("participant_ids_available"),
            "session_order_source": results.get("session_order_source"),
            "dataset_manifest_sha256": results.get("dataset_manifest_sha256"),
            "input_manifest_equals_dataset_manifest": None,
        }
        per_run[run.name] = row
        if not isinstance(units, int) or isinstance(units, bool) or units < units_min:
            problems.append(f"{run.name}: replay_units_ingested {units!r} < {units_min}")
        if not isinstance(failures, int) or isinstance(failures, bool) or failures > failures_max:
            problems.append(f"{run.name}: replay_parse_failures {failures!r} > {failures_max}")
        if not isinstance(row["participant_ids_available"], bool):
            problems.append(f"{run.name}: participant_ids_available is not a bool")
        if not isinstance(row["session_order_source"], str) or not row["session_order_source"]:
            problems.append(f"{run.name}: session_order_source missing")
        if manifest_sha is not None and results.get("dataset_manifest_sha256") != manifest_sha:
            problems.append(f"{run.name}: dataset_manifest_sha256 != committed manifest {manifest_sha}")
        input_path = run / "input_manifest.json"
        if not input_path.exists():
            problems.append(f"{run.name}: input_manifest.json missing")
            continue
        try:
            input_manifest = _load_json(input_path)
        except ValueError as exc:
            problems.append(f"{run.name}: input_manifest.json unreadable: {exc}")
            continue
        raw_files = input_manifest.get("raw_files") if isinstance(input_manifest, dict) else None
        if not isinstance(raw_files, dict):
            problems.append(f"{run.name}: input_manifest.json has no raw_files mapping")
            continue
        read = {str(k): str(v).lower() for k, v in raw_files.items()}
        equal = read == manifest_digests and bool(manifest_digests)
        row["input_manifest_equals_dataset_manifest"] = equal
        row["raw_files_read"] = len(read)
        if must_equal and not equal:
            only_read = sorted(set(read) - set(manifest_digests))
            only_listed = sorted(set(manifest_digests) - set(read))
            changed = sorted(k for k in set(read) & set(manifest_digests) if read[k] != manifest_digests[k])
            problems.append(
                f"{run.name}: input manifest differs from dataset manifest "
                f"(read-only {only_read[:5]}, listed-only {only_listed[:5]}, changed {changed[:5]})"
            )
    return CheckResult(
        "replay_ingestion",
        passed=bool(runs) and not problems,
        observed={"runs": per_run, "dataset_manifest_sha256": manifest_sha, "problems": problems},
        threshold={
            "replay_units_min": units_min,
            "replay_parse_failures_max": failures_max,
            "input_manifest_must_equal_dataset_manifest": must_equal,
        },
        evidence=[_rel(r / f) for r in runs for f in ("results.json", "input_manifest.json")]
        + [_rel(manifest_path)],
    )


def check_human_baseline_coverage(prereg: dict[str, Any], artifacts_root: Path) -> CheckResult:
    """Derived levels over public_levels_total >= the floor; every derived value a positive int."""
    coverage_min = float(threshold(prereg, "human_baseline_level_coverage_min"))
    levels_total = int(threshold(prereg, "public_levels_total"))
    games_total = int(threshold(prereg, "public_games_total"))
    positive_ints = bool(threshold(prereg, "derived_baselines_positive_integers"))
    problems: list[str] = []
    per_run: dict[str, dict[str, Any]] = {}
    runs = _run_dirs(artifacts_root)
    for run in runs:
        try:
            results = _runner_results(_load_json(run / "results.json"))
            table = _load_json(run / "human_baselines.json")
        except (OSError, ValueError) as exc:
            problems.append(f"{run.name}: result files unreadable: {exc}")
            continue
        games = table.get("games") if isinstance(table, dict) else None
        if not isinstance(games, list):
            problems.append(f"{run.name}: human_baselines.json has no games list")
            continue
        rows: list[dict[str, Any]] = []
        for game in games:
            levels = game.get("levels") if isinstance(game, dict) else None
            if not isinstance(levels, list):
                problems.append(f"{run.name}: game {game!r} has no levels list")
                continue
            for level in levels:
                if not isinstance(level, dict) or any(k not in level for k in G2_LEVEL_KEYS):
                    problems.append(f"{run.name}: level record lacks a required key: {level!r}")
                    continue
                rows.append(level)
        derived_rows = [r for r in rows if r["derived_baseline_actions"] is not None]
        for r in derived_rows:
            value = r["derived_baseline_actions"]
            official = r["official_baseline_actions"]
            if positive_ints and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
                problems.append(f"{run.name}: derived value {value!r} is not a positive int")
            if isinstance(official, bool) or not isinstance(official, int) or official < 1:
                problems.append(f"{run.name}: official value {official!r} is not a positive int")
            if r["exact_agreement"] != (value == official):
                problems.append(f"{run.name}: exact_agreement inconsistent for {r!r}")
        derived = len(derived_rows)
        coverage = derived / levels_total if levels_total else 0.0
        agreement = (
            sum(1 for r in derived_rows if r["derived_baseline_actions"] == r["official_baseline_actions"]) / derived
            if derived else None
        )
        row = {
            "games": len(games), "levels": len(rows), "derived_levels": derived,
            "coverage": coverage, "reported_coverage": results.get("human_baseline_level_coverage"),
            "reported_derived_levels": results.get("derived_levels"),
            "exact_agreement_fraction": agreement,
            "reported_exact_agreement_fraction": results.get("exact_agreement_fraction"),
            "median_abs_relative_difference": results.get("median_abs_relative_difference"),
        }
        per_run[run.name] = row
        if len(games) != games_total:
            problems.append(f"{run.name}: table has {len(games)} games, required {games_total}")
        if len(rows) != levels_total:
            problems.append(f"{run.name}: table has {len(rows)} levels, required {levels_total}")
        if results.get("derived_levels") != derived:
            problems.append(f"{run.name}: results derived_levels {results.get('derived_levels')!r} != table {derived}")
        reported = results.get("human_baseline_level_coverage")
        if not isinstance(reported, (int, float)) or abs(float(reported) - coverage) > 1e-12:
            problems.append(f"{run.name}: reported coverage {reported!r} != recomputed {coverage}")
        if coverage < coverage_min:
            problems.append(f"{run.name}: coverage {coverage:.4f} below {coverage_min}")
        reported_agree = results.get("exact_agreement_fraction")
        if agreement is None:
            if reported_agree is not None:
                problems.append(f"{run.name}: exact_agreement_fraction {reported_agree!r} with no derived level")
        elif not isinstance(reported_agree, (int, float)) or abs(float(reported_agree) - agreement) > 1e-12:
            problems.append(f"{run.name}: reported exact_agreement_fraction {reported_agree!r} != {agreement}")
        if "median_abs_relative_difference" not in results:
            problems.append(f"{run.name}: median_abs_relative_difference not recorded")
    return CheckResult(
        "human_baseline_coverage",
        passed=bool(runs) and not problems,
        observed={"runs": per_run, "problems": problems},
        threshold={
            "human_baseline_level_coverage_min": coverage_min,
            "public_levels_total": levels_total,
            "public_games_total": games_total,
            "derived_baselines_positive_integers": positive_ints,
        },
        evidence=[_rel(r / f) for r in runs for f in ("results.json", "human_baselines.json")],
    )


def check_determinism_fixed_seed(
    prereg: dict[str, Any], artifacts_root: Path, excluded: frozenset[str]
) -> CheckResult:
    """Identity across the fixed-seed runs on every pre-registered compared file; no contrast.

    For a derivation with no source of variation (G2 ``determinism_protocol.reasoning``).
    The protocol must pre-register ``contrast_invocations`` equal to the
    ``contrast_runs_required`` threshold and ``require_contrast_differs`` false; anything
    else is a pre-registration this check cannot evaluate and it raises.
    """
    proto = section(prereg, "determinism_protocol")
    identity_min = float(threshold(prereg, "determinism_identity_min"))
    contrast_required = int(threshold(prereg, "contrast_runs_required"))
    for key in ("fixed_seed", "identical_invocations", "contrast_invocations",
                "require_contrast_differs", "compared_files"):
        if key not in proto:
            raise PreregistrationError(f"determinism_protocol.{key} missing")
    if int(proto["contrast_invocations"]) != contrast_required:
        raise PreregistrationError(
            f"determinism_protocol.contrast_invocations {proto['contrast_invocations']} != "
            f"thresholds.contrast_runs_required {contrast_required}"
        )
    if bool(proto["require_contrast_differs"]):
        raise PreregistrationError("require_contrast_differs is true but no contrast seed is pre-registered")
    fixed_seed = int(proto["fixed_seed"])
    n_identical = int(proto["identical_invocations"])
    compared = [str(f) for f in proto["compared_files"]]
    if "results.json" not in compared or "metrics.csv" not in compared:
        raise PreregistrationError("compared_files must include results.json and metrics.csv")
    extra_json = [f for f in compared if f not in ("results.json", "metrics.csv")]
    if any(not f.endswith(".json") for f in extra_json):
        raise PreregistrationError(f"compared_files beyond the G0 pair must be JSON: {extra_json}")

    problems: list[str] = []
    fixed_runs: list[Path] = []
    other_seeds: list[str] = []
    for run in _run_dirs(artifacts_root):
        manifest = _load_manifest(run)
        if manifest is None or "seed" not in manifest:
            problems.append(f"{run.name}: no manifest seed; excluded from grouping")
            continue
        if manifest.get("completion_status") != COMPLETED_STATUS:
            problems.append(f"{run.name}: completion_status != {COMPLETED_STATUS!r}; excluded")
            continue
        if int(manifest["seed"]) == fixed_seed:
            fixed_runs.append(run)
        else:
            other_seeds.append(run.name)

    def signature(run: Path) -> tuple[Any, ...]:
        parts: list[Any] = [
            canonical_json_bytes(run / "results.json", excluded),
            canonical_csv_rows(run / "metrics.csv", excluded),
        ]
        parts.extend(canonical_json_bytes(run / name, excluded) for name in extra_json)
        return tuple(parts)

    identity = 0.0
    if len(fixed_runs) < n_identical:
        problems.append(f"need {n_identical} completed runs at seed {fixed_seed}, found {len(fixed_runs)}")
    else:
        try:
            ref = signature(fixed_runs[0])
            mismatches = [r.name for r in fixed_runs[1:] if signature(r) != ref]
            identity = 0.0 if mismatches else 1.0
            if mismatches:
                problems.append(f"same-seed runs differ from {fixed_runs[0].name}: {mismatches}")
        except (OSError, ValueError) as exc:
            problems.append(f"could not read compared files: {exc}")
    if other_seeds and contrast_required == 0:
        problems.append(f"runs at a seed other than {fixed_seed} are not pre-registered: {other_seeds}")
    return CheckResult(
        "determinism_identity",
        passed=identity >= identity_min and not problems,
        observed={
            "identity": identity, "fixed_seed_runs": [r.name for r in fixed_runs],
            "other_seed_runs": other_seeds, "compared_files": compared,
            "excluded_fields": sorted(excluded), "problems": problems,
        },
        threshold={
            "identity_min": identity_min, "fixed_seed": fixed_seed,
            "identical_invocations": n_identical, "contrast_runs_required": contrast_required,
        },
        evidence=[_rel(r / f) for r in fixed_runs for f in compared],
    )


def evaluate_g2(
    prereg: dict[str, Any], artifacts_root: Path, root: Path = ROOT, skip_tooling: bool = False
) -> list[CheckResult]:
    """G2 checks in the order ``verification.checks_in_order`` lists them."""
    extra = tuple(str(f) for f in section(prereg, "verification").get("additional_run_artifacts", []))
    contract = str(section(prereg, "experiment").get("results_json_contract") or "")
    operation = human_baseline_run.OPERATION
    if f'"{operation}"' not in contract:
        raise PreregistrationError(
            f"experiment.results_json_contract does not name operation {operation!r}"
        )
    compared = section(prereg, "determinism_protocol").get("compared_files") or []
    nesting_files = tuple(str(f) for f in compared if str(f).endswith(".json"))
    checks: list[CheckResult] = []
    checks.append(check_public_level_count(prereg, root))
    # The adapter is project code (the same module score_vector_case imports), so its text is
    # read from the project, not from the data root.
    checks.append(check_rhae_synthetic_vectors(prereg, ROOT))
    checks.append(check_baseline_derivation_vectors(prereg))
    checks.append(check_dataset_manifest(prereg, root))
    checks.append(check_run_completeness(artifacts_root, extra))
    checks.append(check_sha256sums(prereg, artifacts_root))
    checks.append(
        check_offline_run(prereg, artifacts_root, mode_key="operation", expected_mode=operation)
    )
    checks.append(check_replay_ingestion(prereg, artifacts_root, root))
    checks.append(check_human_baseline_coverage(prereg, artifacts_root))
    # "after the G0 exclusions" (determinism_protocol.reasoning): the category bounds are the
    # hash-locked G0 pre-registration's, read from the project, and its digest is recorded.
    g0, g0_path, g0_sha256 = load_preregistration("G0", ROOT)
    nd_check, excluded = check_nondeterministic_fields(
        prereg, root, bounds=section(g0, "determinism_protocol")
    )
    nd_check.threshold = {
        **nd_check.threshold,
        "bounds_source": {"preregistration": _rel(g0_path), "sha256": g0_sha256},
    }
    checks.append(check_exclusion_nesting(prereg, artifacts_root, excluded, nesting_files))
    checks.append(nd_check)
    checks.append(check_determinism_fixed_seed(prereg, artifacts_root, excluded))
    checks.append(check_git_clean(prereg, root))
    checks.append(check_licence(prereg, root))
    checks.extend(_tooling_checks(prereg, root, skip_tooling))
    return checks


GATE_EVALUATORS = {"G0": evaluate_g0, "G1": evaluate_g1, "G2": evaluate_g2}


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
