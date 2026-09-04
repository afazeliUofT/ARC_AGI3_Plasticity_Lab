"""Unit tests for the run artifact writer, checked against the gate verifier's own contract."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from arc_plasticity.core.artifacts import (
    CONTRACT_FILES,
    ArtifactError,
    RunArtifactWriter,
    RunManifest,
)

ROOT = Path(__file__).resolve().parents[2]


def _verifier() -> ModuleType:
    if "verify_run" in sys.modules:
        return sys.modules["verify_run"]
    spec = importlib.util.spec_from_file_location("verify_run", ROOT / "scripts" / "verify_run.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _manifest(**overrides: object) -> RunManifest:
    base: dict[str, object] = {
        "experiment_id": "E000_bootstrap",
        "run_id": "r1",
        "timestamp_utc": "2026-09-04T00:00:00Z",
        "git_commit": "abc",
        "git_dirty": False,
        "python_version": "3.12.0",
        "dependency_lock_hash": "0" * 64,
        "config_hash": "1" * 64,
        "environment_generator_version": "toy-grid-1.0.0",
        "seed": 1,
        "model_identifier": None,
        "prompt_hash": None,
        "action_budget": 1,
        "simulation_budget": 0,
        "token_budget": 0,
        "persistent_state_size_cap": 0,
        "hardware": "test",
        "wallclock_limit_seconds": 10,
        "completion_status": "completed",
        "wallclock_seconds": 0.1,
        "network_calls_allowed": 0,
        "network_attempts": 0,
        "model_calls_allowed": 0,
        "model_calls": 0,
    }
    base.update(overrides)
    return RunManifest(**base)  # type: ignore[arg-type]


def _write_full_run(run_dir: Path) -> dict[str, str]:
    with RunArtifactWriter(run_dir) as w:
        w.write_resolved_config("seed: 1\n")
        w.write_git_state("commit abc\n")
        w.write_environment_info({"hostname": "h"})
        w.log("hello")
        w.log_error("")
        w.append_transition({"step": 1, "action": 0})
        w.append_hypothesis({"step": 1, "text": "none"})
        w.append_memory_operation({"op": "noop"})
        w.write_results({"score": 0.5, "run_id": "r1"})
        w.write_metrics([{"metric": "score", "value": 0.5}])
        w.write_environment_results([{"env": "e", "score": 1}], ("env", "score"))
        w.write_manifest(_manifest())
        return w.finalize()


def test_contract_matches_the_verifier() -> None:
    vr = _verifier()
    assert tuple(CONTRACT_FILES) == tuple(vr.REQUIRED_RUN_FILES)
    assert set(vr.REQUIRED_MANIFEST_KEYS) <= set(RunManifest.__dataclass_fields__)


def test_full_run_passes_verifier_checks(tmp_path: Path) -> None:
    vr = _verifier()
    digests = _write_full_run(tmp_path / "r1")
    assert set(digests) == set(CONTRACT_FILES) - {"SHA256SUMS"}
    prereg, _, _ = vr.load_preregistration("G0", ROOT)
    assert vr.check_run_completeness(tmp_path).passed
    sums = vr.check_sha256sums(prereg, tmp_path)
    assert sums.passed, sums.observed


def test_sha256sums_uses_sha256sum_format(tmp_path: Path) -> None:
    run = tmp_path / "r1"
    _write_full_run(run)
    for line in (run / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((run / name).read_bytes()).hexdigest() == digest
    assert "SHA256SUMS" not in (run / "SHA256SUMS").read_text()


def test_jsonl_streams_round_trip(tmp_path: Path) -> None:
    run = tmp_path / "r1"
    _write_full_run(run)
    lines = (run / "transitions.jsonl").read_text().splitlines()
    assert [json.loads(line) for line in lines] == [{"action": 0, "step": 1}]
    assert (run / "stdout.log").read_text() == "hello\n"


def test_refuses_existing_run_directory(tmp_path: Path) -> None:
    (tmp_path / "r1").mkdir()
    with pytest.raises(ArtifactError, match="never overwritten"):
        RunArtifactWriter(tmp_path / "r1").open()


def test_refuses_to_write_a_contract_file_twice(tmp_path: Path) -> None:
    with RunArtifactWriter(tmp_path / "r1") as w:
        w.write_results({"a": 1})
        with pytest.raises(ArtifactError, match="already written"):
            w.write_results({"a": 2})


def test_refuses_writes_after_seal(tmp_path: Path) -> None:
    run = tmp_path / "r1"
    _write_full_run(run)
    w = RunArtifactWriter(tmp_path / "r2")
    w.open()
    w.write_resolved_config("x\n")
    w.write_git_state("x\n")
    w.write_environment_info({})
    w.write_results({})
    w.write_metrics([])
    w.write_environment_results([], ("env",))
    w.write_manifest(_manifest(run_id="r2"))
    w.finalize()
    assert w.sealed
    with pytest.raises(ArtifactError, match="sealed"):
        w.log("late")
    with pytest.raises(ArtifactError, match="sealed"):
        w.write_results({})


def test_seal_refuses_incomplete_run(tmp_path: Path) -> None:
    with RunArtifactWriter(tmp_path / "r1") as w, pytest.raises(ArtifactError, match="missing"):
        w.finalize()


def test_csv_rows_must_match_columns(tmp_path: Path) -> None:
    with RunArtifactWriter(tmp_path / "r1") as w, pytest.raises(ArtifactError, match="mismatch"):
        w.write_metrics([{"metric": "a", "value": 1, "extra": 2}])


def test_manifest_rejects_unknown_status() -> None:
    with pytest.raises(ArtifactError):
        _manifest(completion_status="done")


# ------------------------------------------------------------------ extra artifacts (G1)


def test_extra_json_is_written_once_and_sealed(tmp_path: Path) -> None:
    run = tmp_path / "r1"
    with RunArtifactWriter(run, ("throughput.json",)) as w:
        w.write_resolved_config("seed: 1\n")
        w.write_git_state("commit abc\n")
        w.write_environment_info({})
        w.write_results({})
        w.write_metrics([])
        w.write_environment_results([], ("env",))
        w.write_manifest(_manifest())
        w.write_extra_json(
            "throughput.json", {"aggregate": {"steps": 1, "step_seconds": 0.5, "fps": 2.0}}
        )
        with pytest.raises(ArtifactError, match="already written"):
            w.write_extra_json("throughput.json", {})
        digests = w.finalize()
    assert "throughput.json" in digests
    assert json.loads((run / "throughput.json").read_text())["aggregate"]["steps"] == 1
    assert "  throughput.json" in (run / "SHA256SUMS").read_text()


def test_extra_json_refuses_undeclared_names(tmp_path: Path) -> None:
    with (
        RunArtifactWriter(tmp_path / "r1", ("throughput.json",)) as w,
        pytest.raises(ArtifactError, match="not a declared extra artifact"),
    ):
        w.write_extra_json("timing.json", {})
    with (
        RunArtifactWriter(tmp_path / "r2") as w,
        pytest.raises(ArtifactError, match="not a declared extra artifact"),
    ):
        w.write_extra_json("throughput.json", {})


@pytest.mark.parametrize("name", ["results.json", "notes.txt", "sub/x.json", ".hidden.json"])
def test_extra_artifact_declarations_are_validated(tmp_path: Path, name: str) -> None:
    with pytest.raises(ArtifactError):
        RunArtifactWriter(tmp_path / "r1", (name,))
