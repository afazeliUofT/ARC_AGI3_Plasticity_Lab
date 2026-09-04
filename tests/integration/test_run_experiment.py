"""Integration: the canonical entry point produces runs that satisfy the G0 verifier checks.

Runs the real configs/experiments/E000_bootstrap.yaml into a temporary artifacts root, using
the seeds from preregistration/G0.yaml, and evaluates the artifact checks of
scripts/verify_run.py against them. This is the same evaluation the gate will run on the real
artifacts; only the root differs.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from arc_plasticity.core.artifacts import CONTRACT_FILES, RunArtifactWriter
from arc_plasticity.core.config import ExperimentConfig
from arc_plasticity.core.guards import Deadline
from arc_plasticity.core.runner import RunOutcome, register_runner, unregister_runner

ROOT = Path(__file__).resolve().parents[2]
E000 = ROOT / "configs" / "experiments" / "E000_bootstrap.yaml"


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
    data: dict[str, Any] = yaml.safe_load((ROOT / "preregistration" / "G0.yaml").read_text())
    return data


@pytest.fixture(scope="module")
def three_runs(tmp_path_factory: pytest.TempPathFactory, prereg: dict[str, Any]) -> Path:
    rx = _script("run_experiment")
    root = tmp_path_factory.mktemp("artifacts")
    proto = prereg["determinism_protocol"]
    for i in range(int(proto["identical_invocations"])):
        run_dir, status = rx.run(
            E000, seed=int(proto["fixed_seed"]), artifacts_root=root, run_id=f"fixed_{i}"
        )
        assert status == "completed", run_dir
    for i in range(int(proto["contrast_invocations"])):
        run_dir, status = rx.run(
            E000, seed=int(proto["contrast_seed"]), artifacts_root=root, run_id=f"contrast_{i}"
        )
        assert status == "completed", run_dir
    return root / "E000_bootstrap"


def test_runs_are_complete_hashed_and_deterministic(three_runs: Path) -> None:
    vr = _script("verify_run")
    prereg, _, _ = vr.load_preregistration("G0", ROOT)
    nd, excluded = vr.check_nondeterministic_fields(prereg, ROOT)
    assert nd.passed, nd.observed
    completeness = vr.check_run_completeness(three_runs)
    assert completeness.passed, completeness.observed
    sums = vr.check_sha256sums(prereg, three_runs)
    assert sums.passed, sums.observed
    det = vr.check_determinism(prereg, three_runs, excluded)
    assert det.passed, det.observed
    assert det.observed["identity"] == 1.0
    assert det.observed["contrast_differs"] is True


def test_manifest_records_provenance_and_zero_network(three_runs: Path) -> None:
    m = json.loads((three_runs / "fixed_0" / "manifest.json").read_text())
    assert m["completion_status"] == "completed"
    assert m["network_attempts"] == 0 and m["network_calls_allowed"] == 0
    assert m["model_calls"] == 0 and m["model_identifier"] is None
    assert len(m["git_commit"]) == 40
    assert len(m["dependency_lock_hash"]) == 64
    assert len(m["config_hash"]) == 64
    assert m["wallclock_limit_seconds"] == 600
    assert m["environment_generator_version"].startswith("toy-grid-")
    assert set(CONTRACT_FILES) == {p.name for p in (three_runs / "fixed_0").iterdir()}


def test_same_seed_runs_share_config_hash_and_contrast_does_not(three_runs: Path) -> None:
    hashes = {
        name: json.loads((three_runs / name / "manifest.json").read_text())["config_hash"]
        for name in ("fixed_0", "fixed_1", "contrast_0")
    }
    assert hashes["fixed_0"] == hashes["fixed_1"] != hashes["contrast_0"]


def test_transitions_are_identical_for_same_seed(three_runs: Path) -> None:
    a = (three_runs / "fixed_0" / "transitions.jsonl").read_bytes()
    b = (three_runs / "fixed_1" / "transitions.jsonl").read_bytes()
    assert a == b and a


class _NetworkRunner:
    name = "test_network_runner"
    environment_generator_version = "test-0"

    def run(
        self, config: ExperimentConfig, writer: RunArtifactWriter, deadline: Deadline
    ) -> RunOutcome:
        socket.getaddrinfo("example.invalid", 443)
        return RunOutcome({}, [], [], ("environment",))


def test_network_attempt_is_recorded_as_failure_not_hidden(tmp_path: Path) -> None:
    rx = _script("run_experiment")
    register_runner(_NetworkRunner.name, _NetworkRunner)
    try:
        raw = yaml.safe_load(E000.read_text())
        raw["runner"] = _NetworkRunner.name
        cfg = tmp_path / "net.yaml"
        cfg.write_text(yaml.safe_dump(raw))
        run_dir, status = rx.run(cfg, artifacts_root=tmp_path / "artifacts")
    finally:
        unregister_runner(_NetworkRunner.name)
    assert status == "failed"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["completion_status"] == "failed"
    assert manifest["network_attempts"] == 1
    assert "network guard" in (run_dir / "stderr.log").read_text()
    assert (run_dir / "SHA256SUMS").exists(), "a failed run is still sealed evidence"


def test_cli_exit_codes(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_experiment.py"),
            "--config",
            str(E000),
            "--artifacts-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["completion_status"] == "completed"
    assert (Path(out["run_dir"]) / "SHA256SUMS").exists()

    bad = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_experiment.py"),
            "--config",
            str(tmp_path / "missing.yaml"),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert bad.returncode == 2
    assert "FAIL config" in bad.stderr
