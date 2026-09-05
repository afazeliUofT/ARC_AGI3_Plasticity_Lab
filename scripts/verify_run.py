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

G3 conventions (``preregistration/G3.yaml`` ``backtest_rejection_experiment``,
``verification``), which the E310 runner (``arc_plasticity.evaluation.backtest_rejection``)
produces and this verifier consumes:

* ``results.json["results"]`` carries ``G3_E310_RESULTS_KEYS``: ``history_source`` (the G1
  run's ``transitions_path``, ``transitions_sha256``, ``sha256sums_sha256``,
  ``results_sha256``, ``environment_seed``, ``history_run_id`` - not ``run_id``, which is
  an excluded name and may only occur at the top level), ``games[]`` (``game_id``,
  ``history_length``, ``final_frame_sha256_expected``, ``final_frame_sha256_replayed``,
  ``frame_digest_mismatches``, ``replay_identity``), the trial counts and fractions,
  ``per_class``, ``backtest_limits`` and the module digests.
* ``transitions.jsonl`` holds one row per trial (``game_id``, ``trial_index``, ``kind``,
  ``mutation_class``, ``vacuous``, ``backtested``); ``hypotheses.jsonl`` holds the
  backtester's record per trial (``certified``, ``mismatches``, ``history_length``,
  ``history_length_checked``, ``failure_kind``, module digests). The verifier recomputes
  every rejection number from these two files and grades the recomputation; results.json
  must agree with it.
* The G1 history run is located from ``history_source.transitions_path`` and bound to the
  hash-locked ``g1_history_run_sha256sums_sha256``; its ``results.json`` supplies the final
  frame digests and step counts the E310 histories must reproduce.
* The E310 determinism protocol lives under ``backtest_rejection_experiment``; the G0
  exclusion bounds apply, as G2.
* E300 checks whose artifacts arrive with G3.4-G3.8 are reported as failures (never passes,
  never skips) until their evaluators exist, so an incomplete G3 cannot read as PASS.

G3 graded-set conventions (``preregistration/G3.yaml`` ``experiment``, ``verification``, and
the successor ``preregistration/G3b.yaml`` when it exists), which the E300/E304 runner
(``arc_plasticity.agents.ref_world_model``) produces and this verifier consumes:

* One game per run. ``results.json["results"]`` carries ``G3_E300_RESULTS_KEYS``; the top
  level carries ``config_file_sha256`` and ``experiment_id``. ``level_accounting.json`` and
  ``rhae.json`` are the per-level tables the RHAE recomputation reads; ``metrics.csv`` is a
  ``metric,value`` table. ``transitions.jsonl`` carries ``G3_E300_TRANSITION_KEYS`` per action
  (``source`` is ``exploration``, ``plan`` or ``reset``); ``plans.jsonl``, ``backtests.jsonl``,
  ``hypotheses.jsonl`` and ``model_calls.jsonl`` carry the keys named by the ``G3_*_KEYS``
  tuples. The accounting is rebuilt from ``transitions.jsonl`` through
  ``level_accounting.accounting_from_log`` and must equal the run's own.
* The run set manifest (``experiments/<experiment>_run_set.json``) is recomputed from the
  run directories by the rule in ``_assign_sets_and_roles`` and compared; the verifier grades
  the highest-numbered complete set.
* When ``preregistration/G3b.yaml`` exists, ``evaluate_g3`` reads the G3 thresholds, replaces
  exactly the keys under ``thresholds_overriding_g3`` with the successor's values, grades the
  successor's ``graded_experiment.artifacts_root``, adds the successor's checks, and records
  both digests in the ``successor_preregistration_overlay`` check.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from arc_plasticity.core.guards import NetworkGuard
from arc_plasticity.environments import arc_interface
from arc_plasticity.evaluation import human_baseline_run, human_replays, rhae
from arc_plasticity.evaluation import level_accounting as la

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
    artifacts_root: Path,
    extra_files: tuple[str, ...] = (),
    runs: list[Path] | None = None,
) -> CheckResult:
    """Every run has every contract file and every manifest key (constitution section 11).

    ``extra_files`` are the gate's ``verification.additional_run_artifacts``. ``runs``
    restricts the check to the given run directories (G3: the graded set, so a preserved
    failed attempt is listed by the run set manifest without being held to the contract).
    """
    problems: list[str] = []
    runs = _run_dirs(artifacts_root) if runs is None else list(runs)
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


def check_sha256sums(
    prereg: dict[str, Any], artifacts_root: Path, runs: list[Path] | None = None
) -> CheckResult:
    frac_min = float(threshold(prereg, "sha256sums_verified_fraction_min"))
    must_list_all = bool(threshold(prereg, "sha256sums_must_list_every_artifact_file"))
    total = verified = 0
    problems: list[str] = []
    runs = _run_dirs(artifacts_root) if runs is None else list(runs)
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
            present = {str(p.relative_to(run)) for p in run.rglob("*") if p.is_file() and p != sums}
            unlisted = sorted(present - set(listed))
            if unlisted:
                problems.append(f"{run.name}: unlisted files {unlisted}")
    fraction = (verified / total) if total else 0.0
    return CheckResult(
        "sha256sums_verify",
        passed=bool(runs) and fraction >= frac_min and not problems,
        observed={
            "listed": total,
            "verified": verified,
            "fraction": fraction,
            "problems": problems,
        },
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
        evidence=[
            str(r / f) for r in fixed_runs + contrast_runs for f in ("results.json", "metrics.csv")
        ],
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
    body = markdown[m.end() :]
    nxt = re.search(r"^## ", body, re.MULTILINE)
    if nxt:
        body = body[: nxt.start()]
    starts = [mm for mm in re.finditer(r"^(\d+)\.\s", body, re.MULTILINE)]
    total = resolved = 0
    unresolved: list[str] = []
    for i, mm in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(body)
        item = body[mm.start() : end]
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
                CheckResult(
                    name,
                    passed=False,
                    observed=None,
                    threshold=threshold(prereg, name),
                    skipped=True,
                    detail="skipped by --skip-tooling",
                )
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
        raise PreregistrationError(
            "cache_warming.manifest_path or experiment.environments_dir missing"
        )
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
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
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
    model_allowed: int | None = None,
    runs: list[Path] | None = None,
) -> CheckResult:
    """Every run declared zero network and zero model calls, attempted none, ran offline.

    ``mode_key`` names the results.json field carrying the mode (G1 ``operation_mode``, G2
    ``operation``); ``expected_mode`` defaults to ``experiment.operation_mode`` of the
    pre-registration. ``model_allowed`` defaults to ``thresholds.model_calls_allowed``; G3
    passes the E310 experiment's own ``model_calls_allowed`` (zero) because its thresholds
    carry a per-game model-call ceiling for E300 instead. ``runs`` restricts the check to
    the given run directories (G3: the graded set).
    """
    net_allowed = int(threshold(prereg, "network_calls_allowed"))
    attempts_max = int(threshold(prereg, "network_attempts_max"))
    if model_allowed is None:
        model_allowed = int(threshold(prereg, "model_calls_allowed"))
    if expected_mode is None:
        expected_mode = str(section(prereg, "experiment").get("operation_mode") or "")
    if not expected_mode:
        raise PreregistrationError("experiment.operation_mode missing")
    expected_guard = NetworkGuard.__name__
    problems: list[str] = []
    per_run: dict[str, dict[str, Any]] = {}
    runs = _run_dirs(artifacts_root) if runs is None else list(runs)
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
                    result = arc_interface.replay_actions(
                        env_dir, game_id, int(rec["seed"]), actions
                    )
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
        per_run[run.name] = {
            "steps": steps,
            "step_seconds": seconds,
            "fps": fps,
            "stated_fps": stated,
        }
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


def _tooling_checks(prereg: dict[str, Any], root: Path, skip_tooling: bool) -> list[CheckResult]:
    if not skip_tooling:
        return check_tooling(prereg, root)
    return [
        CheckResult(
            name,
            passed=False,
            observed=None,
            threshold=threshold(prereg, name),
            skipped=True,
            detail="skipped by --skip-tooling",
        )
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
    extra = tuple(
        str(f) for f in section(prereg, "verification").get("additional_run_artifacts", [])
    )
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
        observed={
            "games": len(games),
            "levels_sum": levels_sum,
            "per_game": per_game,
            "problems": problems,
        },
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
        ok = (
            len(got_envs) == len(expected_envs)
            and all(abs(g - e) <= tol for g, e in zip(got_envs, expected_envs, strict=True))
            and abs(got_total - expected_total) <= tol
        )
        per_case.append(
            {
                "id": case_id,
                "ok": ok,
                "expected": [*expected_envs, expected_total],
                "got": [*got_envs, got_total],
            }
        )
        if not ok:
            failing += 1
            problems.append(
                f"{case_id}: got {got_envs} total {got_total}, expected {expected_envs} total {expected_total}"
            )
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
            "cases": len(cases),
            "failing": failing,
            "tags_seen": sorted(tags_seen),
            "delegates": delegates,
            "per_case": per_case,
            "problems": problems,
        },
        threshold={
            "rhae_synthetic_cases_min": cases_min,
            "rhae_synthetic_cases_max": cases_max,
            "rhae_synthetic_abs_tolerance": tol,
            "rhae_synthetic_required_tags": required_tags,
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
        observed={
            "cases": len(cases),
            "failing": failing,
            "per_case": per_case,
            "problems": problems,
        },
        threshold={
            "derivation_vectors_min": cases_min,
            "derivation_vectors_all_must_pass": all_must_pass,
        },
        evidence=["src/arc_plasticity/evaluation/human_replays.py", "preregistration"],
    )


def _dataset_manifest(
    prereg: dict[str, Any], root: Path
) -> tuple[Path, dict[str, Any] | None, str]:
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
        "manifest": inputs["dataset_manifest"],
        "raw_dir": inputs["raw_replays_dir"],
        "committed": False,
        "files": 0,
        "drift": [],
        "provenance": {},
    }
    if manifest is not None:
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", inputs["dataset_manifest"]],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        observed["committed"] = proc.returncode == 0
        if proc.returncode != 0:
            problems.append(f"{inputs['dataset_manifest']} is not tracked by git")
        for key in required:
            if manifest.get(key) in (None, "", {}, []):
                problems.append(f"manifest lacks {key}")
        observed["provenance"] = {
            k: manifest.get(k)
            for k in ("source_url", "retrieval_utc", "retrieval_method", "revision")
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
            "replay_units_ingested": units,
            "replay_parse_failures": failures,
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
            problems.append(
                f"{run.name}: dataset_manifest_sha256 != committed manifest {manifest_sha}"
            )
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
            changed = sorted(
                k for k in set(read) & set(manifest_digests) if read[k] != manifest_digests[k]
            )
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
            if positive_ints and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                problems.append(f"{run.name}: derived value {value!r} is not a positive int")
            if isinstance(official, bool) or not isinstance(official, int) or official < 1:
                problems.append(f"{run.name}: official value {official!r} is not a positive int")
            if r["exact_agreement"] != (value == official):
                problems.append(f"{run.name}: exact_agreement inconsistent for {r!r}")
        derived = len(derived_rows)
        coverage = derived / levels_total if levels_total else 0.0
        agreement = (
            sum(
                1
                for r in derived_rows
                if r["derived_baseline_actions"] == r["official_baseline_actions"]
            )
            / derived
            if derived
            else None
        )
        row = {
            "games": len(games),
            "levels": len(rows),
            "derived_levels": derived,
            "coverage": coverage,
            "reported_coverage": results.get("human_baseline_level_coverage"),
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
            problems.append(
                f"{run.name}: results derived_levels {results.get('derived_levels')!r} != table {derived}"
            )
        reported = results.get("human_baseline_level_coverage")
        if not isinstance(reported, (int, float)) or abs(float(reported) - coverage) > 1e-12:
            problems.append(f"{run.name}: reported coverage {reported!r} != recomputed {coverage}")
        if coverage < coverage_min:
            problems.append(f"{run.name}: coverage {coverage:.4f} below {coverage_min}")
        reported_agree = results.get("exact_agreement_fraction")
        if agreement is None:
            if reported_agree is not None:
                problems.append(
                    f"{run.name}: exact_agreement_fraction {reported_agree!r} with no derived level"
                )
        elif (
            not isinstance(reported_agree, (int, float))
            or abs(float(reported_agree) - agreement) > 1e-12
        ):
            problems.append(
                f"{run.name}: reported exact_agreement_fraction {reported_agree!r} != {agreement}"
            )
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
    for key in (
        "fixed_seed",
        "identical_invocations",
        "contrast_invocations",
        "require_contrast_differs",
        "compared_files",
    ):
        if key not in proto:
            raise PreregistrationError(f"determinism_protocol.{key} missing")
    if int(proto["contrast_invocations"]) != contrast_required:
        raise PreregistrationError(
            f"determinism_protocol.contrast_invocations {proto['contrast_invocations']} != "
            f"thresholds.contrast_runs_required {contrast_required}"
        )
    if bool(proto["require_contrast_differs"]):
        raise PreregistrationError(
            "require_contrast_differs is true but no contrast seed is pre-registered"
        )
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
        except (OSError, ValueError) as exc:
            problems.append(f"could not read compared files: {exc}")
    if other_seeds and contrast_required == 0:
        problems.append(
            f"runs at a seed other than {fixed_seed} are not pre-registered: {other_seeds}"
        )
    return CheckResult(
        "determinism_identity",
        passed=identity >= identity_min and not problems,
        observed={
            "identity": identity,
            "fixed_seed_runs": [r.name for r in fixed_runs],
            "other_seed_runs": other_seeds,
            "compared_files": compared,
            "excluded_fields": sorted(excluded),
            "problems": problems,
        },
        threshold={
            "identity_min": identity_min,
            "fixed_seed": fixed_seed,
            "identical_invocations": n_identical,
            "contrast_runs_required": contrast_required,
        },
        evidence=[_rel(r / f) for r in fixed_runs for f in compared],
    )


def evaluate_g2(
    prereg: dict[str, Any], artifacts_root: Path, root: Path = ROOT, skip_tooling: bool = False
) -> list[CheckResult]:
    """G2 checks in the order ``verification.checks_in_order`` lists them."""
    extra = tuple(
        str(f) for f in section(prereg, "verification").get("additional_run_artifacts", [])
    )
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


# --------------------------------------------------------------------------- G3 checks

G3_E310_RESULTS_KEYS: tuple[str, ...] = (
    "operation_mode",
    "network_guard",
    "history_source",
    "games",
    "wrong_model_trials",
    "vacuous_trials",
    "non_vacuous_trials",
    "rejected_trials",
    "rejection_fraction",
    "per_class",
    "control_trials",
    "control_accepted",
    "correct_model_acceptance_fraction",
    "replay_identity_games",
    "replay_divergent_games",
    "history_length_checked_equal_length_all",
    "backtest_limits",
    "backtest_module_sha256",
    "interface_sha256",
)

G3_E310_GAME_KEYS: tuple[str, ...] = (
    "game_id",
    "history_length",
    "final_frame_sha256_expected",
    "final_frame_sha256_replayed",
    "frame_digest_mismatches",
    "replay_identity",
)

G3_E310_HISTORY_SOURCE_KEYS: tuple[str, ...] = (
    "transitions_path",
    "transitions_sha256",
    "sha256sums_sha256",
    "results_sha256",
    "environment_seed",
    "history_run_id",
)

G3_E310_TRANSITION_KEYS: tuple[str, ...] = (
    "game_id",
    "trial_index",
    "kind",
    "mutation_class",
    "vacuous",
    "backtested",
)

G3_E310_HYPOTHESIS_KEYS: tuple[str, ...] = (
    "game_id",
    "trial_index",
    "kind",
    "mutation_class",
    "certified",
    "mismatches",
    "history_length",
    "history_length_checked",
    "failure_kind",
    "backtest_module_sha256",
    "interface_sha256",
)

G3_E310_LIMIT_THRESHOLDS: tuple[tuple[str, str], ...] = (
    ("backtest_seconds_max", "sandbox_backtest_seconds_max"),
    ("predict_seconds_max", "sandbox_predict_seconds_max"),
    ("address_space_bytes_max", "sandbox_address_space_bytes_max"),
)

# E300 checks named in verification.checks_in_order whose evaluators arrive with the
# artifacts they grade (task_plan G3.4-G3.8). Until then each is a failure, never a pass.
G3_E300_PENDING_CHECKS: tuple[tuple[str, str], ...] = (
    ("run_set_manifest", "experiments/E300_ref_run_set.json and artifacts/E300_ref/ (G3.4)"),
    ("official_baselines_used", "artifacts/E300_ref/<run>/level_accounting.json (G3.4)"),
    ("action_budget_enforced", "artifacts/E300_ref/<run>/level_accounting.json (G3.4)"),
    ("replay_final_frame_identity", "artifacts/E300_ref/<run>/transitions.jsonl (G3.4)"),
    ("rhae_recomputed", "artifacts/E300_ref/<run>/rhae.json (G3.4)"),
    ("model_call_accounting", "artifacts/E300_ref/<run>/model_calls.jsonl (G3.5)"),
    ("verification_active", "artifacts/E300_ref/<run>/plans.jsonl and backtests.jsonl (G3.4)"),
    ("preflight_recorded", "state/BUDGET.json g3_preflight and the three pre-flight runs (G3.6)"),
)


def _pending_e300_check(name: str, needs: str, artifacts_root: Path) -> CheckResult:
    """A pre-registered E300 check that cannot be evaluated yet: a failure, not a skip."""
    return CheckResult(
        name,
        passed=False,
        observed={
            "status": "not_yet_evaluable",
            "needs": needs,
            "artifacts_root_present": artifacts_root.exists(),
        },
        threshold="evaluator added with its artifacts (verification.task_plan); "
        "never a pass until it exists",
        detail="not yet evaluable; reported as a failure so an incomplete G3 cannot pass",
        evidence=[_rel(artifacts_root)],
    )


def _g3_e310_section(prereg: dict[str, Any]) -> dict[str, Any]:
    return section(prereg, "backtest_rejection_experiment")


def _g3_e310_view(prereg: dict[str, Any]) -> dict[str, Any]:
    """The pre-registration with the E310 determinism protocol hoisted to the top level, so
    the G0/G1 determinism and exclusion checks apply to E310 unchanged."""
    proto = _g3_e310_section(prereg).get("determinism_protocol")
    if not isinstance(proto, dict):
        raise PreregistrationError("backtest_rejection_experiment.determinism_protocol missing")
    return {**prereg, "determinism_protocol": proto}


def _g3_cache_manifest_path(prereg: dict[str, Any]) -> str:
    text = str(section(prereg, "experiment").get("cache_manifest") or "").strip()
    rel = text.split()[0] if text else ""
    if not rel:
        raise PreregistrationError("experiment.cache_manifest missing")
    return rel


def check_cache_manifest_locked(prereg: dict[str, Any], root: Path = ROOT) -> CheckResult:
    """The committed cache manifest has the hash-locked digest, describes environment_files/
    exactly (as G1) and uv.lock pins arc-agi at the locked version."""
    locked = str(threshold(prereg, "cache_manifest_sha256")).lower()
    rel = _g3_cache_manifest_path(prereg)
    path = root / rel
    problems: list[str] = []
    digest = sha256_file(path) if path.exists() else None
    if digest != locked:
        problems.append(f"{rel} sha256 {digest!r} != locked {locked!r}")
    drift = check_environment_cache_manifest(
        {**prereg, "cache_warming": {"manifest_path": rel}}, root
    )
    version = check_arc_agi_version_pinned(prereg, root)
    for sub in (drift, version):
        if not sub.passed:
            sub_problems = sub.observed.get("problems") if isinstance(sub.observed, dict) else None
            problems.append(f"{sub.name}: {sub_problems}")
    return CheckResult(
        "cache_manifest_locked",
        passed=not problems,
        observed={
            "manifest": rel,
            "sha256": digest,
            drift.name: drift.observed,
            version.name: version.observed,
            "problems": problems,
        },
        threshold={"cache_manifest_sha256": locked, **drift.threshold, **version.threshold},
        evidence=[rel, *drift.evidence, *version.evidence],
    )


def _read_jsonl_records(
    run: Path, name: str, required: tuple[str, ...], problems: list[str]
) -> list[dict[str, Any]]:
    path = run / name
    if not path.exists():
        problems.append(f"{run.name}: {name} missing")
        return []
    records: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError as exc:
            problems.append(f"{run.name}: {name} line {lineno}: {exc}")
            continue
        if not isinstance(rec, dict):
            problems.append(f"{run.name}: {name} line {lineno} is not a mapping")
            continue
        missing = [k for k in required if k not in rec]
        if missing:
            problems.append(f"{run.name}: {name} line {lineno} lacks {missing}")
            continue
        records.append(rec)
    return records


def _parse_sha256sums(path: Path) -> dict[str, str]:
    listed: dict[str, str] = {}
    for line in path.read_text().splitlines():
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$", line)
        if m:
            listed[m.group(2).strip()] = m.group(1).lower()
    return listed


def _g1_history_run(
    prereg: dict[str, Any], root: Path, run_name: str, source: Any, problems: list[str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Locate the G1 run the E310 histories came from and bind it to the locked digest.

    Returns the G1 per-game records keyed by game_id and the evidence paths read. The path
    comes from the run's own ``history_source`` record; the binding comes from the
    pre-registration's ``g1_history_run_sha256sums_sha256``, never from the record.
    """
    locked = str(threshold(prereg, "g1_history_run_sha256sums_sha256")).lower()
    if not isinstance(source, dict):
        problems.append(f"{run_name}: history_source is not a mapping")
        return {}, []
    missing = [k for k in G3_E310_HISTORY_SOURCE_KEYS if k not in source]
    if missing:
        problems.append(f"{run_name}: history_source lacks {missing}")
        return {}, []
    transitions = root / str(source["transitions_path"])
    g1_run = transitions.parent
    sums = g1_run / "SHA256SUMS"
    results = g1_run / "results.json"
    evidence = [_rel(p) for p in (sums, transitions, results)]
    if not (sums.exists() and transitions.exists() and results.exists()):
        problems.append(f"{run_name}: G1 history run {_rel(g1_run)} is incomplete")
        return {}, evidence
    sums_digest = sha256_file(sums)
    if sums_digest != locked:
        problems.append(f"{run_name}: G1 run SHA256SUMS sha256 {sums_digest} != locked {locked}")
    if str(source["sha256sums_sha256"]).lower() != locked:
        problems.append(f"{run_name}: recorded history sha256sums_sha256 != locked digest")
    listed = _parse_sha256sums(sums)
    t_digest = sha256_file(transitions)
    if t_digest != str(source["transitions_sha256"]).lower():
        problems.append(f"{run_name}: G1 transitions.jsonl sha256 {t_digest} != recorded")
    if listed.get("transitions.jsonl") != t_digest:
        problems.append(f"{run_name}: G1 transitions.jsonl is not sealed by its SHA256SUMS")
    r_digest = sha256_file(results)
    if r_digest != str(source["results_sha256"]).lower():
        problems.append(f"{run_name}: G1 results.json sha256 {r_digest} != recorded")
    if listed.get("results.json") != r_digest:
        problems.append(f"{run_name}: G1 results.json is not sealed by its SHA256SUMS")
    manifest = _load_manifest(g1_run) or {}
    if manifest.get("run_id") != source["history_run_id"]:
        problems.append(f"{run_name}: G1 manifest run_id {manifest.get('run_id')!r} != recorded")
    if manifest.get("seed") != source["environment_seed"]:
        problems.append(
            f"{run_name}: G1 manifest seed {manifest.get('seed')!r} != recorded environment_seed"
        )
    records, rec_problems = _game_records(g1_run)
    problems.extend(f"{run_name}: G1 {p}" for p in rec_problems)
    return {str(r["game_id"]): r for r in records}, evidence


def check_backtest_rejection(
    prereg: dict[str, Any], artifacts_root: Path, root: Path = ROOT
) -> CheckResult:
    """E310: the backtester rejects wrong models and accepts the true one, recomputed.

    Every count and fraction is recomputed from ``hypotheses.jsonl`` (the backtester's
    records) joined with ``transitions.jsonl`` (the trial table, which carries ``vacuous``)
    and graded on the recomputation; ``results.json`` must agree with it. The histories are
    bound to the G1 run by the locked SHA256SUMS digest and must reproduce its final frame
    digests and step counts. The sandbox limits must be the locked ones, the recorded
    backtester digest must be the live module's and the same across runs, and every record's
    ``certified`` must follow from its mismatches, coverage and failure kind.
    """
    from arc_plasticity.hypotheses import backtest as backtest_mod

    wrong_min = int(threshold(prereg, "backtest_wrong_model_trials_min"))
    control_min = int(threshold(prereg, "backtest_control_trials_min"))
    classes_min = int(threshold(prereg, "backtest_mutation_classes_min"))
    per_class_min = int(threshold(prereg, "backtest_trials_per_class_min"))
    vacuous_max = int(threshold(prereg, "backtest_vacuous_trials_max"))
    rejection_min = float(threshold(prereg, "backtest_rejection_fraction_min"))
    acceptance_min = float(threshold(prereg, "backtest_correct_model_acceptance_min"))
    history_min = int(threshold(prereg, "backtest_history_min_length"))
    mismatch_max = int(threshold(prereg, "backtest_mismatches_for_certification_max"))
    full_history = bool(threshold(prereg, "backtest_must_cover_full_history"))
    games_total = int(threshold(prereg, "public_games_total"))
    identity_min = float(threshold(prereg, "replay_final_frame_identity_min"))
    divergent_max = int(threshold(prereg, "replay_divergent_games_max"))
    limits_expected = {key: threshold(prereg, name) for key, name in G3_E310_LIMIT_THRESHOLDS}
    live = {
        "backtest_module_sha256": backtest_mod.backtest_module_sha256(),
        "interface_sha256": backtest_mod.interface_sha256(),
    }

    problems: list[str] = []
    runs = _completed_runs(artifacts_root, problems)
    per_run: dict[str, dict[str, Any]] = {}
    evidence: list[str] = []
    module_digests: set[str] = set()
    for run in runs:
        name = run.name
        evidence.extend(
            _rel(run / f) for f in ("results.json", "transitions.jsonl", "hypotheses.jsonl")
        )
        try:
            results = _runner_results(_load_json(run / "results.json"))
        except (OSError, ValueError) as exc:
            problems.append(f"{name}: results.json unreadable: {exc}")
            continue
        missing = [k for k in G3_E310_RESULTS_KEYS if k not in results]
        if missing:
            problems.append(f"{name}: results.json lacks {missing}")
            continue

        # Histories: located from the run's record, bound to the locked G1 digest.
        g1_games, g1_evidence = _g1_history_run(
            prereg, root, name, results["history_source"], problems
        )
        evidence.extend(e for e in g1_evidence if e not in evidence)
        games = results["games"]
        if not isinstance(games, list):
            problems.append(f"{name}: games is not a list")
            games = []
        identical = 0
        divergent: list[str] = []
        game_ids: list[str] = []
        for i, game in enumerate(games):
            if not isinstance(game, dict) or any(k not in game for k in G3_E310_GAME_KEYS):
                problems.append(f"{name}: game record {i} lacks {list(G3_E310_GAME_KEYS)}")
                continue
            game_id = str(game["game_id"])
            game_ids.append(game_id)
            ref = g1_games.get(game_id)
            if ref is None:
                problems.append(f"{name}: {game_id} is not in the G1 history run")
                divergent.append(game_id)
                continue
            expected = str(ref["final_frame_sha256"])
            ok = (
                game["final_frame_sha256_expected"] == expected
                and game["final_frame_sha256_replayed"] == expected
                and game["frame_digest_mismatches"] == 0
                and game["replay_identity"] is True
            )
            if ok:
                identical += 1
            else:
                divergent.append(game_id)
            length = int(game["history_length"])
            if length != int(ref["steps_taken"]):
                problems.append(
                    f"{name}: {game_id} history_length {length} != G1 steps_taken "
                    f"{ref['steps_taken']}"
                )
            if length < history_min:
                problems.append(f"{name}: {game_id} history_length {length} < {history_min}")
        if len(game_ids) != games_total:
            problems.append(f"{name}: {len(game_ids)} games, required {games_total}")
        if g1_games and set(game_ids) != set(g1_games):
            problems.append(f"{name}: game set differs from the G1 history run")
        identity = (identical / len(game_ids)) if game_ids else 0.0
        if identity < identity_min:
            problems.append(f"{name}: replay identity {identity} < {identity_min}")
        if len(divergent) > divergent_max:
            problems.append(f"{name}: divergent games {divergent} (max {divergent_max})")
        if results["replay_identity_games"] != identical:
            problems.append(f"{name}: results replay_identity_games != recomputed {identical}")
        if results["replay_divergent_games"] != len(divergent):
            problems.append(f"{name}: results replay_divergent_games != recomputed")

        # Trials: recomputed from the backtester's records joined with the trial table.
        transitions = _read_jsonl_records(
            run, "transitions.jsonl", G3_E310_TRANSITION_KEYS, problems
        )
        hyps = _read_jsonl_records(run, "hypotheses.jsonl", G3_E310_HYPOTHESIS_KEYS, problems)
        trial_table: dict[tuple[str, int], dict[str, Any]] = {}
        for t in transitions:
            key = (str(t["game_id"]), int(t["trial_index"]))
            if key in trial_table:
                problems.append(f"{name}: duplicate trial {key} in transitions.jsonl")
            trial_table[key] = t
        hyp_keys = [(str(h["game_id"]), int(h["trial_index"])) for h in hyps]
        if len(set(hyp_keys)) != len(hyp_keys):
            problems.append(f"{name}: duplicate trial records in hypotheses.jsonl")
        if set(hyp_keys) != set(trial_table):
            problems.append(
                f"{name}: hypotheses.jsonl trials != transitions.jsonl trials "
                f"(every trial must be backtested exactly once)"
            )
        inconsistent = 0
        partial_certified = 0
        module_mismatches = 0
        wrong: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
        controls: list[dict[str, Any]] = []
        for h in hyps:
            key = (str(h["game_id"]), int(h["trial_index"]))
            checked, length = int(h["history_length_checked"]), int(h["history_length"])
            expected_certified = (
                int(h["mismatches"]) <= mismatch_max
                and checked == length
                and h["failure_kind"] is None
            )
            if bool(h["certified"]) != expected_certified:
                inconsistent += 1
            if full_history and bool(h["certified"]) and checked != length:
                partial_certified += 1
            if (
                h["backtest_module_sha256"] != results["backtest_module_sha256"]
                or h["interface_sha256"] != results["interface_sha256"]
            ):
                module_mismatches += 1
            if h["kind"] == "wrong_model":
                wrong.append((h, trial_table.get(key)))
            elif h["kind"] == "control":
                controls.append(h)
            else:
                problems.append(f"{name}: trial {key} has kind {h['kind']!r}")
        if inconsistent:
            problems.append(
                f"{name}: {inconsistent} records whose certified flag does not follow from "
                f"mismatches <= {mismatch_max}, full coverage and no failure"
            )
        if partial_certified:
            problems.append(f"{name}: {partial_certified} certifications on a partial history")
        if module_mismatches:
            problems.append(f"{name}: {module_mismatches} records with other module digests")
        non_vacuous = [
            (h, trial) for h, trial in wrong if trial is not None and not bool(trial["vacuous"])
        ]
        rejected = [h for h, _ in non_vacuous if not bool(h["certified"])]
        vacuous = len(wrong) - len(non_vacuous)
        per_class: dict[str, dict[str, int]] = {}
        for h, trial in wrong:
            cls = str(h["mutation_class"])
            row = per_class.setdefault(cls, {"trials": 0, "non_vacuous": 0, "rejected": 0})
            row["trials"] += 1
            if trial is not None and not bool(trial["vacuous"]):
                row["non_vacuous"] += 1
                if not bool(h["certified"]):
                    row["rejected"] += 1
        rejection = (len(rejected) / len(non_vacuous)) if non_vacuous else 0.0
        accepted = sum(1 for h in controls if bool(h["certified"]))
        acceptance = (accepted / len(controls)) if controls else 0.0

        if len(wrong) < wrong_min:
            problems.append(f"{name}: wrong-model trials {len(wrong)} < {wrong_min}")
        if len(controls) < control_min:
            problems.append(f"{name}: control trials {len(controls)} < {control_min}")
        if len(per_class) < classes_min:
            problems.append(f"{name}: {len(per_class)} mutation classes < {classes_min}")
        for cls, row in sorted(per_class.items()):
            if row["trials"] < per_class_min:
                problems.append(f"{name}: class {cls} has {row['trials']} trials < {per_class_min}")
        if vacuous > vacuous_max:
            problems.append(f"{name}: vacuous trials {vacuous} > {vacuous_max}")
        if rejection < rejection_min:
            problems.append(f"{name}: rejection fraction {rejection} < {rejection_min}")
        if acceptance < acceptance_min:
            problems.append(f"{name}: correct-model acceptance {acceptance} < {acceptance_min}")

        recorded = {
            "wrong_model_trials": len(wrong),
            "vacuous_trials": vacuous,
            "non_vacuous_trials": len(non_vacuous),
            "rejected_trials": len(rejected),
            "rejection_fraction": rejection,
            "control_trials": len(controls),
            "control_accepted": accepted,
            "correct_model_acceptance_fraction": acceptance,
        }
        for field_name, value in recorded.items():
            if results[field_name] != value:
                problems.append(
                    f"{name}: results {field_name} {results[field_name]!r} != recomputed {value!r}"
                )
        results_classes = results["per_class"] if isinstance(results["per_class"], dict) else {}
        for cls, row in per_class.items():
            rec = results_classes.get(cls)
            if (
                not isinstance(rec, dict)
                or rec.get("trials") != row["trials"]
                or rec.get("rejected_trials") != row["rejected"]
            ):
                problems.append(f"{name}: results per_class[{cls}] disagrees with recomputation")

        # The sandbox limits and the backtester are the pre-registered ones.
        limits = results["backtest_limits"] if isinstance(results["backtest_limits"], dict) else {}
        for limit_name, expected_value in limits_expected.items():
            if limit_name not in limits or float(limits[limit_name]) != float(expected_value):
                problems.append(
                    f"{name}: backtest_limits.{limit_name} {limits.get(limit_name)!r} != "
                    f"{expected_value!r}"
                )
        for digest_name, digest in live.items():
            if results[digest_name] != digest:
                problems.append(
                    f"{name}: results {digest_name} {results[digest_name]!r} != live module {digest}"
                )
        module_digests.add(str(results["backtest_module_sha256"]))

        per_run[name] = {
            "games": len(game_ids),
            "replay_identity": identity,
            "divergent": divergent,
            "wrong_model_trials": len(wrong),
            "vacuous_trials": vacuous,
            "rejected_trials": len(rejected),
            "rejection_fraction": rejection,
            "per_class": per_class,
            "control_trials": len(controls),
            "control_accepted": accepted,
            "correct_model_acceptance_fraction": acceptance,
            "inconsistent_certifications": inconsistent,
            "history_length_checked_equal_length_all": results[
                "history_length_checked_equal_length_all"
            ],
            "backtest_limits": limits,
            "backtest_module_sha256": results["backtest_module_sha256"],
        }
    if not runs:
        problems.append(f"no completed run under {_rel(artifacts_root)}")
    if len(module_digests) > 1:
        problems.append(f"backtest_module_sha256 differs across runs: {sorted(module_digests)}")
    return CheckResult(
        "backtest_rejection",
        passed=bool(runs) and not problems,
        observed={"runs": per_run, "live_modules": live, "problems": problems},
        threshold={
            "backtest_wrong_model_trials_min": wrong_min,
            "backtest_control_trials_min": control_min,
            "backtest_mutation_classes_min": classes_min,
            "backtest_trials_per_class_min": per_class_min,
            "backtest_vacuous_trials_max": vacuous_max,
            "backtest_rejection_fraction_min": rejection_min,
            "backtest_correct_model_acceptance_min": acceptance_min,
            "backtest_history_min_length": history_min,
            "backtest_mismatches_for_certification_max": mismatch_max,
            "backtest_must_cover_full_history": full_history,
            "public_games_total": games_total,
            "replay_final_frame_identity_min": identity_min,
            "replay_divergent_games_max": divergent_max,
            "g1_history_run_sha256sums_sha256": threshold(
                prereg, "g1_history_run_sha256sums_sha256"
            ),
            "backtest_limits": limits_expected,
        },
        evidence=evidence,
    )


# --------------------------------------------------------------------------- G3 graded set
#
# The E300-set checks of preregistration/G3.yaml verification.checks_in_order, evaluated over
# the graded root: artifacts/E300_ref/ under G3.yaml alone, or the successor's
# graded_experiment.artifacts_root (artifacts/E304_ref/) when preregistration/G3b.yaml exists
# (G3.yaml cost_preflight.decision_rule names the successor; G3b.yaml
# verification.how_the_graded_set_is_verified says how the two files combine: the G3
# thresholds stay in force, exactly the keys listed under thresholds_overriding_g3 are
# replaced, the successor's own operational caps are read from the successor, and both
# digests are recorded in the report). Every number is read through ``threshold``; the
# successor's numbers through ``threshold(successor, ...)``.

G3_SUCCESSOR_GATE = "G3b"

ROLE_PREFLIGHT_GRADED = "preflight_graded"
ROLE_GRADED = "graded"
ROLE_FAILED = "failed"
TRANSITION_SOURCE_PLAN = "plan"
PLAN_OUTCOME_FOUND = "found"
HYPOTHESIS_EVENT_PROPOSED = "proposed"
HYPOTHESIS_EVENT_DECERTIFIED = "decertified"

G3_MODEL_CALL_KEYS: tuple[str, ...] = (
    "call_index",
    "purpose",
    "model_identifier_sent",
    "effort",
    "cwd",
    "tools_disabled",
    "prompt_path",
    "prompt_sha256",
    "response_path",
    "response_sha256",
    "tokens_by_kind",
    "wallclock_seconds",
)
G3_PLAN_KEYS: tuple[str, ...] = (
    "plan_index",
    "hypothesis_id",
    "outcome",
    "certification_history_length",
    "step_index_at_plan",
    "actions",
)
G3_BACKTEST_KEYS: tuple[str, ...] = (
    "hypothesis_id",
    "certified",
    "mismatches",
    "history_length",
    "history_length_checked",
    "failure_kind",
    "backtest_module_sha256",
)
G3_HYPOTHESIS_KEYS: tuple[str, ...] = ("hypothesis_id", "event")
G3_E300_TRANSITION_KEYS: tuple[str, ...] = (
    "step_index",
    "action",
    "data",
    "levels_completed",
    "state",
    "frame_sha256",
    "source",
    "hypothesis_id",
    "plan_index",
    "predicted_observation_sha256",
)
G3_E300_RESULTS_KEYS: tuple[str, ...] = (
    "game_id",
    "stem",
    "seed",
    "win_levels",
    "levels_completed",
    "final_state",
    "final_frame_sha256",
    "stop_reason",
    "actions_total",
    "levels",
    "official_baseline_actions",
    "action_budget_multiplier",
    "rhae_environment_score",
    "model_calls",
    "tokens_by_kind",
    "tokens_total",
    "model_wallclock_seconds_total",
    "hypotheses_proposed",
    "hypotheses_certified",
    "plans_searched",
    "plans_executed",
    "resumptions",
    "backtest_module_sha256",
    "prompt_hash",
)
# The five E304 config lines that differ from E303 (G3b.yaml graded_experiment.derived_from),
# as config paths bound to the successor threshold that fixes each value. The code owns the
# mapping from a config key to a threshold name, never the value.
G3_SUCCESSOR_CONFIG_LINES: tuple[tuple[str, str], ...] = (
    ("experiment_id", "experiment_id"),
    ("wallclock_limit_seconds", "wallclock_per_invocation_seconds"),
    ("runner_params.planner.max_nodes", "planner_max_nodes"),
    ("runner_params.spend_control.calls_per_run_max", "calls_per_run_max"),
    (
        "runner_params.spend_control.model_wallclock_per_run_seconds",
        "model_wallclock_per_run_seconds",
    ),
)
G3_SUCCESSOR_PLANNER_THRESHOLDS: tuple[tuple[str, str], ...] = (
    ("max_depth", "planner_max_depth"),
    ("max_nodes", "planner_max_nodes"),
    ("click_grid_step", "planner_click_grid_step"),
    ("click_points", "planner_click_points"),
)


def load_g3_successor(root: Path = ROOT) -> tuple[dict[str, Any], Path, str] | None:
    """The successor pre-registration for the graded G3 set, when it exists."""
    if not (root / "preregistration" / f"{G3_SUCCESSOR_GATE}.yaml").exists():
        return None
    return load_preregistration(G3_SUCCESSOR_GATE, root)


def g3_overriding_keys(successor: dict[str, Any]) -> list[str]:
    """The G3 threshold keys the successor replaces: the first token of each listed item."""
    raw = successor.get("thresholds_overriding_g3")
    if not isinstance(raw, list) or not raw:
        raise PreregistrationError("successor pre-registration lacks thresholds_overriding_g3")
    keys: list[str] = []
    for item in raw:
        tokens = str(item).split()
        if not tokens:
            raise PreregistrationError("thresholds_overriding_g3 has an empty item")
        keys.append(tokens[0])
    return keys


def apply_g3_overlay(
    prereg: dict[str, Any], successor: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """The G3 pre-registration with exactly the overriding keys replaced by the successor's.

    Returns the view and ``{key: {"g3": old, "successor": new}}``. A key the successor names
    but G3 lacks, or that the successor does not itself fix, is a pre-registration error.
    """
    thresholds = dict(prereg["thresholds"])
    overrides: dict[str, dict[str, Any]] = {}
    for key in g3_overriding_keys(successor):
        if key not in thresholds:
            raise PreregistrationError(f"thresholds_overriding_g3 names {key}, which G3 lacks")
        new = threshold(successor, key)
        overrides[key] = {"g3": thresholds[key], "successor": new}
        thresholds[key] = new
    return {**prereg, "thresholds": thresholds}, overrides


@dataclass(frozen=True)
class GradedExperiment:
    """Where the graded game-runs live and how their run set is labelled."""

    experiment_id: str
    artifacts_root: Path
    run_set_manifest: Path
    config_path: Path
    preflight_stems: tuple[str, ...]
    roles: tuple[str, ...]


def _required_str(mapping: dict[str, Any], key: str, where: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PreregistrationError(f"{where}.{key} missing")
    return value.strip()


def g3_graded_experiment(
    prereg: dict[str, Any], successor: dict[str, Any] | None, root: Path = ROOT
) -> GradedExperiment:
    if successor is None:
        exp = section(prereg, "experiment")
        run_set = exp.get("run_set_manifest")
        if not isinstance(run_set, dict):
            raise PreregistrationError("experiment.run_set_manifest missing")
        games = section(prereg, "cost_preflight").get("games")
        if not isinstance(games, list):
            raise PreregistrationError("cost_preflight.games missing")
        return GradedExperiment(
            experiment_id=_required_str(exp, "experiment_id", "experiment"),
            artifacts_root=root
            / _required_str(section(prereg, "verification"), "artifacts_root", "verification"),
            run_set_manifest=root / _required_str(run_set, "file", "experiment.run_set_manifest"),
            config_path=root / _required_str(exp, "config", "experiment"),
            preflight_stems=tuple(str(g) for g in games),
            roles=(ROLE_PREFLIGHT_GRADED, ROLE_GRADED, ROLE_FAILED),
        )
    exp = section(successor, "graded_experiment")
    run_set = exp.get("run_set_manifest")
    if not isinstance(run_set, dict):
        raise PreregistrationError("graded_experiment.run_set_manifest missing")
    return GradedExperiment(
        experiment_id=_required_str(exp, "experiment_id", "graded_experiment"),
        artifacts_root=root / _required_str(exp, "artifacts_root", "graded_experiment"),
        run_set_manifest=root
        / _required_str(run_set, "file", "graded_experiment.run_set_manifest"),
        config_path=root / _required_str(exp, "config", "graded_experiment"),
        preflight_stems=(),
        roles=(ROLE_GRADED, ROLE_FAILED),
    )


def _g3_extra_artifacts(prereg: dict[str, Any]) -> tuple[str, ...]:
    """``experiment.extra_artifacts`` as file names (first token, trailing slash dropped)."""
    raw = section(prereg, "experiment").get("extra_artifacts")
    if not isinstance(raw, list) or not raw:
        raise PreregistrationError("experiment.extra_artifacts missing")
    names = tuple(str(item).split()[0].rstrip("/") for item in raw if str(item).split())
    if len(names) != len(raw):
        raise PreregistrationError("experiment.extra_artifacts has an empty item")
    return names


def _g3_environments_dir(prereg: dict[str, Any], root: Path) -> Path:
    return root / _required_str(section(prereg, "experiment"), "environments_dir", "experiment")


def _cache_manifest_games(prereg: dict[str, Any], root: Path) -> dict[str, str]:
    """``{stem: game_id}`` from the committed cache manifest the thresholds lock."""
    doc = _load_json(root / _g3_cache_manifest_path(prereg))
    games = doc.get("games") if isinstance(doc, dict) else None
    out: dict[str, str] = {}
    for rec in games if isinstance(games, list) else []:
        if isinstance(rec, dict) and isinstance(rec.get("stem"), str):
            out[str(rec["stem"])] = str(rec.get("game_id"))
    return out


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _run_row(run: Path) -> dict[str, Any]:
    """One run directory as the run set manifest must describe it (recomputed here)."""
    manifest = _load_manifest(run) or {}
    results: dict[str, Any] = {}
    if (run / "results.json").exists():
        try:
            results = _runner_results(_load_json(run / "results.json"))
        except ValueError:
            results = {}
    stem = results.get("stem") if isinstance(results.get("stem"), str) else None
    if stem is None:
        params = _read_yaml_mapping(run / "resolved_config.yaml").get("runner_params")
        if isinstance(params, dict) and isinstance(params.get("game"), str):
            stem = str(params["game"])
    sums = run / "SHA256SUMS"
    status = manifest.get("completion_status")
    return {
        "run_id": run.name,
        "path": run,
        "stem": stem,
        "game_id": results.get("game_id") if isinstance(results.get("game_id"), str) else None,
        "completion_status": status if isinstance(status, str) else None,
        "sealed": sums.is_file(),
        "sha256sums_sha256": sha256_file(sums) if sums.is_file() else None,
        "timestamp_utc": manifest.get("timestamp_utc"),
    }


def _assign_sets_and_roles(rows: list[dict[str, Any]], preflight_stems: tuple[str, ...]) -> None:
    """The run set rule of G3.yaml experiment.run_set_manifest, applied mechanically.

    ``set_index`` is one more than the number of completed, sealed runs of the same stem that
    precede the run by run_id; ``role`` is ``failed`` iff the run is not completed and sealed
    (a completed run is never labelled failed), else ``preflight_graded`` for the pre-flight
    stems (E300 only) and ``graded`` otherwise.
    """
    completed_before: dict[str, int] = {}
    for row in sorted(rows, key=lambda r: str(r["run_id"])):
        key = row["stem"] if isinstance(row["stem"], str) else "?"
        row["set_index"] = completed_before.get(key, 0) + 1
        completed = row["completion_status"] == COMPLETED_STATUS and bool(row["sealed"])
        if not completed:
            row["role"] = ROLE_FAILED
            continue
        row["role"] = ROLE_PREFLIGHT_GRADED if key in preflight_stems else ROLE_GRADED
        completed_before[key] = completed_before.get(key, 0) + 1


@dataclass
class GradedSet:
    """The run set the verifier grades: the highest-numbered complete set, else the highest
    set present (incomplete, so that per-run checks still report on what exists)."""

    set_index: int
    runs: list[Path]
    runs_by_stem: dict[str, Path]
    complete: bool
    missing_stems: list[str]
    duplicate_stems: list[str]
    unknown_stems: list[str]
    rows: list[dict[str, Any]]
    sets: dict[int, dict[str, Any]]
    stems_required: list[str]


def g3_graded_set(
    prereg: dict[str, Any], experiment: GradedExperiment, root: Path = ROOT
) -> GradedSet:
    per_game = int(threshold(prereg, "graded_runs_per_game"))
    stems_required = sorted(_cache_manifest_games(prereg, root))
    rows = [_run_row(run) for run in _run_dirs(experiment.artifacts_root)]
    _assign_sets_and_roles(rows, experiment.preflight_stems)
    sets: dict[int, dict[str, Any]] = {}
    for row in rows:
        entry = sets.setdefault(
            int(row["set_index"]), {"graded": [], "failed_run_ids": [], "complete": False}
        )
        if row["role"] == ROLE_FAILED:
            entry["failed_run_ids"].append(row["run_id"])
        else:
            entry["graded"].append(row)
    for entry in sets.values():
        counts: dict[str, int] = {}
        for row in entry["graded"]:
            counts[str(row["stem"])] = counts.get(str(row["stem"]), 0) + 1
        entry["missing_stems"] = [s for s in stems_required if counts.get(s, 0) < per_game]
        entry["duplicate_stems"] = sorted(s for s, n in counts.items() if n > per_game)
        entry["unknown_stems"] = sorted(s for s in counts if s not in stems_required)
        entry["complete"] = (
            not entry["missing_stems"]
            and not entry["duplicate_stems"]
            and not entry["unknown_stems"]
            and bool(stems_required)
        )
    complete_indices = [i for i, e in sets.items() if e["complete"]]
    if complete_indices:
        chosen = max(complete_indices)
    elif sets:
        chosen = max(sets)
    else:
        chosen = 0
    entry = sets.get(chosen, {"graded": [], "missing_stems": list(stems_required)})
    graded_rows = sorted(entry["graded"], key=lambda r: (str(r["stem"]), str(r["run_id"])))
    return GradedSet(
        set_index=chosen,
        runs=[row["path"] for row in graded_rows],
        runs_by_stem={str(row["stem"]): row["path"] for row in graded_rows},
        complete=bool(entry.get("complete")),
        missing_stems=list(entry.get("missing_stems", stems_required)),
        duplicate_stems=list(entry.get("duplicate_stems", [])),
        unknown_stems=list(entry.get("unknown_stems", [])),
        rows=rows,
        sets=sets,
        stems_required=stems_required,
    )


def _set_summary(graded: GradedSet) -> dict[str, Any]:
    return {
        "set_index": graded.set_index,
        "complete": graded.complete,
        "graded_runs": len(graded.runs),
        "missing_stems": graded.missing_stems,
        "duplicate_stems": graded.duplicate_stems,
        "unknown_stems": graded.unknown_stems,
        "sets": {
            str(i): {
                "graded_runs": len(e["graded"]),
                "failed_run_ids": sorted(e["failed_run_ids"]),
                "complete": e["complete"],
            }
            for i, e in sorted(graded.sets.items())
        },
    }


def _excluded_diagnostic_runs(successor: dict[str, Any]) -> list[tuple[str, str, str]]:
    """``(experiment dir, stem, run_id)`` for every excluded diagnostic run the successor lists."""
    block = section(successor, "diagnostic_runs_excluded_from_grading")
    raw = block.get("runs")
    if not isinstance(raw, list) or not raw:
        raise PreregistrationError("diagnostic_runs_excluded_from_grading.runs missing")
    out: list[tuple[str, str, str]] = []
    for item in raw:
        tokens = str(item).split()
        if len(tokens) < 3:
            raise PreregistrationError(
                f"excluded diagnostic run {item!r} is not '<exp> <stem> <run_id>'"
            )
        out.append((tokens[0], tokens[1], tokens[2]))
    return out


def _load_run(
    run: Path, problems: list[str]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """(manifest, results.json top level, results.json['results']) with problems recorded."""
    manifest = _load_manifest(run) or {}
    if not manifest:
        problems.append(f"{run.name}: manifest.json missing or not a mapping")
    try:
        top = _load_json(run / "results.json")
    except (OSError, ValueError) as exc:
        problems.append(f"{run.name}: results.json unreadable: {exc}")
        top = {}
    if not isinstance(top, dict):
        problems.append(f"{run.name}: results.json is not a mapping")
        top = {}
    results = _runner_results(top)
    missing = [k for k in G3_E300_RESULTS_KEYS if k not in results]
    if missing:
        problems.append(f"{run.name}: results.json lacks {missing}")
    return manifest, top, results


def _load_json_mapping(path: Path, problems: list[str], what: str) -> dict[str, Any]:
    try:
        doc = _load_json(path)
    except (OSError, ValueError) as exc:
        problems.append(f"{path.parent.name}: {what} unreadable: {exc}")
        return {}
    if not isinstance(doc, dict):
        problems.append(f"{path.parent.name}: {what} is not a mapping")
        return {}
    return doc


def _runner_params(run: Path) -> dict[str, Any]:
    params = _read_yaml_mapping(run / "resolved_config.yaml").get("runner_params")
    return params if isinstance(params, dict) else {}


def check_run_set_manifest(
    prereg: dict[str, Any],
    successor: dict[str, Any] | None,
    experiment: GradedExperiment,
    graded: GradedSet,
    root: Path = ROOT,
) -> CheckResult:
    """The committed run set manifest lists every run directory exactly as recomputed here,
    the graded set is complete, no completed run is labelled failed, and the set count and
    failed re-runs stay within their ceilings (G3.yaml experiment.run_set_manifest; G3b.yaml
    graded_experiment.run_set_manifest and diagnostic_runs_excluded_from_grading)."""
    games_required = int(threshold(prereg, "graded_games_required"))
    per_game = int(threshold(prereg, "graded_runs_per_game"))
    sets_max = int(threshold(prereg, "graded_sets_max"))
    unlisted_max = int(threshold(prereg, "unlisted_run_dirs_max"))
    labelled_failed_max = int(threshold(prereg, "completed_runs_labelled_failed_max"))
    thresholds: dict[str, Any] = {
        "graded_games_required": games_required,
        "graded_runs_per_game": per_game,
        "graded_sets_max": sets_max,
        "unlisted_run_dirs_max": unlisted_max,
        "completed_runs_labelled_failed_max": labelled_failed_max,
        "roles": list(experiment.roles),
    }
    problems: list[str] = []
    manifest_path = experiment.run_set_manifest
    listed: dict[str, dict[str, Any]] = {}
    doc: dict[str, Any] = {}
    if not manifest_path.exists():
        problems.append(f"{_rel(manifest_path)} does not exist (commit it before verifying)")
    else:
        doc = _load_json_mapping(manifest_path, problems, _rel(manifest_path))
        runs_raw = doc.get("runs")
        if not isinstance(runs_raw, list):
            problems.append(f"{_rel(manifest_path)}: runs is not a list")
            runs_raw = []
        for i, rec in enumerate(runs_raw):
            if not isinstance(rec, dict) or not isinstance(rec.get("run_id"), str):
                problems.append(f"{_rel(manifest_path)}: runs[{i}] lacks run_id")
                continue
            listed[str(rec["run_id"])] = rec
        if doc.get("experiment_id") != experiment.experiment_id:
            problems.append(
                f"{_rel(manifest_path)}: experiment_id {doc.get('experiment_id')!r} != "
                f"{experiment.experiment_id!r}"
            )
    recomputed = {str(row["run_id"]): row for row in graded.rows}
    unlisted = sorted(set(recomputed) - set(listed))
    if len(unlisted) > unlisted_max:
        problems.append(f"run directories not listed: {unlisted}")
    for run_id in sorted(set(listed) - set(recomputed)):
        problems.append(
            f"listed run {run_id} has no directory under {_rel(experiment.artifacts_root)}"
        )
    labelled_failed = 0
    for run_id, rec in sorted(listed.items()):
        row = recomputed.get(run_id)
        if row is None:
            continue
        role = rec.get("role")
        if role not in experiment.roles:
            problems.append(f"{run_id}: role {role!r} not in {list(experiment.roles)}")
        for key in ("stem", "set_index", "role", "sha256sums_sha256", "completion_status"):
            if rec.get(key) != row.get(key):
                problems.append(
                    f"{run_id}: manifest {key} {rec.get(key)!r} != recomputed {row.get(key)!r}"
                )
        if role == ROLE_FAILED and row["completion_status"] == COMPLETED_STATUS and row["sealed"]:
            labelled_failed += 1
    if labelled_failed > labelled_failed_max:
        problems.append(f"{labelled_failed} completed runs labelled failed")
    set_indices = sorted(i for i, e in graded.sets.items() if e["graded"])
    if len(set_indices) > sets_max:
        problems.append(f"{len(set_indices)} sets with graded runs > graded_sets_max {sets_max}")
    if len(graded.stems_required) != games_required:
        problems.append(
            f"cache manifest lists {len(graded.stems_required)} stems, "
            f"graded_games_required {games_required}"
        )
    if not graded.complete:
        problems.append(
            f"no complete set: set {graded.set_index} has {len(graded.runs)} graded runs, "
            f"missing {graded.missing_stems}, duplicates {graded.duplicate_stems}, "
            f"unknown {graded.unknown_stems}"
        )
    elif len(graded.runs) != games_required * per_game:
        problems.append(f"graded set holds {len(graded.runs)} runs, required {games_required}")
    excluded_hits: list[str] = []
    if successor is not None:
        reruns_max = int(threshold(successor, "failed_reruns_per_game_max"))
        thresholds["failed_reruns_per_game_max"] = reruns_max
        failed_by_stem: dict[str, int] = {}
        for row in graded.rows:
            if row["role"] == ROLE_FAILED:
                key = str(row["stem"])
                failed_by_stem[key] = failed_by_stem.get(key, 0) + 1
        for stem, n in sorted(failed_by_stem.items()):
            if n > reruns_max:
                problems.append(
                    f"{stem}: {n} failed runs > failed_reruns_per_game_max {reruns_max}"
                )
        excluded_ids = {run_id for _, _, run_id in _excluded_diagnostic_runs(successor)}
        excluded_hits = sorted(excluded_ids & (set(listed) | set(recomputed)))
        if excluded_hits:
            problems.append(f"excluded diagnostic runs present in the graded set: {excluded_hits}")
    return CheckResult(
        "run_set_manifest",
        passed=not problems,
        observed={
            "manifest": _rel(manifest_path),
            "manifest_sha256": sha256_file(manifest_path) if manifest_path.exists() else None,
            "listed_runs": len(listed),
            "run_directories": len(recomputed),
            "unlisted": unlisted,
            "completed_labelled_failed": labelled_failed,
            "excluded_diagnostic_runs_present": excluded_hits,
            **_set_summary(graded),
            "problems": problems,
        },
        threshold=thresholds,
        evidence=[_rel(manifest_path), _rel(experiment.artifacts_root)],
    )


def check_official_baselines_used(
    prereg: dict[str, Any], experiment: GradedExperiment, graded: GradedSet, root: Path = ROOT
) -> CheckResult:
    """Every graded run scores against the cached metadata.json baseline_actions of the exact
    cached game version, level for level, and the RHAE adapter still delegates to the toolkit."""
    must_match = bool(threshold(prereg, "official_baselines_must_match_metadata"))
    levels_total = int(threshold(prereg, "public_levels_total"))
    env_dir = _g3_environments_dir(prereg, root)
    cache_games = _cache_manifest_games(prereg, root)
    adapter = root / "src" / "arc_plasticity" / "evaluation" / "rhae.py"
    adapter_text = adapter.read_text(encoding="utf-8") if adapter.exists() else ""
    delegates = (
        "from arc_agi.scorecard import EnvironmentScoreCalculator" in adapter_text
        and "EnvironmentScoreCalculator(" in adapter_text
    )
    problems: list[str] = []
    if not delegates:
        problems.append(f"{_rel(adapter)} no longer delegates to arc_agi.scorecard")
    per_run: dict[str, Any] = {}
    levels_seen = 0
    for run in graded.runs:
        _, _, results = _load_run(run, problems)
        accounting = _load_json_mapping(
            run / "level_accounting.json", problems, "level_accounting.json"
        )
        rhae_doc = _load_json_mapping(run / "rhae.json", problems, "rhae.json")
        game_id = str(results.get("game_id"))
        stem = str(results.get("stem"))
        if cache_games.get(stem) != game_id:
            problems.append(
                f"{run.name}: game_id {game_id} is not the cached version {cache_games.get(stem)!r}"
            )
        try:
            baselines = la.load_official_baselines(env_dir, game_id)
        except la.LevelAccountingError as exc:
            problems.append(f"{run.name}: {exc}")
            baselines = []
        levels_seen += len(baselines)
        recorded = accounting.get("official_baseline_actions")
        if must_match and recorded != baselines:
            problems.append(
                f"{run.name}: level_accounting official_baseline_actions {recorded} != metadata {baselines}"
            )
        if must_match and results.get("official_baseline_actions") != baselines:
            problems.append(f"{run.name}: results official_baseline_actions != metadata")
        if must_match and rhae_doc.get("official_baseline_actions") != baselines:
            problems.append(f"{run.name}: rhae.json official_baseline_actions != metadata")
        if results.get("win_levels") != len(baselines):
            problems.append(
                f"{run.name}: win_levels {results.get('win_levels')!r} != {len(baselines)} baselines"
            )
        for name, doc in (
            ("level_accounting.json", accounting),
            ("rhae.json", rhae_doc),
            ("results.json", results),
        ):
            levels = doc.get("levels")
            if not isinstance(levels, list) or len(levels) != len(baselines):
                problems.append(
                    f"{run.name}: {name} has {len(levels) if isinstance(levels, list) else 'no'} levels, metadata {len(baselines)}"
                )
                continue
            for i, (level, h) in enumerate(zip(levels, baselines, strict=True), start=1):
                if (
                    not isinstance(level, dict)
                    or level.get("level") != i
                    or level.get("official_baseline_actions") != h
                ):
                    problems.append(f"{run.name}: {name} level {i} does not carry baseline {h}")
        canonical = str(rhae_doc.get("canonical_scoring_baseline") or "")
        if "metadata.json" not in canonical:
            problems.append(f"{run.name}: rhae.json canonical_scoring_baseline {canonical!r}")
        per_run[run.name] = {"game_id": game_id, "baselines": baselines}
    if graded.complete and levels_seen != levels_total:
        problems.append(
            f"graded set covers {levels_seen} levels, public_levels_total {levels_total}"
        )
    if not graded.runs:
        problems.append("no graded run")
    return CheckResult(
        "official_baselines_used",
        passed=not problems,
        observed={
            "runs": per_run,
            "levels_seen": levels_seen,
            "adapter_delegates": delegates,
            "set_complete": graded.complete,
            "problems": problems,
        },
        threshold={
            "official_baselines_must_match_metadata": must_match,
            "public_levels_total": levels_total,
            "environments_dir": _rel(env_dir),
        },
        evidence=[_rel(adapter), *(_rel(r / "level_accounting.json") for r in graded.runs)],
    )


def _sorted_transitions(run: Path, problems: list[str]) -> list[dict[str, Any]]:
    records = _read_jsonl_records(run, "transitions.jsonl", G3_E300_TRANSITION_KEYS, problems)
    records.sort(key=lambda r: int(r["step_index"]))
    if [int(r["step_index"]) for r in records] != list(range(1, len(records) + 1)):
        problems.append(f"{run.name}: transitions.jsonl step_index is not 1..n")
    return records


def _first_uncompleted_level(levels: list[Any]) -> dict[str, Any] | None:
    for level in levels:
        if isinstance(level, dict) and not level.get("completed"):
            return level
    return None


def check_action_budget_enforced(
    prereg: dict[str, Any], experiment: GradedExperiment, graded: GradedSet
) -> CheckResult:
    """Per level, attributed actions never exceed multiplier x baseline; the accounting is
    rebuilt from transitions.jsonl under level_accounting_rule and must equal the run's own;
    the stop reason is one of per_game_stop_rule's and the level-budget stop is exact."""
    multiplier = int(threshold(prereg, "action_budget_multiplier"))
    over_max = int(threshold(prereg, "per_level_actions_over_budget_max"))
    problems: list[str] = []
    per_run: dict[str, Any] = {}
    for run in graded.runs:
        manifest, _, results = _load_run(run, problems)
        accounting = _load_json_mapping(
            run / "level_accounting.json", problems, "level_accounting.json"
        )
        transitions = _sorted_transitions(run, problems)
        levels = accounting.get("levels") if isinstance(accounting.get("levels"), list) else []
        baselines = accounting.get("official_baseline_actions")
        if (
            accounting.get("action_budget_multiplier") != multiplier
            or results.get("action_budget_multiplier") != multiplier
        ):
            problems.append(f"{run.name}: action_budget_multiplier is not {multiplier}")
        over = 0
        attributed_total = 0
        for level in levels:
            if not isinstance(level, dict):
                problems.append(f"{run.name}: malformed level record")
                continue
            h = int(level.get("official_baseline_actions") or 0)
            attributed = int(level.get("actions_attributed") or 0)
            attributed_total += attributed
            if level.get("budget") != multiplier * h:
                problems.append(
                    f"{run.name}: level {level.get('level')} budget {level.get('budget')!r} != {multiplier * h}"
                )
            if attributed > multiplier * h:
                over += 1
        if over > over_max:
            problems.append(f"{run.name}: {over} levels over budget (max {over_max})")
        if accounting.get("over_budget_levels") not in ([], None) or results.get(
            "over_budget_levels"
        ) not in ([], None):
            problems.append(
                f"{run.name}: over_budget_levels recorded: {accounting.get('over_budget_levels')}"
            )
        actions_total = results.get("actions_total")
        if not (
            attributed_total == actions_total == accounting.get("actions_total") == len(transitions)
        ):
            problems.append(
                f"{run.name}: attributed {attributed_total}, actions_total {actions_total!r}, "
                f"accounting {accounting.get('actions_total')!r}, transitions {len(transitions)} disagree"
            )
        if (
            isinstance(baselines, list)
            and baselines
            and manifest.get("action_budget") != multiplier * sum(int(b) for b in baselines)
        ):
            problems.append(
                f"{run.name}: manifest action_budget {manifest.get('action_budget')!r} != {multiplier} x sum(baselines)"
            )
        stop_reason = str(results.get("stop_reason"))
        if stop_reason not in la.STOP_REASONS:
            problems.append(
                f"{run.name}: stop_reason {stop_reason!r} is not one of {la.STOP_REASONS}"
            )
        if stop_reason == la.STOP_STEP_FAILED:
            problems.append(
                f"{run.name}: stop_reason step_failed is a run failure, not a graded run"
            )
        if stop_reason == la.STOP_LEVEL_BUDGET_EXHAUSTED:
            current = _first_uncompleted_level(levels)
            if current is None or current.get("actions_attributed") != current.get("budget"):
                problems.append(
                    f"{run.name}: level_budget_exhausted but the current level is not at its budget"
                )
        rebuilt_equal = None
        if (
            isinstance(baselines, list)
            and baselines
            and transitions
            and stop_reason in la.STOP_REASONS
        ):
            try:
                rebuilt = la.accounting_from_log(
                    [int(b) for b in baselines],
                    multiplier,
                    transitions,
                    game_id=str(results.get("game_id")),
                )
                rebuilt.stop(stop_reason)
                rebuilt_equal = rebuilt.to_dict() == accounting
            except la.LevelAccountingError as exc:
                problems.append(f"{run.name}: accounting cannot be rebuilt: {exc}")
                rebuilt_equal = False
            if rebuilt_equal is False:
                problems.append(
                    f"{run.name}: level_accounting.json != accounting rebuilt from transitions.jsonl"
                )
        if results.get("levels") != levels:
            problems.append(f"{run.name}: results.json levels != level_accounting.json levels")
        per_run[run.name] = {
            "stop_reason": stop_reason,
            "actions_total": actions_total,
            "levels_completed": results.get("levels_completed"),
            "over_budget_levels": over,
            "rebuilt_from_transitions_equal": rebuilt_equal,
        }
    if not graded.runs:
        problems.append("no graded run")
    return CheckResult(
        "action_budget_enforced",
        passed=not problems,
        observed={"runs": per_run, "problems": problems},
        threshold={
            "action_budget_multiplier": multiplier,
            "per_level_actions_over_budget_max": over_max,
            "stop_reasons": list(la.STOP_REASONS),
        },
        evidence=[
            _rel(r / f) for r in graded.runs for f in ("level_accounting.json", "transitions.jsonl")
        ],
    )


def check_replay_final_frame_identity_e300(
    prereg: dict[str, Any], experiment: GradedExperiment, graded: GradedSet, root: Path = ROOT
) -> CheckResult:
    """Every graded run's transitions.jsonl, replayed offline in this process through a fresh
    cached environment, reproduces the recorded final frame digest and final state (as G1)."""
    identity_min = float(threshold(prereg, "replay_final_frame_identity_min"))
    divergent_max = int(threshold(prereg, "replay_divergent_games_max"))
    net_allowed = int(threshold(prereg, "network_calls_allowed"))
    expected_seed = section(prereg, "experiment").get("seed")
    if expected_seed is None:
        raise PreregistrationError("experiment.seed missing")
    env_dir = _g3_environments_dir(prereg, root)
    problems: list[str] = []
    divergent: list[str] = []
    per_run: dict[str, Any] = {}
    attempted = 0
    with NetworkGuard(net_allowed) as guard:
        for run in graded.runs:
            manifest, _, results = _load_run(run, problems)
            transitions = _sorted_transitions(run, problems)
            game_id = str(results.get("game_id"))
            if manifest.get("seed") != expected_seed or results.get("seed") != expected_seed:
                problems.append(
                    f"{run.name}: seed {manifest.get('seed')!r}/{results.get('seed')!r} != {expected_seed!r}"
                )
            if len(transitions) != results.get("actions_total"):
                problems.append(
                    f"{run.name}: {len(transitions)} transitions but actions_total {results.get('actions_total')!r}"
                )
            recorded = results.get("final_frame_sha256")
            if transitions and transitions[-1].get("frame_sha256") != recorded:
                problems.append(
                    f"{run.name}: last transition frame_sha256 != results final_frame_sha256"
                )
            attempted += 1
            row: dict[str, Any] = {
                "game_id": game_id,
                "steps": len(transitions),
                "identical": False,
            }
            try:
                actions = [arc_interface.ActionRecord.from_mapping(r) for r in transitions]
                result = arc_interface.replay_actions(env_dir, game_id, int(expected_seed), actions)
            except (
                arc_interface.EnvironmentLoadError,
                arc_interface.ReplayError,
                ValueError,
            ) as exc:
                divergent.append(run.name)
                row["reason"] = str(exc)
                per_run[run.name] = row
                continue
            row["replayed"] = result.final_digest
            row["final_state"] = result.final_state
            ok = (
                result.succeeded
                and result.final_digest == recorded
                and result.final_state == results.get("final_state")
            )
            row["identical"] = ok
            if not ok:
                divergent.append(run.name)
                row["recorded"] = recorded
                row["failed_at_step"] = result.failed_at_step
            per_run[run.name] = row
        attempts = guard.attempts
    fraction = ((attempted - len(divergent)) / attempted) if attempted else 0.0
    if attempts > net_allowed:
        problems.append(f"replay made {attempts} network attempts")
    if not graded.runs:
        problems.append("no graded run")
    passed = (
        attempted > 0
        and fraction >= identity_min
        and len(divergent) <= divergent_max
        and not problems
    )
    return CheckResult(
        "replay_final_frame_identity",
        passed=passed,
        observed={
            "runs_attempted": attempted,
            "divergent": divergent,
            "identity": fraction,
            "network_attempts": attempts,
            "runs": per_run,
            "problems": problems,
        },
        threshold={
            "replay_final_frame_identity_min": identity_min,
            "replay_divergent_games_max": divergent_max,
            "seed": expected_seed,
            "environments_dir": _rel(env_dir),
        },
        evidence=[_rel(r / f) for r in graded.runs for f in ("results.json", "transitions.jsonl")],
    )


def _metrics_value(run: Path, metric: str) -> float | None:
    path = run / "metrics.csv"
    if not path.exists():
        return None
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("metric") == metric:
                try:
                    return float(str(row.get("value")))
                except ValueError:
                    return None
    return None


def check_rhae_recomputed(
    prereg: dict[str, Any], experiment: GradedExperiment, graded: GradedSet
) -> CheckResult:
    """The primary metric: every run's environment score is recomputed through the adapter
    from level_accounting.json and must agree with results.json, rhae.json, metrics.csv and
    level_accounting.json within tolerance; the plain mean over the complete graded set is
    graded against rhae_total_min."""
    tol = float(threshold(prereg, "rhae_recompute_abs_tolerance"))
    cap = float(threshold(prereg, "rhae_level_cap")) * 100.0
    rhae_min = float(threshold(prereg, "rhae_total_min"))
    games_required = int(threshold(prereg, "graded_games_required"))
    problems: list[str] = []
    per_game: dict[str, float] = {}
    scores: list[float] = []
    for run in graded.runs:
        _, _, results = _load_run(run, problems)
        accounting = _load_json_mapping(
            run / "level_accounting.json", problems, "level_accounting.json"
        )
        rhae_doc = _load_json_mapping(run / "rhae.json", problems, "rhae.json")
        levels = accounting.get("levels") if isinstance(accounting.get("levels"), list) else []
        game_id = str(results.get("game_id"))
        try:
            outcomes = [
                rhae.LevelOutcome(
                    human_baseline_actions=int(level["official_baseline_actions"]),
                    agent_actions=int(level["actions_attributed"]),
                    completed=bool(level["completed"]),
                )
                for level in levels
            ]
            score = rhae.environment_score(outcomes, game_id=game_id)
            level_scores = rhae.level_scores(outcomes, game_id=game_id)
        except (rhae.RhaeInputError, KeyError, TypeError, ValueError) as exc:
            problems.append(f"{run.name}: level_accounting.json cannot be scored: {exc}")
            continue
        for name, value in (
            ("results.json", results.get("rhae_environment_score")),
            ("level_accounting.json", accounting.get("rhae_environment_score")),
            ("rhae.json", rhae_doc.get("rhae_environment_score")),
            ("metrics.csv", _metrics_value(run, "rhae_environment_score")),
        ):
            if not isinstance(value, int | float) or abs(float(value) - score) > tol:
                problems.append(
                    f"{run.name}: {name} rhae_environment_score {value!r} != recomputed {score}"
                )
        recorded_levels = accounting.get("rhae_level_scores")
        if (
            not isinstance(recorded_levels, list)
            or len(recorded_levels) != len(level_scores)
            or any(
                abs(float(a) - b) > tol for a, b in zip(recorded_levels, level_scores, strict=True)
            )
        ):
            problems.append(
                f"{run.name}: level_accounting rhae_level_scores != recomputed {level_scores}"
            )
        rhae_levels = rhae_doc.get("levels") if isinstance(rhae_doc.get("levels"), list) else []
        if len(rhae_levels) != len(level_scores) or any(
            not isinstance(lv, dict) or abs(float(lv.get("rhae_level_score", -1.0)) - s) > tol
            for lv, s in zip(rhae_levels, level_scores, strict=True)
        ):
            problems.append(f"{run.name}: rhae.json per-level scores != recomputed")
        if any(s > cap + tol for s in level_scores):
            problems.append(f"{run.name}: a level score exceeds the cap {cap}")
        stem = str(results.get("stem"))
        per_game[stem] = score
        scores.append(score)
    mean = rhae.total_score(scores) if scores else 0.0
    if not graded.complete or len(scores) != games_required:
        problems.append(
            f"mean over {len(scores)} runs is not a graded mean (set complete: {graded.complete})"
        )
    elif mean < rhae_min:
        problems.append(f"rhae_total_public_{games_required} {mean} < {rhae_min}")
    return CheckResult(
        "rhae_recomputed",
        passed=not problems,
        observed={
            "per_game": dict(sorted(per_game.items())),
            "runs_scored": len(scores),
            "set_complete": graded.complete,
            "rhae_total_mean": mean,
            "problems": problems,
        },
        threshold={
            "rhae_total_min": rhae_min,
            "rhae_recompute_abs_tolerance": tol,
            "rhae_level_cap_percent": cap,
            "graded_games_required": games_required,
        },
        evidence=[
            _rel(r / f)
            for r in graded.runs
            for f in ("level_accounting.json", "rhae.json", "results.json")
        ],
    )


def _cwd_outside_repo(cwd: str, root: Path) -> bool:
    try:
        path = Path(cwd).resolve()
    except OSError:
        return False
    return not (path.is_relative_to(root.resolve()) or path.is_relative_to(ROOT.resolve()))


def check_model_call_accounting(
    prereg: dict[str, Any], experiment: GradedExperiment, graded: GradedSet, root: Path = ROOT
) -> CheckResult:
    """Every model call is on record with its verbatim prompt and response (digests verified),
    the frozen identifier and effort, a cwd outside the repository and tools disabled; per run
    the calls and summed tokens stay within the ceilings and agree with results.json."""
    identifier = str(threshold(prereg, "model_identifier"))
    effort = str(threshold(prereg, "model_effort"))
    calls_max = int(threshold(prereg, "model_calls_per_game_max"))
    tokens_max = int(threshold(prereg, "tokens_per_game_max"))
    cwd_outside = bool(threshold(prereg, "model_call_cwd_must_be_outside_repo"))
    tools_disabled = bool(threshold(prereg, "model_call_tools_must_be_disabled"))
    problems: list[str] = []
    per_run: dict[str, Any] = {}
    for run in graded.runs:
        manifest, _, results = _load_run(run, problems)
        calls = _read_jsonl_records(run, "model_calls.jsonl", G3_MODEL_CALL_KEYS, problems)
        if [int(c["call_index"]) for c in calls] != list(range(1, len(calls) + 1)):
            problems.append(f"{run.name}: call_index is not 1..n")
        tokens: dict[str, int] = {}
        wallclock = 0.0
        for call in calls:
            idx = call["call_index"]
            for kind in ("prompt", "response"):
                path = run / str(call[f"{kind}_path"])
                if not path.is_file():
                    problems.append(
                        f"{run.name}: call {idx} {kind} file {call[f'{kind}_path']} missing"
                    )
                elif sha256_file(path) != str(call[f"{kind}_sha256"]).lower():
                    problems.append(f"{run.name}: call {idx} {kind} sha256 mismatch")
            if call["model_identifier_sent"] != identifier:
                problems.append(
                    f"{run.name}: call {idx} identifier {call['model_identifier_sent']!r}"
                )
            if call["effort"] != effort:
                problems.append(f"{run.name}: call {idx} effort {call['effort']!r}")
            if cwd_outside and not _cwd_outside_repo(str(call["cwd"]), root):
                problems.append(
                    f"{run.name}: call {idx} cwd {call['cwd']!r} is inside the repository"
                )
            if tools_disabled and call["tools_disabled"] is not True:
                problems.append(f"{run.name}: call {idx} tools_disabled {call['tools_disabled']!r}")
            by_kind = call["tokens_by_kind"] if isinstance(call["tokens_by_kind"], dict) else {}
            for kind, n in by_kind.items():
                tokens[str(kind)] = tokens.get(str(kind), 0) + int(n)
            wallclock += float(call["wallclock_seconds"])
        total = sum(tokens.values())
        if len(calls) > calls_max:
            problems.append(f"{run.name}: {len(calls)} calls > {calls_max}")
        if not (len(calls) == results.get("model_calls") == manifest.get("model_calls")):
            problems.append(
                f"{run.name}: model_calls {results.get('model_calls')!r}/{manifest.get('model_calls')!r} != {len(calls)} records"
            )
        if (
            manifest.get("model_calls_allowed") != calls_max
            or results.get("model_calls_per_game_max") != calls_max
        ):
            problems.append(
                f"{run.name}: model_calls_allowed {manifest.get('model_calls_allowed')!r} != {calls_max}"
            )
        if total > tokens_max:
            problems.append(f"{run.name}: {total} tokens > {tokens_max}")
        if (
            results.get("tokens_per_game_max") != tokens_max
            or manifest.get("token_budget") != tokens_max
        ):
            problems.append(f"{run.name}: tokens_per_game_max/token_budget != {tokens_max}")
        if results.get("tokens_by_kind") != tokens or results.get("tokens_total") != total:
            problems.append(
                f"{run.name}: results tokens {results.get('tokens_by_kind')!r} != summed {tokens}"
            )
        recorded_wall = results.get("model_wallclock_seconds_total")
        if (
            not isinstance(recorded_wall, int | float)
            or abs(float(recorded_wall) - wallclock) > 1e-3
        ):
            problems.append(
                f"{run.name}: model_wallclock_seconds_total {recorded_wall!r} != summed {wallclock}"
            )
        if (
            results.get("model_identifier") != identifier
            or manifest.get("model_identifier") != identifier
        ):
            problems.append(f"{run.name}: model_identifier is not {identifier!r}")
        if results.get("model_effort") != effort:
            problems.append(f"{run.name}: model_effort {results.get('model_effort')!r}")
        per_run[run.name] = {
            "calls": len(calls),
            "tokens": tokens,
            "tokens_total": total,
            "model_wallclock_seconds": wallclock,
        }
    if not graded.runs:
        problems.append("no graded run")
    return CheckResult(
        "model_call_accounting",
        passed=not problems,
        observed={"runs": per_run, "problems": problems},
        threshold={
            "model_identifier": identifier,
            "model_effort": effort,
            "model_calls_per_game_max": calls_max,
            "tokens_per_game_max": tokens_max,
            "model_call_cwd_must_be_outside_repo": cwd_outside,
            "model_call_tools_must_be_disabled": tools_disabled,
        },
        evidence=[_rel(r / "model_calls.jsonl") for r in graded.runs],
    )


def check_verification_active(
    prereg: dict[str, Any], experiment: GradedExperiment, graded: GradedSet, e310_root: Path
) -> CheckResult:
    """Every plan was searched inside a program whose backtest certified it on the full history
    with zero mismatches; every executed plan action cites a found plan of a program that was
    certified at that step; the backtester digest is one across E300 and E310."""
    mismatch_max = int(threshold(prereg, "backtest_mismatches_for_certification_max"))
    full_history = bool(threshold(prereg, "backtest_must_cover_full_history"))
    must_cite = bool(threshold(prereg, "executed_plans_must_cite_certified_hypothesis"))
    must_match_e310 = bool(
        threshold(prereg, "backtest_module_sha256_must_match_between_e300_and_e310")
    )
    problems: list[str] = []
    per_run: dict[str, Any] = {}
    module_digests: set[str] = set()
    for run in graded.runs:
        _, _, results = _load_run(run, problems)
        backtests = _read_jsonl_records(run, "backtests.jsonl", G3_BACKTEST_KEYS, problems)
        hyps = _read_jsonl_records(run, "hypotheses.jsonl", G3_HYPOTHESIS_KEYS, problems)
        plans = _read_jsonl_records(run, "plans.jsonl", G3_PLAN_KEYS, problems)
        transitions = _sorted_transitions(run, problems)
        by_hyp: dict[str, dict[str, Any]] = {}
        for rec in backtests:
            hid = str(rec["hypothesis_id"])
            if hid in by_hyp:
                problems.append(f"{run.name}: {hid} backtested more than once")
            by_hyp[hid] = rec
            expected = (
                int(rec["mismatches"]) <= mismatch_max
                and (not full_history or rec["history_length_checked"] == rec["history_length"])
                and rec["failure_kind"] is None
            )
            if bool(rec["certified"]) != expected:
                problems.append(
                    f"{run.name}: {hid} certified {rec['certified']} does not follow from its record"
                )
            module_digests.add(str(rec["backtest_module_sha256"]))
        proposed = [h for h in hyps if h["event"] == HYPOTHESIS_EVENT_PROPOSED]
        certified_ids = {str(h["hypothesis_id"]) for h in proposed if h.get("certified") is True}
        decertified_at: dict[str, int] = {}
        for h in hyps:
            if h["event"] == HYPOTHESIS_EVENT_DECERTIFIED:
                decertified_at[str(h["hypothesis_id"])] = int(h.get("step_index") or 0)
        if results.get("hypotheses_proposed") != len(proposed) or results.get(
            "hypotheses_certified"
        ) != len(certified_ids):
            problems.append(
                f"{run.name}: results hypotheses_proposed/certified != hypotheses.jsonl ({len(proposed)}/{len(certified_ids)})"
            )
        plan_by_index: dict[int, dict[str, Any]] = {}
        for plan in plans:
            index = int(plan["plan_index"])
            if index in plan_by_index:
                problems.append(f"{run.name}: duplicate plan_index {index}")
            plan_by_index[index] = plan
            hid = str(plan["hypothesis_id"])
            rec = by_hyp.get(hid)
            if rec is None or not bool(rec["certified"]) or hid not in certified_ids:
                problems.append(f"{run.name}: plan {index} cites {hid}, which has no certification")
                continue
            if int(rec["mismatches"]) > mismatch_max or (
                full_history and rec["history_length_checked"] != rec["history_length"]
            ):
                problems.append(
                    f"{run.name}: plan {index} cites {hid} whose backtest is partial or has mismatches"
                )
            if plan["certification_history_length"] != rec["history_length"]:
                problems.append(
                    f"{run.name}: plan {index} certification_history_length != backtest history_length"
                )
        executed: set[int] = set()
        for t in transitions:
            if t["source"] != TRANSITION_SOURCE_PLAN:
                continue
            step = int(t["step_index"])
            if t["hypothesis_id"] is None or t["plan_index"] is None:
                problems.append(
                    f"{run.name}: plan action at step {step} cites no hypothesis or plan"
                )
                continue
            plan = plan_by_index.get(int(t["plan_index"]))
            if must_cite and (
                plan is None
                or plan["outcome"] != PLAN_OUTCOME_FOUND
                or plan["hypothesis_id"] != t["hypothesis_id"]
            ):
                problems.append(
                    f"{run.name}: plan action at step {step} cites plan {t['plan_index']} which is not a found plan of {t['hypothesis_id']}"
                )
                continue
            executed.add(int(t["plan_index"]))
            if plan is not None and step <= int(plan["step_index_at_plan"]):
                problems.append(
                    f"{run.name}: plan {t['plan_index']} executed at step {step} before it was searched"
                )
            if t["predicted_observation_sha256"] is None:
                problems.append(
                    f"{run.name}: plan action at step {step} has no recorded prediction"
                )
            decert = decertified_at.get(str(t["hypothesis_id"]))
            if decert is not None and decert < step:
                problems.append(
                    f"{run.name}: plan action at step {step} executed after {t['hypothesis_id']} was decertified at {decert}"
                )
        if results.get("plans_searched") != len(plans) or results.get("plans_executed") != len(
            executed
        ):
            problems.append(
                f"{run.name}: results plans_searched/executed != plans.jsonl ({len(plans)}/{len(executed)})"
            )
        if results.get("backtest_module_sha256") not in module_digests and backtests:
            problems.append(f"{run.name}: results backtest_module_sha256 != the records'")
        per_run[run.name] = {
            "backtests": len(backtests),
            "certified": len(certified_ids),
            "plans": len(plans),
            "plans_executed": len(executed),
            "plan_actions": sum(1 for t in transitions if t["source"] == TRANSITION_SOURCE_PLAN),
        }
    e310_digests: set[str] = set()
    for run in _completed_runs(e310_root, []):
        try:
            e310_digests.add(
                str(_runner_results(_load_json(run / "results.json")).get("backtest_module_sha256"))
            )
        except (OSError, ValueError):
            continue
    if len(module_digests) > 1:
        problems.append(
            f"backtest_module_sha256 differs across graded runs: {sorted(module_digests)}"
        )
    if (
        must_match_e310
        and module_digests
        and (len(e310_digests) != 1 or module_digests != e310_digests)
    ):
        problems.append(
            f"backtest_module_sha256 {sorted(module_digests)} != E310 {sorted(e310_digests)}"
        )
    if not graded.runs:
        problems.append("no graded run")
    return CheckResult(
        "verification_active",
        passed=not problems,
        observed={
            "runs": per_run,
            "backtest_module_sha256": sorted(module_digests),
            "e310_backtest_module_sha256": sorted(e310_digests),
            "problems": problems,
        },
        threshold={
            "backtest_mismatches_for_certification_max": mismatch_max,
            "backtest_must_cover_full_history": full_history,
            "executed_plans_must_cite_certified_hypothesis": must_cite,
            "backtest_module_sha256_must_match_between_e300_and_e310": must_match_e310,
        },
        evidence=[
            _rel(r / f)
            for r in graded.runs
            for f in ("plans.jsonl", "backtests.jsonl", "hypotheses.jsonl")
        ],
    )


def _ledger_entries(root: Path) -> list[dict[str, Any]]:
    path = root / "state" / "LEDGER.jsonl"
    entries: list[dict[str, Any]] = []
    if not path.exists():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            entries.append(rec)
    return entries


def check_preflight_recorded(
    prereg: dict[str, Any], experiment: GradedExperiment, graded: GradedSet, root: Path = ROOT
) -> CheckResult:
    """state/BUDGET.json g3_preflight records the three pre-flight runs (present, sealed, the
    pre-registered games), the fraction or the no-denominator escalation, and every graded run
    that is not itself a pre-flight run started after the third pre-flight run."""
    games_measured = int(threshold(prereg, "preflight_games_measured"))
    escalate_above = float(threshold(prereg, "preflight_escalate_above_fraction"))
    must_precede = bool(threshold(prereg, "preflight_must_precede_fourth_game_run"))
    games = section(prereg, "cost_preflight").get("games")
    if not isinstance(games, list) or not games:
        raise PreregistrationError("cost_preflight.games missing")
    e300_root = root / _required_str(
        section(prereg, "verification"), "artifacts_root", "verification"
    )
    problems: list[str] = []
    budget_path = root / "state" / "BUDGET.json"
    budget = (
        _load_json_mapping(budget_path, problems, "state/BUDGET.json")
        if budget_path.exists()
        else {}
    )
    if not budget_path.exists():
        problems.append("state/BUDGET.json missing")
    preflight = budget.get("g3_preflight") if isinstance(budget.get("g3_preflight"), dict) else {}
    if not preflight:
        problems.append("state/BUDGET.json lacks g3_preflight")
    if preflight.get("games_measured") != games_measured:
        problems.append(f"games_measured {preflight.get('games_measured')!r} != {games_measured}")
    if preflight.get("escalate_above_fraction") != escalate_above:
        problems.append(
            f"escalate_above_fraction {preflight.get('escalate_above_fraction')!r} != {escalate_above}"
        )
    measured = (
        preflight.get("measured_runs") if isinstance(preflight.get("measured_runs"), dict) else {}
    )
    if len(measured) != games_measured:
        problems.append(f"{len(measured)} measured runs recorded, required {games_measured}")
    stems_measured: list[str] = []
    latest_preflight: str | None = None
    evidence = [_rel(budget_path)]
    for run_id, rec in sorted(measured.items()):
        run = e300_root / str(run_id)
        evidence.append(_rel(run / "SHA256SUMS"))
        if not isinstance(rec, dict):
            problems.append(f"measured run {run_id} is not a mapping")
            continue
        stems_measured.append(str(rec.get("game", "")).split("-", 1)[0])
        if not (run / "SHA256SUMS").is_file() or not (run / "results.json").is_file():
            problems.append(f"pre-flight run {run_id} is not preserved under {_rel(e300_root)}")
            continue
        if sha256_file(run / "SHA256SUMS") != str(rec.get("sha256sums_sha256")).lower():
            problems.append(f"pre-flight run {run_id} SHA256SUMS digest != recorded")
        if sha256_file(run / "results.json") != str(rec.get("results_json_sha256")).lower():
            problems.append(f"pre-flight run {run_id} results.json digest != recorded")
        manifest = _load_manifest(run) or {}
        ts = manifest.get("timestamp_utc")
        if isinstance(ts, str) and (latest_preflight is None or ts > latest_preflight):
            latest_preflight = ts
    if sorted(stems_measured) != sorted(str(g) for g in games):
        problems.append(
            f"measured games {sorted(stems_measured)} != cost_preflight.games {sorted(games)}"
        )
    fraction = preflight.get("projected_fraction_of_weekly_allowance")
    escalations = [
        e
        for e in _ledger_entries(root)
        if e.get("event") == "human_escalation"
        and e.get("gate") == "G3"
        and (
            "no_denominator" in str(e.get("kind", ""))
            or "no_denominator_rule" in str(e.get("summary", ""))
        )
    ]
    if fraction is None:
        if not escalations:
            problems.append(
                "projected_fraction_of_weekly_allowance is null and no no-denominator human_escalation ledger entry exists"
            )
    elif not isinstance(fraction, int | float):
        problems.append(f"projected_fraction_of_weekly_allowance {fraction!r} is not a number")
    elif float(fraction) > escalate_above and not escalations:
        problems.append(f"fraction {fraction} > {escalate_above} without a human_escalation entry")
    later_graded: list[str] = []
    if must_precede and latest_preflight is not None:
        for row in graded.rows:
            if row["role"] == ROLE_FAILED or str(row["run_id"]) in measured:
                continue
            ts = row.get("timestamp_utc")
            if not isinstance(ts, str) or ts <= latest_preflight:
                later_graded.append(str(row["run_id"]))
        if later_graded:
            problems.append(f"graded runs that do not post-date the pre-flight: {later_graded}")
    return CheckResult(
        "preflight_recorded",
        passed=not problems,
        observed={
            "games_measured": preflight.get("games_measured"),
            "measured_runs": sorted(measured),
            "stems_measured": sorted(stems_measured),
            "projected_fraction_of_weekly_allowance": fraction,
            "projected_usd_25": preflight.get("projected_usd_25"),
            "no_denominator_escalations": [str(e.get("ts")) for e in escalations],
            "latest_preflight_timestamp_utc": latest_preflight,
            "graded_runs_not_after_preflight": later_graded,
            "problems": problems,
        },
        threshold={
            "preflight_games_measured": games_measured,
            "preflight_escalate_above_fraction": escalate_above,
            "preflight_must_precede_fourth_game_run": must_precede,
            "games": [str(g) for g in games],
        },
        evidence=evidence,
    )


# ----- checks the successor pre-registration adds (G3b.yaml additional_checks_this_file_requires)


def check_successor_overlay(
    g3_path: Path,
    g3_sha256: str,
    successor: dict[str, Any],
    successor_path: Path,
    successor_sha256: str,
    overrides: dict[str, dict[str, Any]],
) -> CheckResult:
    """Record both pre-registration digests and the overridden keys; the successor must name
    the G3 file it succeeds by the digest actually loaded."""
    successor_of = successor.get("successor_of")
    problems: list[str] = []
    if (
        not isinstance(successor_of, dict)
        or str(successor_of.get("sha256", "")).lower() != g3_sha256
    ):
        problems.append("successor_of.sha256 != the G3 pre-registration digest loaded")
    if not overrides:
        problems.append("no overriding key")
    return CheckResult(
        "successor_preregistration_overlay",
        passed=not problems,
        observed={
            "g3": {"preregistration": _rel(g3_path), "sha256": g3_sha256},
            "successor": {"preregistration": _rel(successor_path), "sha256": successor_sha256},
            "overrides": overrides,
            "problems": problems,
        },
        threshold={"thresholds_overriding_g3": list(overrides)},
        evidence=[_rel(g3_path), _rel(successor_path)],
    )


def check_graded_config_identity(
    successor: dict[str, Any], experiment: GradedExperiment, graded: GradedSet, root: Path = ROOT
) -> CheckResult:
    """The committed graded config has the locked digest and every graded run was produced
    from it with the locked prompt and experiment id."""
    config_sha = str(threshold(successor, "graded_config_sha256")).lower()
    prompt_hash = str(threshold(successor, "prompt_hash")).lower()
    experiment_id = str(threshold(successor, "experiment_id"))
    problems: list[str] = []
    config_digest = sha256_file(experiment.config_path) if experiment.config_path.exists() else None
    if config_digest != config_sha:
        problems.append(
            f"{_rel(experiment.config_path)} sha256 {config_digest!r} != locked {config_sha}"
        )
    if experiment.experiment_id != experiment_id:
        problems.append(
            f"graded_experiment.experiment_id {experiment.experiment_id!r} != thresholds.experiment_id"
        )
    per_run: dict[str, Any] = {}
    for run in graded.runs:
        manifest, top, results = _load_run(run, problems)
        row = {
            "config_file_sha256": top.get("config_file_sha256"),
            "prompt_hash": manifest.get("prompt_hash"),
            "experiment_id": manifest.get("experiment_id"),
        }
        if str(row["config_file_sha256"]).lower() != config_sha:
            problems.append(
                f"{run.name}: config_file_sha256 {row['config_file_sha256']!r} != {config_sha}"
            )
        if (
            str(row["prompt_hash"]).lower() != prompt_hash
            or str(results.get("prompt_hash")).lower() != prompt_hash
        ):
            problems.append(f"{run.name}: prompt_hash != {prompt_hash}")
        resolved_id = _read_yaml_mapping(run / "resolved_config.yaml").get("experiment_id")
        if not (row["experiment_id"] == top.get("experiment_id") == resolved_id == experiment_id):
            problems.append(
                f"{run.name}: experiment_id {row['experiment_id']!r} != {experiment_id}"
            )
        per_run[run.name] = row
    if not graded.runs:
        problems.append("no graded run")
    return CheckResult(
        "graded_config_identity",
        passed=not problems,
        observed={
            "config": _rel(experiment.config_path),
            "config_sha256": config_digest,
            "runs": per_run,
            "problems": problems,
        },
        threshold={
            "graded_config_sha256": config_sha,
            "prompt_hash": prompt_hash,
            "experiment_id": experiment_id,
        },
        evidence=[_rel(experiment.config_path), *(_rel(r / "results.json") for r in graded.runs)],
    )


def _flatten(mapping: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {prefix.rstrip("."): mapping}
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, f"{path}."))
        else:
            out[path] = value
    return out


def _line_changes(a: list[str], b: list[str]) -> int:
    changed = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag in ("replace", "insert", "delete"):
            changed += max(i2 - i1, j2 - j1)
    return changed


def check_graded_config_derivation(
    successor: dict[str, Any], experiment: GradedExperiment, root: Path = ROOT
) -> CheckResult:
    """The graded config differs from the validated diagnostic config by exactly the
    pre-registered number of lines, at exactly the five pre-registered keys, each taking the
    successor's locked value; the planner keys carried unchanged read the locked values."""
    from arc_plasticity.agents.ref_world_model import click_points_for_step

    derived_sha = str(threshold(successor, "graded_config_derived_from_sha256")).lower()
    changes_expected = int(threshold(successor, "graded_config_line_changes_from_e303"))
    expected_leaves = {path: threshold(successor, name) for path, name in G3_SUCCESSOR_CONFIG_LINES}
    planner_expected = {
        key: threshold(successor, name) for key, name in G3_SUCCESSOR_PLANNER_THRESHOLDS
    }
    problems: list[str] = []
    parent: Path | None = None
    for candidate in sorted(experiment.config_path.parent.glob("*.yaml")):
        if candidate != experiment.config_path and sha256_file(candidate) == derived_sha:
            parent = candidate
            break
    line_changes: int | None = None
    differing: dict[str, Any] = {}
    if parent is None:
        problems.append(
            f"no config under {_rel(experiment.config_path.parent)} has sha256 {derived_sha}"
        )
    elif not experiment.config_path.exists():
        problems.append(f"{_rel(experiment.config_path)} missing")
    else:
        a = parent.read_text(encoding="utf-8").splitlines()
        b = experiment.config_path.read_text(encoding="utf-8").splitlines()
        line_changes = _line_changes(a, b)
        if line_changes != changes_expected:
            problems.append(
                f"{line_changes} line changes between {parent.name} and {experiment.config_path.name}, pre-registered {changes_expected}"
            )
        flat_a = _flatten(_read_yaml_mapping(parent))
        flat_b = _flatten(_read_yaml_mapping(experiment.config_path))
        for key in sorted(set(flat_a) | set(flat_b)):
            if flat_a.get(key) != flat_b.get(key):
                differing[key] = {"from": flat_a.get(key), "to": flat_b.get(key)}
        if set(differing) != set(expected_leaves):
            problems.append(
                f"differing keys {sorted(differing)} != pre-registered {sorted(expected_leaves)}"
            )
        for key, value in expected_leaves.items():
            if key in flat_b and flat_b[key] != value:
                problems.append(f"{key} is {flat_b[key]!r}, pre-registered {value!r}")
        planner = (
            _read_yaml_mapping(experiment.config_path).get("runner_params", {}).get("planner", {})
        )
        if not isinstance(planner, dict):
            planner = {}
        observed_planner = {
            "max_depth": planner.get("max_depth"),
            "max_nodes": planner.get("max_nodes"),
            "click_grid_step": planner.get("click_grid_step"),
            "click_points": len(click_points_for_step(int(planner.get("click_grid_step") or 0))),
        }
        if observed_planner != planner_expected:
            problems.append(
                f"graded config planner {observed_planner} != pre-registered {planner_expected}"
            )
    return CheckResult(
        "graded_config_derivation",
        passed=not problems,
        observed={
            "derived_from": _rel(parent) if parent else None,
            "line_changes": line_changes,
            "differing_keys": differing,
            "problems": problems,
        },
        threshold={
            "graded_config_derived_from_sha256": derived_sha,
            "graded_config_line_changes_from_e303": changes_expected,
            "expected_leaves": expected_leaves,
            "planner": planner_expected,
        },
        evidence=[_rel(experiment.config_path)] + ([_rel(parent)] if parent else []),
    )


def check_spend_caps_respected(
    prereg: dict[str, Any],
    successor: dict[str, Any],
    experiment: GradedExperiment,
    graded: GradedSet,
) -> CheckResult:
    """Every graded run ran under the locked operational caps and stayed within them: the
    per-run model wall-clock (plus at most one call's overrun), the per-run call cap, the
    runner wall-clock limit (the overridden invocation limit) and the job margin."""
    wall_cap = float(threshold(successor, "model_wallclock_per_run_seconds"))
    calls_cap = int(threshold(successor, "calls_per_run_max"))
    invocation = float(threshold(prereg, "wallclock_per_invocation_seconds"))
    job_limit = float(threshold(successor, "job_wallclock_limit_seconds"))
    margin_min = float(threshold(successor, "job_margin_over_runner_limit_seconds_min"))
    sim_max = int(threshold(successor, "simulation_steps_per_game_max"))
    if sim_max != int(threshold(prereg, "simulation_steps_per_game_max")):
        raise PreregistrationError(
            "simulation_steps_per_game_max differs between G3 and its successor"
        )
    problems: list[str] = []
    if invocation + margin_min > job_limit:
        problems.append(
            f"wallclock_per_invocation_seconds {invocation} + margin {margin_min} > job limit {job_limit}"
        )
    config = _read_yaml_mapping(experiment.config_path)
    if config.get("wallclock_limit_seconds") != invocation:
        problems.append(
            f"{_rel(experiment.config_path)} wallclock_limit_seconds {config.get('wallclock_limit_seconds')!r} != {invocation}"
        )
    per_run: dict[str, Any] = {}
    for run in graded.runs:
        manifest, _, results = _load_run(run, problems)
        params = _runner_params(run)
        client = params.get("model_client") if isinstance(params.get("model_client"), dict) else {}
        call_cap = float(client.get("call_wallclock_seconds") or 0.0)
        reserve = float(params.get("wallclock_reserve_seconds") or 0.0)
        spend = (
            results.get("spend_control") if isinstance(results.get("spend_control"), dict) else {}
        )
        model_wall = float(results.get("model_wallclock_seconds_total") or 0.0)
        calls = int(results.get("model_calls") or 0)
        row = {
            "model_wallclock_seconds_total": model_wall,
            "model_calls": calls,
            "wallclock_seconds": manifest.get("wallclock_seconds"),
            "wallclock_limit_seconds": manifest.get("wallclock_limit_seconds"),
            "call_wallclock_seconds": call_cap,
            "wallclock_reserve_seconds": reserve,
            "simulation_budget": results.get("simulation_budget"),
        }
        if (
            float(spend.get("model_wallclock_per_run_seconds", -1)) != wall_cap
            or spend.get("calls_per_run_max") != calls_cap
        ):
            problems.append(
                f"{run.name}: spend_control {spend} != locked caps {wall_cap}/{calls_cap}"
            )
        if model_wall > wall_cap + call_cap:
            problems.append(
                f"{run.name}: model wall-clock {model_wall} > cap {wall_cap} + one call {call_cap}"
            )
        if calls > calls_cap:
            problems.append(f"{run.name}: {calls} calls > calls_per_run_max {calls_cap}")
        if manifest.get("wallclock_limit_seconds") != invocation:
            problems.append(
                f"{run.name}: manifest wallclock_limit_seconds {manifest.get('wallclock_limit_seconds')!r} != {invocation}"
            )
        wall = manifest.get("wallclock_seconds")
        if not isinstance(wall, int | float) or float(wall) > invocation + reserve:
            problems.append(
                f"{run.name}: wallclock_seconds {wall!r} > limit {invocation} + reserve {reserve}"
            )
        sim = (
            results.get("simulation_budget")
            if isinstance(results.get("simulation_budget"), dict)
            else {}
        )
        if (
            sim.get("max_steps") != sim_max
            or int(sim.get("used") or 0) > sim_max
            or results.get("simulation_steps_per_game_max") != sim_max
        ):
            problems.append(f"{run.name}: simulation budget {sim} not within {sim_max}")
        per_run[run.name] = row
    if not graded.runs:
        problems.append("no graded run")
    return CheckResult(
        "spend_caps_respected",
        passed=not problems,
        observed={"runs": per_run, "problems": problems},
        threshold={
            "model_wallclock_per_run_seconds": wall_cap,
            "calls_per_run_max": calls_cap,
            "wallclock_per_invocation_seconds": invocation,
            "job_wallclock_limit_seconds": job_limit,
            "job_margin_over_runner_limit_seconds_min": margin_min,
            "simulation_steps_per_game_max": sim_max,
        },
        evidence=[_rel(experiment.config_path), *(_rel(r / "results.json") for r in graded.runs)],
    )


def check_planner_caps_recorded(successor: dict[str, Any], graded: GradedSet) -> CheckResult:
    """results.json's planner block carries the locked planner caps in every graded run."""
    expected = {key: threshold(successor, name) for key, name in G3_SUCCESSOR_PLANNER_THRESHOLDS}
    problems: list[str] = []
    per_run: dict[str, Any] = {}
    for run in graded.runs:
        _, _, results = _load_run(run, problems)
        planner = results.get("planner")
        per_run[run.name] = planner
        if planner != expected:
            problems.append(f"{run.name}: planner {planner!r} != {expected}")
    if not graded.runs:
        problems.append("no graded run")
    return CheckResult(
        "planner_caps_recorded",
        passed=not problems,
        observed={"runs": per_run, "problems": problems},
        threshold=expected,
        evidence=[_rel(r / "results.json") for r in graded.runs],
    )


def check_no_resumption(successor: dict[str, Any], graded: GradedSet) -> CheckResult:
    """No graded run was resumed (G3b.yaml resumption_rule)."""
    resumptions_max = int(threshold(successor, "resumptions_used_max"))
    problems: list[str] = []
    per_run: dict[str, Any] = {}
    for run in graded.runs:
        manifest, _, results = _load_run(run, problems)
        used = results.get("resumptions")
        recorded = manifest.get("resumptions")
        per_run[run.name] = {"results": used, "manifest": recorded}
        if not isinstance(used, int) or used > resumptions_max:
            problems.append(f"{run.name}: resumptions {used!r} > {resumptions_max}")
        if recorded not in (None, 0, [], {}) and not (
            isinstance(recorded, list) and len(recorded) <= resumptions_max
        ):
            problems.append(f"{run.name}: manifest resumptions {recorded!r}")
    if not graded.runs:
        problems.append("no graded run")
    return CheckResult(
        "no_resumption",
        passed=not problems,
        observed={"runs": per_run, "problems": problems},
        threshold={"resumptions_used_max": resumptions_max},
        evidence=[_rel(r / "manifest.json") for r in graded.runs],
    )


def check_diagnostic_runs_untouched(
    successor: dict[str, Any], experiment: GradedExperiment, root: Path = ROOT
) -> CheckResult:
    """The excluded diagnostic runs still exist, their SHA256SUMS verify where the run was
    sealed, and none of them appears under the graded root or in the run set manifest."""
    excluded_count = int(threshold(successor, "diagnostic_runs_excluded"))
    excluded = _excluded_diagnostic_runs(successor)
    problems: list[str] = []
    if len(excluded) != excluded_count:
        problems.append(f"{len(excluded)} excluded runs listed, pre-registered {excluded_count}")
    listed_ids: set[str] = set()
    if experiment.run_set_manifest.exists():
        doc = _load_json_mapping(
            experiment.run_set_manifest, problems, _rel(experiment.run_set_manifest)
        )
        for rec in doc.get("runs", []) if isinstance(doc.get("runs"), list) else []:
            if isinstance(rec, dict) and isinstance(rec.get("run_id"), str):
                listed_ids.add(rec["run_id"])
    graded_dirs = {p.name for p in _run_dirs(experiment.artifacts_root)}
    per_run: dict[str, Any] = {}
    evidence: list[str] = []
    for exp_dir, stem, run_id in excluded:
        run = root / "artifacts" / exp_dir / run_id
        evidence.append(_rel(run))
        row: dict[str, Any] = {
            "experiment": exp_dir,
            "stem": stem,
            "exists": run.is_dir(),
            "sealed": (run / "SHA256SUMS").is_file(),
        }
        if not run.is_dir():
            problems.append(f"excluded run {exp_dir}/{run_id} no longer exists")
        elif row["sealed"]:
            listed = _parse_sha256sums(run / "SHA256SUMS")
            bad = [
                rel
                for rel, digest in listed.items()
                if not (run / rel).is_file() or sha256_file(run / rel) != digest
            ]
            row["files_verified"] = len(listed) - len(bad)
            if bad:
                problems.append(
                    f"excluded run {exp_dir}/{run_id}: {len(bad)} files fail SHA256SUMS"
                )
        elif (_load_manifest(run) or {}).get("completion_status") == COMPLETED_STATUS:
            problems.append(f"excluded run {exp_dir}/{run_id} is completed but unsealed")
        if run_id in graded_dirs or run_id in listed_ids:
            problems.append(f"excluded run {run_id} appears in the graded set")
        per_run[run_id] = row
    return CheckResult(
        "diagnostic_runs_untouched",
        passed=not problems,
        observed={"runs": per_run, "problems": problems},
        threshold={"diagnostic_runs_excluded": excluded_count},
        evidence=evidence,
    )


def check_stop_reason_semantics(
    prereg: dict[str, Any],
    successor: dict[str, Any],
    experiment: GradedExperiment,
    graded: GradedSet,
) -> CheckResult:
    """Each graded run's stop_reason is borne out by its own records (G3b.yaml item 5 and
    G3.yaml per_game_stop_rule): a model-budget stop has the budget consumed and no certified
    program left; a wall-clock stop is within reserve of the limit; a level-budget stop has
    the current level exactly at its budget; a win ends in state WIN with every level done."""
    thresholds_used = {
        "stop_reasons": list(la.STOP_REASONS),
        "wallclock_per_invocation_seconds": threshold(prereg, "wallclock_per_invocation_seconds"),
        "model_wallclock_per_run_seconds": threshold(successor, "model_wallclock_per_run_seconds"),
    }
    problems: list[str] = []
    per_run: dict[str, Any] = {}
    stop_counts: dict[str, int] = {}
    for run in graded.runs:
        manifest, _, results = _load_run(run, problems)
        reason = str(results.get("stop_reason"))
        stop_counts[reason] = stop_counts.get(reason, 0) + 1
        levels = results.get("levels") if isinstance(results.get("levels"), list) else []
        row: dict[str, Any] = {
            "stop_reason": reason,
            "model_budget_binding": results.get("model_budget_binding"),
        }
        if reason == la.STOP_MODEL_BUDGET_EXHAUSTED:
            if results.get("model_budget_consumed") is not True or not results.get(
                "model_budget_binding"
            ):
                problems.append(
                    f"{run.name}: model_budget_exhausted without model_budget_consumed/binding"
                )
            hyps = _read_jsonl_records(run, "hypotheses.jsonl", G3_HYPOTHESIS_KEYS, problems)
            certified = {
                str(h["hypothesis_id"])
                for h in hyps
                if h["event"] == HYPOTHESIS_EVENT_PROPOSED and h.get("certified") is True
            }
            decertified = {
                str(h["hypothesis_id"]) for h in hyps if h["event"] == HYPOTHESIS_EVENT_DECERTIFIED
            }
            row["certified_at_stop"] = sorted(certified - decertified)
            if certified - decertified:
                problems.append(
                    f"{run.name}: model_budget_exhausted while {sorted(certified - decertified)} still certified"
                )
        elif reason == la.STOP_WALLCLOCK:
            reserve = float(_runner_params(run).get("wallclock_reserve_seconds") or 0.0)
            wall = manifest.get("wallclock_seconds")
            limit = manifest.get("wallclock_limit_seconds")
            row["wallclock_seconds"] = wall
            if (
                not isinstance(wall, int | float)
                or not isinstance(limit, int | float)
                or abs(float(wall) - float(limit)) > reserve
            ):
                problems.append(
                    f"{run.name}: wallclock stop at {wall!r} is not within {reserve} s of the limit {limit!r}"
                )
        elif reason == la.STOP_LEVEL_BUDGET_EXHAUSTED:
            current = _first_uncompleted_level(levels)
            if current is None or current.get("actions_attributed") != current.get("budget"):
                problems.append(
                    f"{run.name}: level_budget_exhausted but the current level is not at its budget"
                )
        elif reason == la.STOP_WIN:
            if results.get("final_state") != la.WIN_STATE or results.get(
                "levels_completed"
            ) != results.get("win_levels"):
                problems.append(
                    f"{run.name}: win without final_state WIN and every level completed"
                )
        else:
            problems.append(f"{run.name}: stop_reason {reason!r} is not a graded outcome")
        per_run[run.name] = row
    if not graded.runs:
        problems.append("no graded run")
    return CheckResult(
        "stop_reason_semantics",
        passed=not problems,
        observed={"runs": per_run, "stop_reason_counts": stop_counts, "problems": problems},
        threshold=thresholds_used,
        evidence=[_rel(r / f) for r in graded.runs for f in ("results.json", "hypotheses.jsonl")],
    )


def evaluate_g3(
    prereg: dict[str, Any], artifacts_root: Path, root: Path = ROOT, skip_tooling: bool = False
) -> list[CheckResult]:
    """G3 checks in the order ``verification.checks_in_order`` lists them.

    ``artifacts_root`` is the graded root (E300 under G3.yaml alone; the successor's graded
    root when preregistration/G3b.yaml exists, whose thresholds_overriding_g3 keys replace
    the G3 values and whose additional checks follow the G3 ones). The E310 root is
    ``verification.secondary_artifacts_root``; checks over E310 carry the ``_e310`` suffix.
    """
    successor_loaded = load_g3_successor(root)
    view = prereg
    overrides: dict[str, dict[str, Any]] = {}
    successor: dict[str, Any] | None = None
    if successor_loaded is not None:
        successor, successor_path, successor_sha256 = successor_loaded
        view, overrides = apply_g3_overlay(prereg, successor)
    experiment = replace(g3_graded_experiment(view, successor, root), artifacts_root=artifacts_root)
    verification = section(view, "verification")
    e310_rel = str(verification.get("secondary_artifacts_root") or "")
    if not e310_rel:
        raise PreregistrationError("verification.secondary_artifacts_root missing")
    e310_root = root / e310_rel
    e310 = _g3_e310_section(view)
    if "model_calls_allowed" not in e310:
        raise PreregistrationError("backtest_rejection_experiment.model_calls_allowed missing")
    e310_model_calls = int(e310["model_calls_allowed"])
    e300_model_calls = int(threshold(view, "model_calls_per_game_max"))
    extra = _g3_extra_artifacts(view)
    e310_view = _g3_e310_view(view)

    def suffixed(check: CheckResult) -> CheckResult:
        check.name = f"{check.name}_e310"
        return check

    checks: list[CheckResult] = []
    if successor is not None:
        _, g3_path, g3_sha256 = load_preregistration("G3", root)
        checks.append(
            check_successor_overlay(
                g3_path, g3_sha256, successor, successor_path, successor_sha256, overrides
            )
        )
    checks.append(check_cache_manifest_locked(view, root))
    graded = g3_graded_set(view, experiment, root)
    checks.append(check_run_set_manifest(view, successor, experiment, graded, root))
    checks.append(check_run_completeness(experiment.artifacts_root, extra, runs=graded.runs))
    checks.append(suffixed(check_run_completeness(e310_root)))
    checks.append(check_sha256sums(view, experiment.artifacts_root, runs=graded.runs))
    checks.append(suffixed(check_sha256sums(view, e310_root)))
    checks.append(
        check_offline_run(
            view, experiment.artifacts_root, model_allowed=e300_model_calls, runs=graded.runs
        )
    )
    checks.append(suffixed(check_offline_run(view, e310_root, model_allowed=e310_model_calls)))
    checks.append(check_official_baselines_used(view, experiment, graded, root))
    checks.append(check_action_budget_enforced(view, experiment, graded))
    checks.append(check_replay_final_frame_identity_e300(view, experiment, graded, root))
    checks.append(check_rhae_recomputed(view, experiment, graded))
    checks.append(check_model_call_accounting(view, experiment, graded, root))
    checks.append(check_verification_active(view, experiment, graded, e310_root))
    checks.append(check_backtest_rejection(view, e310_root, root))
    checks.append(check_preflight_recorded(view, experiment, graded, root))
    if successor is not None:
        checks.append(check_graded_config_identity(successor, experiment, graded, root))
        checks.append(check_graded_config_derivation(successor, experiment, root))
        checks.append(check_spend_caps_respected(view, successor, experiment, graded))
        checks.append(check_planner_caps_recorded(successor, graded))
        checks.append(check_no_resumption(successor, graded))
        checks.append(check_diagnostic_runs_untouched(successor, experiment, root))
        checks.append(check_stop_reason_semantics(view, successor, experiment, graded))
    # "after the G0 exclusions" under the G1 exclusion_nesting_rule: the category bounds are
    # the hash-locked G0 pre-registration's, read from the project, and its digest recorded.
    g0, g0_path, g0_sha256 = load_preregistration("G0", ROOT)
    nd_check, excluded = check_nondeterministic_fields(
        e310_view, root, bounds=section(g0, "determinism_protocol")
    )
    nd_check.threshold = {
        **nd_check.threshold,
        "bounds_source": {"preregistration": _rel(g0_path), "sha256": g0_sha256},
    }
    checks.append(suffixed(check_exclusion_nesting(view, e310_root, excluded)))
    checks.append(nd_check)
    checks.append(suffixed(check_determinism(e310_view, e310_root, excluded)))
    checks.append(check_git_clean(view, root))
    checks.append(check_licence(view, root))
    checks.extend(_tooling_checks(view, root, skip_tooling))
    return checks


GATE_EVALUATORS = {"G0": evaluate_g0, "G1": evaluate_g1, "G2": evaluate_g2, "G3": evaluate_g3}


def default_artifacts_root(gate: str, prereg: dict[str, Any], root: Path = ROOT) -> Path:
    """``verification.artifacts_root``, or for G3 with a successor the successor's graded root."""
    if gate == "G3":
        successor_loaded = load_g3_successor(root)
        if successor_loaded is not None:
            return g3_graded_experiment(prereg, successor_loaded[0], root).artifacts_root
    declared = section(prereg, "verification").get("artifacts_root")
    if not declared:
        raise PreregistrationError("verification.artifacts_root missing")
    return root / str(declared)


def evaluate(
    gate: str, artifacts_root: Path | None = None, root: Path = ROOT, skip_tooling: bool = False
) -> Report:
    prereg, path, digest = load_preregistration(gate, root)
    if gate not in GATE_EVALUATORS:
        raise PreregistrationError(f"no evaluator implemented for gate {gate}")
    if artifacts_root is None:
        artifacts_root = default_artifacts_root(gate, prereg, root)
    checks = GATE_EVALUATORS[gate](prereg, artifacts_root, root, skip_tooling)
    return Report(gate, str(path.relative_to(root)), digest, checks)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
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
