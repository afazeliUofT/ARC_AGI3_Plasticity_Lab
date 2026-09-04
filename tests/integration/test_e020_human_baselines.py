"""Integration: the E020 runner through the canonical entry point, then the G2 verifier.

A synthetic world (``tests/g2_synthetic.py``) stands in for the released dataset. The real
runner is invoked through ``scripts/run_experiment.py`` twice at the pre-registered fixed
seed into the world's ``artifacts/`` root; every G2 data check of ``scripts/verify_run.py``
is then evaluated against those artifacts with the world as ``root``. Only the tooling checks
are skipped. Preflight refusals are checked to leave no directory behind.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from arc_plasticity.core.runner import RunPreflightError
from arc_plasticity.evaluation import human_baseline_run as hbr
from tests.g2_synthetic import G1_RUN_IDS, SyntheticWorld, build_world, ingestion_counts

ROOT = Path(__file__).resolve().parents[2]
E020 = ROOT / "configs" / "experiments" / "E020_human_baselines.yaml"


def _script(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def prereg() -> dict[str, Any]:
    data: dict[str, Any]
    data, _, _ = _script("verify_run").load_preregistration("G2", ROOT)
    return data


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory, prereg: dict[str, Any]) -> SyntheticWorld:
    return build_world(tmp_path_factory.mktemp("g2world"), prereg)


def _config_for(world: SyntheticWorld, path: Path, **overrides: Any) -> Path:
    raw = yaml.safe_load(E020.read_text())
    raw["runner_params"] = {**world.runner_params(), **overrides.pop("runner_params", {})}
    raw.update(overrides)
    path.write_text(yaml.safe_dump(raw))
    return path


@pytest.fixture(scope="module")
def two_runs(world: SyntheticWorld, prereg: dict[str, Any]) -> Path:
    rx = _script("run_experiment")
    # Outside the world root so git_status_clean stays true for the committed world.
    cfg = _config_for(world, world.root.parent / f"{world.root.name}_E020.yaml")
    proto = prereg["determinism_protocol"]
    for i in range(int(proto["identical_invocations"])):
        run_dir, status = rx.run(
            cfg,
            seed=int(proto["fixed_seed"]),
            artifacts_root=world.root / "artifacts",
            run_id=f"fixed_{i}",
        )
        assert status == "completed", (run_dir / "stderr.log").read_text()
    return world.root / "artifacts" / "E020_human_baselines"


# ------------------------------------------------------------------ the config in the repo


def test_repo_config_matches_the_preregistration(prereg: dict[str, Any]) -> None:
    raw = yaml.safe_load(E020.read_text())
    exp = prereg["experiment"]
    assert raw["experiment_id"] == exp["experiment_id"]
    assert raw["runner"] == exp["runner"] == hbr.RUNNER_NAME
    assert raw["seed"] == exp["seed"]
    assert raw["wallclock_limit_seconds"] == exp["wallclock_limit_seconds"]
    assert raw["network_calls_allowed"] == exp["network_calls_allowed"]
    assert raw["model_calls_allowed"] == exp["model_calls_allowed"]
    assert raw["runner_params"]["extra_artifacts"] == exp["extra_artifacts"]
    assert (
        raw["runner_params"]["action_budget_multiplier"]
        == prereg["thresholds"]["action_budget_multiplier_for_later_gates"]
    )
    for key in ("raw_replays_dir", "dataset_manifest", "environments_dir", "cache_manifest"):
        assert raw["runner_params"][key] == exp["inputs"][key]
    state = json.loads((ROOT / "state" / "PROJECT_STATE.json").read_text())
    assert set(raw["runner_params"]["g1_run_ids"]) == set(state["verifier_reports"]["G1"]["runs"])


# ------------------------------------------------------------------ preflight


def test_preflight_refuses_without_dataset_manifest(world: SyntheticWorld, tmp_path: Path) -> None:
    rx = _script("run_experiment")
    cfg = _config_for(
        world,
        tmp_path / "cfg.yaml",
        runner_params={"dataset_manifest": str(tmp_path / "absent_manifest.json")},
    )
    with pytest.raises(RunPreflightError, match="does not exist"):
        rx.run(cfg, artifacts_root=tmp_path / "artifacts")
    assert not (tmp_path / "artifacts").exists(), "a refused run must leave no directory"


def test_preflight_refuses_on_raw_drift(world: SyntheticWorld, tmp_path: Path) -> None:
    rx = _script("run_experiment")
    drifted = tmp_path / "raw"
    drifted.mkdir()
    (drifted / "extra.jsonl").write_text("{}\n")
    cfg = _config_for(world, tmp_path / "cfg.yaml", runner_params={"raw_replays_dir": str(drifted)})
    with pytest.raises(RunPreflightError, match="drift"):
        rx.run(cfg, artifacts_root=tmp_path / "artifacts")
    assert not (tmp_path / "artifacts").exists()


def test_cli_exits_2_on_preflight_refusal(world: SyntheticWorld, tmp_path: Path) -> None:
    cfg = _config_for(
        world,
        tmp_path / "cfg.yaml",
        runner_params={"dataset_manifest": str(tmp_path / "absent_manifest.json")},
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_experiment.py"),
            "--config",
            str(cfg),
            "--artifacts-root",
            str(tmp_path / "artifacts"),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert proc.returncode == 2, proc.stderr
    assert "FAIL preflight" in proc.stderr
    assert not (tmp_path / "artifacts").exists()


def test_real_repo_config_refuses_while_the_dataset_is_absent() -> None:
    """Until the manifest is committed, the repository config cannot create artifacts/E020."""
    if (ROOT / "experiments" / "human_replays_manifest.json").exists():
        pytest.skip("dataset manifest present; the refusal no longer applies")
    rx = _script("run_experiment")
    with pytest.raises(RunPreflightError):
        rx.run(E020, artifacts_root=ROOT / "artifacts")
    assert not (ROOT / "artifacts" / "E020_human_baselines").exists()


# ------------------------------------------------------------------ artifacts


def test_runs_complete_with_every_contract_and_extra_file(
    two_runs: Path, prereg: dict[str, Any]
) -> None:
    vr = _script("verify_run")
    extra = tuple(prereg["verification"]["additional_run_artifacts"])
    completeness = vr.check_run_completeness(two_runs, extra)
    assert completeness.passed, completeness.observed
    sums = vr.check_sha256sums(prereg, two_runs)
    assert sums.passed, sums.observed


def test_results_contract_and_no_timing(two_runs: Path, world: SyntheticWorld) -> None:
    vr = _script("verify_run")
    doc = json.loads((two_runs / "fixed_0" / "results.json").read_text())
    results = doc["results"]
    for key in vr.G2_RESULTS_KEYS:
        assert key in results, key
    assert results["operation"] == hbr.OPERATION
    assert results["network_guard"] == "NetworkGuard"
    units, failures = ingestion_counts(world)
    assert results["replay_units_ingested"] == units == world.replay_files
    assert results["replay_parse_failures"] == failures == 0
    assert results["participant_ids_available"] is True
    assert results["session_order_source"] == "timestamp"
    assert results["public_games_total"] == len(world.stems)
    assert results["public_levels_total_from_metadata"] == world.levels_total
    assert results["derived_levels"] == world.expected_derived_levels
    assert (
        results["human_baseline_level_coverage"]
        == world.expected_derived_levels / world.levels_total
    )
    assert results["exact_agreement_fraction"] == 1.0
    assert results["median_abs_relative_difference"] == 0.0
    text = (two_runs / "fixed_0" / "results.json").read_text() + (
        two_runs / "fixed_0" / "metrics.csv"
    ).read_text()
    for forbidden in ("seconds", "elapsed", "fps"):
        assert forbidden not in text.replace("wallclock_seconds", ""), forbidden
    manifest = json.loads((two_runs / "fixed_0" / "manifest.json").read_text())
    assert manifest["network_attempts"] == 0 and manifest["model_calls"] == 0
    assert manifest["seed"] == 12345


def test_derived_table_reproduces_official_baselines(two_runs: Path, world: SyntheticWorld) -> None:
    table = json.loads((two_runs / "fixed_0" / "human_baselines.json").read_text())
    assert table["public_levels_total"] == world.levels_total
    assert [g["stem"] for g in table["games"]] == world.stems
    none_levels = []
    for game in table["games"]:
        stem = game["stem"]
        assert game["game_id"] == world.game_ids[stem]
        assert [lv["official_baseline_actions"] for lv in game["levels"]] == world.baselines[stem]
        for lv in game["levels"]:
            if lv["derived_baseline_actions"] is None:
                none_levels.append((stem, lv["level"]))
                assert lv["n_participants_with_completion"] == 0
                assert lv["exact_agreement"] is None and lv["relative_difference"] is None
            else:
                assert lv["derived_baseline_actions"] == lv["official_baseline_actions"]
                assert lv["exact_agreement"] is True and lv["relative_difference"] == 0.0
                assert lv["n_participants_with_completion"] == world.participants_per_game
                assert lv["per_participant_best_counts_sorted"] == sorted(
                    lv["per_participant_best_counts_sorted"]
                )
    assert none_levels == [(world.stems[3], len(world.baselines[world.stems[3]]))]
    assert table["totals"]["derived_levels"] == world.expected_derived_levels


def test_second_session_was_excluded(two_runs: Path, world: SyntheticWorld) -> None:
    """P002's faster second session on game 0 must not lower any per-participant best."""
    table = json.loads((two_runs / "fixed_0" / "human_baselines.json").read_text())
    game0 = table["games"][0]
    for lv in game0["levels"]:
        official = lv["official_baseline_actions"]
        assert min(lv["per_participant_best_counts_sorted"]) >= official - 1
    log = [
        json.loads(ln)
        for ln in (two_runs / "fixed_0" / "replay_ingestion_log.jsonl").read_text().splitlines()
    ]
    assert len(log) == world.replay_files
    second = [r for r in log if r["path"].endswith("_P002_s2.jsonl")]
    assert second and second[0]["session_index"] == 2
    assert second[0]["session_order_source"] == "timestamp"
    assert second[0]["field_mapping"]["participant"] == "participant_id"
    assert second[0]["field_mapping"]["levels_completed"] == "data.levels_completed"


def test_input_manifest_and_diagnostic(two_runs: Path, world: SyntheticWorld) -> None:
    inp = json.loads((two_runs / "fixed_0" / "input_manifest.json").read_text())
    dataset = json.loads(world.dataset_manifest.read_text())
    assert inp["raw_files"] == {rel: e["sha256"] for rel, e in dataset["files"].items()}
    assert inp["dataset_manifest"]["revision"] == "synthetic-1"
    assert inp["dataset_manifest"]["retrieval_method"] == "human_placed"
    assert set(inp["g1_results"]) == set(G1_RUN_IDS)
    assert len(inp["metadata_files"]) == len(world.stems)
    assert inp["replay_game_ids_by_stem"][world.stems[0]] == [world.game_ids[world.stems[0]]]
    assert inp["unmatched_replay_game_ids"] == {}
    diag = json.loads((two_runs / "fixed_0" / "g1_termination_vs_budget.json").read_text())
    assert diag["action_budget_multiplier"] == 5
    assert [r["run_id"] for r in diag["runs"]] == list(G1_RUN_IDS)
    first = diag["games"][0]
    assert first["budget_level_1"] == 5 * world.baselines[world.stems[0]][0]
    assert first["budget_all_levels"] == 5 * sum(world.baselines[world.stems[0]])
    assert len(first["g1_runs"]) == len(G1_RUN_IDS)
    assert all(e["within_level_1_budget"] for e in first["g1_runs"])


def test_environment_results_has_one_row_per_level(two_runs: Path, world: SyntheticWorld) -> None:
    with (two_runs / "fixed_0" / "environment_results.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == world.levels_total
    assert list(rows[0]) == list(hbr.ENVIRONMENT_COLUMNS)
    assert rows[0]["official_baseline_actions"] == rows[0]["derived_baseline_actions"]
    with (two_runs / "fixed_0" / "metrics.csv").open(newline="") as fh:
        metrics = {r["metric"]: r["value"] for r in csv.DictReader(fh)}
    assert metrics["derived_levels"] == str(world.expected_derived_levels)
    assert (
        sum(1 for k in metrics if k.startswith("official_baseline_actions[")) == world.levels_total
    )
    assert (
        sum(1 for k in metrics if k.startswith("derived_baseline_actions[")) == world.levels_total
    )


# ------------------------------------------------------------------ the whole G2 evaluator


def test_evaluate_g2_passes_every_data_check_on_the_synthetic_world(
    two_runs: Path, world: SyntheticWorld, prereg: dict[str, Any]
) -> None:
    vr = _script("verify_run")
    checks = vr.evaluate_g2(prereg, two_runs, world.root, skip_tooling=True)
    report = vr.Report("G2", "preregistration/G2.yaml", "synthetic", checks)
    failed = [(c.name, c.observed) for c in report.checks if not c.passed and not c.skipped]
    assert not failed, failed
    assert report.passed
    names = [c.name for c in report.checks]
    expected_order = [
        "public_level_count",
        "rhae_synthetic_vectors",
        "baseline_derivation_vectors",
        "dataset_manifest",
        "run_artifact_completeness",
        "sha256sums_verify",
        "offline_run",
        "replay_ingestion",
        "human_baseline_coverage",
        "exclusion_nesting",
        "nondeterministic_fields_within_bounds",
        "determinism_identity",
        "git_status_clean",
        "licence_text",
    ]
    assert names[: len(expected_order)] == expected_order
    assert set(report.skipped) == {
        "uv_sync_exit_code",
        "pytest_exit_code",
        "pytest_min_tests_collected",
        "ruff_exit_code",
        "mypy_exit_code",
    }
    by_name = {c.name: c for c in report.checks}
    assert by_name["determinism_identity"].observed["identity"] == 1.0
    assert (
        by_name["determinism_identity"].observed["compared_files"]
        == prereg["determinism_protocol"]["compared_files"]
    )
    assert by_name["human_baseline_coverage"].observed["runs"]["fixed_0"]["coverage"] == (
        world.expected_derived_levels / world.levels_total
    )
