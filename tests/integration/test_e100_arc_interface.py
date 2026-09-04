"""Integration: the E100 runner through the canonical entry point satisfies the G1 checks.

Runs configs/experiments/E100_arc_interface.yaml with the per-game budget lowered to 50
actions (25 games x 50 = 1250 steps >= the pre-registered 1000 measured steps) into a
temporary artifacts root, following the G1 determinism protocol (fixed seed twice, contrast
seed once), and evaluates the artifact checks of scripts/verify_run.py against the result. It
never writes under artifacts/E100_arc_interface/; the graded runs are produced separately.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
E100 = ROOT / "configs" / "experiments" / "E100_arc_interface.yaml"
SMOKE_BUDGET_PER_GAME = 50

pytestmark = pytest.mark.skipif(
    not (ROOT / "environment_files").is_dir(), reason="offline cache absent"
)


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
    vr = _script("verify_run")
    data: dict[str, Any]
    data, _, _ = vr.load_preregistration("G1", ROOT)
    return data


@pytest.fixture(scope="module")
def three_runs(tmp_path_factory: pytest.TempPathFactory, prereg: dict[str, Any]) -> Path:
    rx = _script("run_experiment")
    root = tmp_path_factory.mktemp("artifacts")
    raw = yaml.safe_load(E100.read_text())
    raw["runner_params"]["action_budget_per_game"] = SMOKE_BUDGET_PER_GAME
    cfg = root / "E100_smoke.yaml"
    cfg.write_text(yaml.safe_dump(raw))
    proto = prereg["determinism_protocol"]
    for i in range(int(proto["identical_invocations"])):
        run_dir, status = rx.run(
            cfg, seed=int(proto["fixed_seed"]), artifacts_root=root, run_id=f"fixed_{i}"
        )
        assert status == "completed", (run_dir / "stderr.log").read_text()
    for i in range(int(proto["contrast_invocations"])):
        run_dir, status = rx.run(
            cfg, seed=int(proto["contrast_seed"]), artifacts_root=root, run_id=f"contrast_{i}"
        )
        assert status == "completed", (run_dir / "stderr.log").read_text()
    return root / raw["experiment_id"]


def test_runs_satisfy_the_g1_artifact_checks(three_runs: Path, prereg: dict[str, Any]) -> None:
    vr = _script("verify_run")
    extra = tuple(prereg["verification"]["additional_run_artifacts"])
    nd, excluded = vr.check_nondeterministic_fields(prereg, ROOT)
    assert nd.passed, nd.observed
    for check in (
        vr.check_run_completeness(three_runs, extra),
        vr.check_sha256sums(prereg, three_runs),
        vr.check_offline_run(prereg, three_runs),
        vr.check_exclusion_nesting(prereg, three_runs, excluded),
        vr.check_determinism(prereg, three_runs, excluded),
        vr.check_throughput(prereg, three_runs),
    ):
        assert check.passed, (check.name, check.observed)


def test_every_game_replays_identically_in_the_verifier(
    three_runs: Path, prereg: dict[str, Any]
) -> None:
    vr = _script("verify_run")
    replay = vr.check_replay_final_frame_identity(prereg, three_runs, ROOT)
    assert replay.passed, replay.observed
    assert replay.observed["identity"] == 1.0
    assert replay.observed["network_attempts"] == 0
    assert replay.observed["games_attempted"] == 3 * int(
        vr.threshold(prereg, "games_attempted_min")
    )


def test_all_public_games_attempted_with_no_step_failure(
    three_runs: Path, prereg: dict[str, Any]
) -> None:
    vr = _script("verify_run")
    # terminal_games_min is not asserted here: 50 random actions need not end any game.
    for run in ("fixed_0", "fixed_1", "contrast_0"):
        results = json.loads((three_runs / run / "results.json").read_text())["results"]
        games = results["games"]
        assert len(games) == int(vr.threshold(prereg, "games_attempted_min"))
        assert not any(g["step_failed"] for g in games)
        assert all(g["steps_taken"] <= SMOKE_BUDGET_PER_GAME for g in games)
        assert all(len(g["final_frame_sha256"]) == 64 for g in games)
        assert results["operation_mode"] == prereg["experiment"]["operation_mode"]


def test_transitions_identical_for_same_seed_and_differ_for_contrast(three_runs: Path) -> None:
    a = (three_runs / "fixed_0" / "transitions.jsonl").read_bytes()
    b = (three_runs / "fixed_1" / "transitions.jsonl").read_bytes()
    c = (three_runs / "contrast_0" / "transitions.jsonl").read_bytes()
    assert a == b and a
    assert a != c


def test_timing_is_confined_to_throughput_json(three_runs: Path) -> None:
    run = three_runs / "fixed_0"
    metrics = (run / "metrics.csv").read_text()
    assert "seconds" not in metrics and "fps" not in metrics
    results = (run / "results.json").read_text()
    assert "step_seconds" not in results and "fps" not in results
    tp = json.loads((run / "throughput.json").read_text())
    assert tp["aggregate"]["steps"] == sum(g["steps"] for g in tp["per_game"])
    assert len(tp["per_game"]) == 25
    sums = (run / "SHA256SUMS").read_text()
    assert "  throughput.json" in sums


def test_manifest_records_offline_budgets(three_runs: Path) -> None:
    m = json.loads((three_runs / "fixed_0" / "manifest.json").read_text())
    assert m["network_attempts"] == 0 and m["network_calls_allowed"] == 0
    assert m["model_calls"] == 0 and m["model_identifier"] is None
    assert m["environment_generator_version"].startswith("arc-agi-offline-cache-")
    assert m["action_budget"] == 125000
