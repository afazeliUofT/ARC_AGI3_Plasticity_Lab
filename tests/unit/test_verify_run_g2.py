"""Unit tests for the G2 evaluator in scripts/verify_run.py.

Every number a test compares against is read from the real ``preregistration/G2.yaml``
through the verifier's own ``threshold()``. The data checks are exercised on a synthetic
world (``tests/g2_synthetic.py``) with two real runner invocations; each check then gets one
failing case produced by mutating a copy of the artifacts or the world, so the verifier is
shown to reject the defect it exists to catch, not only to accept a good run.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from tests.g2_synthetic import SyntheticWorld, build_world

ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


vr = _load_module("verify_run")


@pytest.fixture(scope="module")
def prereg() -> dict[str, Any]:
    data: dict[str, Any]
    data, _, _ = vr.load_preregistration("G2", ROOT)
    return data


@pytest.fixture(scope="module")
def excluded(prereg: dict[str, Any]) -> frozenset[str]:
    g0, _, _ = vr.load_preregistration("G0", ROOT)
    _, names = vr.check_nondeterministic_fields(prereg, ROOT, bounds=g0["determinism_protocol"])
    return names


def test_g2_exclusions_are_the_g0_exclusions(
    prereg: dict[str, Any], excluded: frozenset[str]
) -> None:
    """The G2 protocol has no bounds of its own; without the G0 bounds the check must raise."""
    with pytest.raises(vr.PreregistrationError, match="category bounds"):
        vr.check_nondeterministic_fields(prereg, ROOT)
    g0, _, _ = vr.load_preregistration("G0", ROOT)
    _, g0_names = vr.check_nondeterministic_fields(g0, ROOT)
    assert excluded == g0_names and "session_id" in excluded


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory, prereg: dict[str, Any]) -> SyntheticWorld:
    w = build_world(tmp_path_factory.mktemp("g2world"), prereg)
    rx = _load_module("run_experiment")
    raw = yaml.safe_load(
        (ROOT / "configs" / "experiments" / "E020_human_baselines.yaml").read_text()
    )
    raw["runner_params"] = w.runner_params()
    cfg = w.root.parent / f"{w.root.name}_E020.yaml"  # outside the committed world
    cfg.write_text(yaml.safe_dump(raw))
    proto = prereg["determinism_protocol"]
    for i in range(int(proto["identical_invocations"])):
        _, status = rx.run(
            cfg,
            seed=int(proto["fixed_seed"]),
            artifacts_root=w.root / "artifacts",
            run_id=f"fixed_{i}",
        )
        assert status == "completed"
    return w


def _artifacts(world: SyntheticWorld) -> Path:
    return world.root / "artifacts" / "E020_human_baselines"


@pytest.fixture
def runs(world: SyntheticWorld, tmp_path: Path) -> Path:
    """A private copy of the two runs that a test may mutate."""
    dst = tmp_path / "E020_human_baselines"
    shutil.copytree(_artifacts(world), dst)
    return dst


def _edit_json(path: Path, mutate: Any) -> None:
    doc = json.loads(path.read_text())
    mutate(doc)
    path.write_text(json.dumps(doc, sort_keys=True, indent=2) + "\n")


def _reseal(run: Path) -> None:
    lines = []
    for p in sorted(x for x in run.rglob("*") if x.is_file() and x.name != "SHA256SUMS"):
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(run)}")
    (run / "SHA256SUMS").write_text("\n".join(lines) + "\n")


# ------------------------------------------------------------------ thresholds, dispatch


def test_every_g2_threshold_is_read_from_the_preregistration(prereg: dict[str, Any]) -> None:
    for key in (
        "public_games_total",
        "public_levels_total",
        "metadata_baseline_levels_must_equal_public_levels_total",
        "rhae_synthetic_cases_min",
        "rhae_synthetic_cases_max",
        "rhae_synthetic_abs_tolerance",
        "rhae_synthetic_required_tags",
        "rhae_synthetic_all_cases_must_pass",
        "rhae_adapter_must_delegate_to_toolkit",
        "derivation_vectors_min",
        "derivation_vectors_all_must_pass",
        "replay_units_min",
        "replay_parse_failures_max",
        "human_baseline_level_coverage_min",
        "derived_baselines_positive_integers",
        "dataset_manifest_required_fields",
        "dataset_manifest_min_files",
        "dataset_manifest_drift_files_max",
        "input_manifest_must_equal_dataset_manifest",
        "determinism_identity_min",
        "contrast_runs_required",
        "excluded_key_max_depth",
        "excluded_key_container_values_allowed",
    ):
        assert vr.threshold(prereg, key) is not None


def test_g2_checks_raise_without_thresholds(prereg: dict[str, Any], tmp_path: Path) -> None:
    stripped = {**prereg, "thresholds": {}}
    for fn in (
        lambda: vr.check_public_level_count(stripped, ROOT),
        lambda: vr.check_rhae_synthetic_vectors(stripped, ROOT),
        lambda: vr.check_baseline_derivation_vectors(stripped),
        lambda: vr.check_dataset_manifest(stripped, ROOT),
        lambda: vr.check_replay_ingestion(stripped, tmp_path, ROOT),
        lambda: vr.check_human_baseline_coverage(stripped, tmp_path),
        lambda: vr.check_determinism_fixed_seed(stripped, tmp_path, frozenset()),
    ):
        with pytest.raises(vr.PreregistrationError):
            fn()


def test_g2_is_dispatched() -> None:
    assert vr.GATE_EVALUATORS["G2"] is vr.evaluate_g2


def test_evaluate_g2_requires_the_contract_to_name_the_operation(
    prereg: dict[str, Any], tmp_path: Path
) -> None:
    broken = copy.deepcopy(prereg)
    broken["experiment"]["results_json_contract"] = "operation unspecified"
    with pytest.raises(vr.PreregistrationError, match="operation"):
        vr.evaluate_g2(broken, tmp_path, ROOT, skip_tooling=True)


# ------------------------------------------------------------------ public_level_count


def test_public_level_count_passes_on_the_real_cache(prereg: dict[str, Any]) -> None:
    result = vr.check_public_level_count(prereg, ROOT)
    assert result.passed, result.observed
    assert result.observed["games"] == vr.threshold(prereg, "public_games_total")
    assert result.observed["levels_sum"] == vr.threshold(prereg, "public_levels_total")


def test_public_level_count_fails_when_a_metadata_baseline_is_shortened(
    prereg: dict[str, Any], world: SyntheticWorld, tmp_path: Path
) -> None:
    assert vr.check_public_level_count(prereg, world.root).passed
    root = tmp_path / "root"
    shutil.copytree(world.root, root, ignore=shutil.ignore_patterns(".git", "artifacts"))
    stem = world.stems[0]
    meta = root / world.inputs["environments_dir"] / stem / "deadbeef" / "metadata.json"
    _edit_json(meta, lambda d: d["baseline_actions"].pop())
    result = vr.check_public_level_count(prereg, root)
    assert not result.passed
    assert any("metadata lists" in p for p in result.observed["problems"])


# ------------------------------------------------------------------ rhae_synthetic_vectors


def test_rhae_synthetic_vectors_pass(prereg: dict[str, Any]) -> None:
    result = vr.check_rhae_synthetic_vectors(prereg, ROOT)
    assert result.passed, result.observed
    assert result.observed["delegates"] is True
    assert result.observed["failing"] == 0
    assert set(vr.threshold(prereg, "rhae_synthetic_required_tags")) <= set(
        result.observed["tags_seen"]
    )


def test_rhae_synthetic_vectors_fail_on_a_tampered_expectation(prereg: dict[str, Any]) -> None:
    tampered = copy.deepcopy(prereg)
    tampered["rhae"]["synthetic_vectors"][2]["expected_total"] += 1.0
    result = vr.check_rhae_synthetic_vectors(tampered, ROOT)
    assert not result.passed
    assert result.observed["failing"] == 1


def test_rhae_synthetic_vectors_fail_without_delegation(
    prereg: dict[str, Any], tmp_path: Path
) -> None:
    tampered = copy.deepcopy(prereg)
    fake = tmp_path / "rhae.py"
    fake.write_text("def score(): return 0\n")
    tampered["rhae"]["implementation"]["module"] = fake.name
    result = vr.check_rhae_synthetic_vectors(tampered, tmp_path)
    assert not result.passed
    assert any("delegate" in p for p in result.observed["problems"])


# ------------------------------------------------------------------ baseline_derivation_vectors


def test_derivation_vectors_pass(prereg: dict[str, Any]) -> None:
    result = vr.check_baseline_derivation_vectors(prereg)
    assert result.passed, result.observed
    assert result.observed["cases"] >= vr.threshold(prereg, "derivation_vectors_min")


def test_derivation_vectors_fail_on_a_tampered_expectation(prereg: dict[str, Any]) -> None:
    tampered = copy.deepcopy(prereg)
    tampered["baseline_derivation_vectors"]["cases"][2]["expected_baseline"] -= (
        4  # D3: lower median
    )
    result = vr.check_baseline_derivation_vectors(tampered)
    assert not result.passed
    assert result.observed["failing"] == 1


# ------------------------------------------------------------------ dataset_manifest


def test_dataset_manifest_passes_on_the_world(
    prereg: dict[str, Any], world: SyntheticWorld
) -> None:
    result = vr.check_dataset_manifest(prereg, world.root)
    assert result.passed, result.observed
    assert result.observed["committed"] is True
    assert result.observed["files"] == world.replay_files


def test_dataset_manifest_fails_on_the_real_root_while_absent(prereg: dict[str, Any]) -> None:
    if (ROOT / "experiments" / "human_replays_manifest.json").exists():
        pytest.skip("dataset manifest present")
    result = vr.check_dataset_manifest(prereg, ROOT)
    assert not result.passed
    assert any("missing" in p for p in result.observed["problems"])


def test_dataset_manifest_fails_on_drift_and_missing_field(
    prereg: dict[str, Any], world: SyntheticWorld, tmp_path: Path
) -> None:
    root = tmp_path / "root"
    shutil.copytree(world.root, root, ignore=shutil.ignore_patterns("artifacts"))
    (root / world.inputs["raw_replays_dir"] / "stray.jsonl").write_text("{}\n")
    result = vr.check_dataset_manifest(prereg, root)
    assert not result.passed
    assert any("drift" in p for p in result.observed["problems"])
    assert result.observed["drift"] == ["present but unlisted: stray.jsonl"]

    (root / world.inputs["raw_replays_dir"] / "stray.jsonl").unlink()
    _edit_json(root / world.inputs["dataset_manifest"], lambda d: d.pop("source_url"))
    result = vr.check_dataset_manifest(prereg, root)
    assert not result.passed
    assert "manifest lacks source_url" in result.observed["problems"]


# ------------------------------------------------------------------ offline_run


def test_offline_run_g2_passes_and_fails_on_wrong_operation(
    prereg: dict[str, Any], world: SyntheticWorld, runs: Path
) -> None:
    hbr = sys.modules["arc_plasticity.evaluation.human_baseline_run"]
    ok = vr.check_offline_run(prereg, runs, mode_key="operation", expected_mode=hbr.OPERATION)
    assert ok.passed, ok.observed
    _edit_json(
        runs / "fixed_0" / "results.json", lambda d: d["results"].__setitem__("operation", "online")
    )
    bad = vr.check_offline_run(prereg, runs, mode_key="operation", expected_mode=hbr.OPERATION)
    assert not bad.passed
    assert any("operation 'online'" in p for p in bad.observed["problems"])


# ------------------------------------------------------------------ replay_ingestion


def test_replay_ingestion_passes(prereg: dict[str, Any], world: SyntheticWorld) -> None:
    result = vr.check_replay_ingestion(prereg, _artifacts(world), world.root)
    assert result.passed, result.observed
    row = result.observed["runs"]["fixed_0"]
    assert row["input_manifest_equals_dataset_manifest"] is True
    assert row["replay_units_ingested"] >= vr.threshold(prereg, "replay_units_min")


def test_replay_ingestion_fails_below_unit_floor(
    prereg: dict[str, Any], world: SyntheticWorld, runs: Path
) -> None:
    floor = int(vr.threshold(prereg, "replay_units_min"))
    _edit_json(
        runs / "fixed_0" / "results.json",
        lambda d: d["results"].__setitem__("replay_units_ingested", floor - 1),
    )
    result = vr.check_replay_ingestion(prereg, runs, world.root)
    assert not result.passed
    assert any("replay_units_ingested" in p for p in result.observed["problems"])


def test_replay_ingestion_fails_on_a_parse_failure(
    prereg: dict[str, Any], world: SyntheticWorld, runs: Path
) -> None:
    _edit_json(
        runs / "fixed_0" / "results.json",
        lambda d: d["results"].__setitem__("replay_parse_failures", 1),
    )
    result = vr.check_replay_ingestion(prereg, runs, world.root)
    assert not result.passed
    assert any("replay_parse_failures" in p for p in result.observed["problems"])


def test_replay_ingestion_fails_when_the_run_read_other_bytes(
    prereg: dict[str, Any], world: SyntheticWorld, runs: Path
) -> None:
    def drop_one(d: dict[str, Any]) -> None:
        d["raw_files"].pop(next(iter(d["raw_files"])))

    _edit_json(runs / "fixed_1" / "input_manifest.json", drop_one)
    result = vr.check_replay_ingestion(prereg, runs, world.root)
    assert not result.passed
    assert any("input manifest differs" in p for p in result.observed["problems"])
    assert result.observed["runs"]["fixed_1"]["input_manifest_equals_dataset_manifest"] is False


# ------------------------------------------------------------------ human_baseline_coverage


def test_coverage_passes(prereg: dict[str, Any], world: SyntheticWorld) -> None:
    result = vr.check_human_baseline_coverage(prereg, _artifacts(world))
    assert result.passed, result.observed
    row = result.observed["runs"]["fixed_0"]
    assert row["derived_levels"] == world.expected_derived_levels
    assert row["coverage"] >= vr.threshold(prereg, "human_baseline_level_coverage_min")
    assert row["exact_agreement_fraction"] == 1.0


def test_coverage_fails_below_the_floor(
    prereg: dict[str, Any], world: SyntheticWorld, runs: Path
) -> None:
    coverage_min = float(vr.threshold(prereg, "human_baseline_level_coverage_min"))
    levels_total = int(vr.threshold(prereg, "public_levels_total"))
    keep = int(coverage_min * levels_total) - 1

    def strip(d: dict[str, Any]) -> None:
        n = 0
        for game in d["games"]:
            for lv in game["levels"]:
                if lv["derived_baseline_actions"] is not None:
                    n += 1
                    if n > keep:
                        lv["derived_baseline_actions"] = None
                        lv["exact_agreement"] = None
                        lv["relative_difference"] = None
                        lv["n_participants_with_completion"] = 0
                        lv["per_participant_best_counts_sorted"] = []

    _edit_json(runs / "fixed_0" / "human_baselines.json", strip)
    _edit_json(
        runs / "fixed_0" / "results.json",
        lambda d: d["results"].update(
            {"derived_levels": keep, "human_baseline_level_coverage": keep / levels_total}
        ),
    )
    result = vr.check_human_baseline_coverage(prereg, runs)
    assert not result.passed
    assert any("below" in p for p in result.observed["problems"])


def test_coverage_fails_on_a_non_integer_derived_value(prereg: dict[str, Any], runs: Path) -> None:
    _edit_json(
        runs / "fixed_0" / "human_baselines.json",
        lambda d: d["games"][0]["levels"][0].__setitem__("derived_baseline_actions", 12.5),
    )
    result = vr.check_human_baseline_coverage(prereg, runs)
    assert not result.passed
    assert any("not a positive int" in p for p in result.observed["problems"])


def test_coverage_fails_when_results_disagree_with_the_table(
    prereg: dict[str, Any], runs: Path
) -> None:
    _edit_json(
        runs / "fixed_0" / "results.json", lambda d: d["results"].__setitem__("derived_levels", 1)
    )
    result = vr.check_human_baseline_coverage(prereg, runs)
    assert not result.passed
    assert any("derived_levels" in p for p in result.observed["problems"])


# ------------------------------------------------------------------ exclusion nesting, determinism


def test_exclusion_nesting_covers_human_baselines(
    prereg: dict[str, Any], runs: Path, excluded: frozenset[str]
) -> None:
    files = ("results.json", "human_baselines.json")
    ok = vr.check_exclusion_nesting(prereg, runs, excluded, files)
    assert ok.passed, ok.observed
    _edit_json(
        runs / "fixed_0" / "human_baselines.json",
        lambda d: d["games"][0]["levels"][0].__setitem__("session_id", "hidden"),
    )
    bad = vr.check_exclusion_nesting(prereg, runs, excluded, files)
    assert not bad.passed
    assert any("human_baselines.json" in p and "session_id" in p for p in bad.observed["problems"])


def test_determinism_fixed_seed_passes_and_compares_the_third_file(
    prereg: dict[str, Any], runs: Path, excluded: frozenset[str]
) -> None:
    ok = vr.check_determinism_fixed_seed(prereg, runs, excluded)
    assert ok.passed, ok.observed
    assert ok.observed["identity"] == 1.0
    _edit_json(
        runs / "fixed_1" / "human_baselines.json",
        lambda d: d["games"][0]["levels"][0].__setitem__("derived_baseline_actions", 999),
    )
    _reseal(runs / "fixed_1")
    bad = vr.check_determinism_fixed_seed(prereg, runs, excluded)
    assert not bad.passed
    assert bad.observed["identity"] == 0.0


def test_determinism_fixed_seed_rejects_unregistered_seeds(
    prereg: dict[str, Any], runs: Path, excluded: frozenset[str]
) -> None:
    _edit_json(runs / "fixed_1" / "manifest.json", lambda d: d.__setitem__("seed", 7))
    result = vr.check_determinism_fixed_seed(prereg, runs, excluded)
    assert not result.passed
    assert any("not pre-registered" in p for p in result.observed["problems"])


def test_determinism_fixed_seed_refuses_an_inconsistent_protocol(
    prereg: dict[str, Any], tmp_path: Path
) -> None:
    broken = copy.deepcopy(prereg)
    broken["determinism_protocol"]["require_contrast_differs"] = True
    with pytest.raises(vr.PreregistrationError, match="contrast"):
        vr.check_determinism_fixed_seed(broken, tmp_path, frozenset())


# ------------------------------------------------------------------ sha256 seal covers the extras


def test_sha256sums_lists_and_verifies_the_four_extras(
    prereg: dict[str, Any], world: SyntheticWorld, runs: Path
) -> None:
    ok = vr.check_sha256sums(prereg, runs)
    assert ok.passed, ok.observed
    listed = (runs / "fixed_0" / "SHA256SUMS").read_text()
    for name in prereg["verification"]["additional_run_artifacts"]:
        assert f"  {name}" in listed
    (runs / "fixed_0" / "replay_ingestion_log.jsonl").write_text("{}\n")
    bad = vr.check_sha256sums(prereg, runs)
    assert not bad.passed
    assert any("replay_ingestion_log.jsonl" in p for p in bad.observed["problems"])
