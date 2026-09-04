"""Unit tests for the candidate-program sandbox: a correct program is certified through the
subprocess; timeouts, memory, network, filesystem, raise, load and protocol failures each yield
not-certified with the recorded reason; program prints cannot corrupt the protocol."""

from __future__ import annotations

from pathlib import Path

import pytest

from arc_plasticity.hypotheses.backtest import BacktestLimits, backtest_program
from arc_plasticity.hypotheses.sandbox import (
    SandboxedProgram,
    SandboxGuards,
    SandboxLimits,
    SandboxViolation,
)
from tests.g3_synthetic import DEFAULT_ACTIONS, SYNTHETIC_PROGRAM_SOURCE, act, synthetic_history

ROOT = Path(__file__).resolve().parents[2]
GIB = 1 << 30

IDENTITY_SOURCE = """
def predict(history, action):
    last = history[-1]
    return {"frame": last["frame"], "state": last["state"],
            "levels_completed": last["levels_completed"],
            "available_actions": last["available_actions"]}
"""


def _limits(**overrides: float) -> BacktestLimits:
    values: dict[str, float] = {
        "backtest_seconds_max": 30.0,
        "predict_seconds_max": 2.0,
        "address_space_bytes_max": 2 * GIB,
    }
    values.update(overrides)
    return BacktestLimits(
        backtest_seconds_max=values["backtest_seconds_max"],
        predict_seconds_max=values["predict_seconds_max"],
        address_space_bytes_max=int(values["address_space_bytes_max"]),
    )


@pytest.fixture
def guards(tmp_path: Path) -> SandboxGuards:
    repo = tmp_path / "repo"
    (repo / "environment_files").mkdir(parents=True)
    (repo / "environment_files" / "secret.py").write_text("x = 1\n")
    (repo / "data").mkdir()
    return SandboxGuards(
        repository_root=repo, forbidden_read_roots=(repo / "environment_files", repo / "data")
    )


def _program(tmp_path: Path, source: str, name: str = "candidate.py") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def test_correct_program_is_certified_through_the_sandbox(
    tmp_path: Path, guards: SandboxGuards
) -> None:
    history = synthetic_history(DEFAULT_ACTIONS)
    record, violations = backtest_program(
        _program(tmp_path, SYNTHETIC_PROGRAM_SOURCE), history, _limits(), guards
    )
    assert record.certified, record
    assert record.history_length == record.history_length_checked == len(DEFAULT_ACTIONS)
    assert record.mismatches == 0 and record.failure_kind is None and violations == []


def test_identity_program_is_rejected_with_first_mismatch(
    tmp_path: Path, guards: SandboxGuards
) -> None:
    history = synthetic_history((act(3), act(3), act(1), act(3)))
    record, _ = backtest_program(_program(tmp_path, IDENTITY_SOURCE), history, _limits(), guards)
    assert not record.certified
    assert record.failure_kind is None  # the program ran to the end; it is simply wrong
    assert record.history_length_checked == 4
    assert record.mismatches == 1 and record.first_mismatch_index == 2


def test_sandbox_transport_is_incremental_but_program_sees_full_history(
    tmp_path: Path, guards: SandboxGuards
) -> None:
    source = """
def predict(history, action):
    last = history[-1]
    return {"frame": [[[len(history)] * 4] * 4], "state": "NOT_FINISHED",
            "levels_completed": 0, "available_actions": [1]}
"""
    history = synthetic_history(DEFAULT_ACTIONS)
    with SandboxedProgram(_program(tmp_path, source), _limits().sandbox_limits(), guards) as p:
        for i in range(len(history)):
            prediction = p.predict(history.prefix(i), history.transitions[i].action)
            assert prediction.frame[0][0][0] == i + 1  # records = transitions + reset
        # A non-extending history forces a full resend and still gives the right length.
        prediction = p.predict(history.prefix(2), act(1))
        assert prediction.frame[0][0][0] == 3


@pytest.mark.parametrize(
    ("source", "kind", "needle"),
    [
        (
            "def predict(history, action):\n    while True:\n        pass\n",
            "predict_timeout",
            "PredictTimeout",
        ),
        (
            (
                "def predict(history, action):\n    try:\n        while True:\n            pass\n"
                "    except BaseException:\n        while True:\n            pass\n"
            ),
            "predict_timeout",
            "no response",
        ),
        (
            "def predict(history, action):\n    b = bytearray(3 << 30)\n    return {}\n",
            "memory",
            "MemoryError",
        ),
        (
            (
                "import socket\ndef predict(history, action):\n"
                "    socket.create_connection(('127.0.0.1', 9), timeout=1)\n    return {}\n"
            ),
            "network",
            "allowance of 0",
        ),
        (
            "def predict(history, action):\n    raise ValueError('nope')\n",
            "raised",
            "ValueError: nope",
        ),
        (
            "def predict(history, action):\n    return {'frame': [[[0]]]}\n",
            "protocol",
            "lacks fields",
        ),
        ("def predict(history, action):\n    return 5\n", "protocol", "must be a mapping"),
    ],
)
def test_violations_are_not_certified_with_reason(
    tmp_path: Path, guards: SandboxGuards, source: str, kind: str, needle: str
) -> None:
    history = synthetic_history(DEFAULT_ACTIONS[:3])
    limits = _limits(predict_seconds_max=0.5)
    record, violations = backtest_program(_program(tmp_path, source), history, limits, guards)
    assert not record.certified
    assert record.failure_kind == kind, record
    assert record.reason is not None and needle in record.reason, record.reason
    assert record.failed_at_index == 0 and record.history_length_checked == 0
    assert violations and violations[0]["kind"] == kind


def test_filesystem_guard_refuses_repository_writes_and_forbidden_reads(
    tmp_path: Path, guards: SandboxGuards
) -> None:
    repo = guards.repository_root
    write_source = f"""
def predict(history, action):
    with open({str(repo / "planted.txt")!r}, "w") as fh:
        fh.write("x")
    return {{}}
"""
    read_source = f"""
def predict(history, action):
    open({str(repo / "environment_files" / "secret.py")!r}).read()
    return {{}}
"""
    pathlib_source = f"""
from pathlib import Path
def predict(history, action):
    Path({str(repo / "planted2.txt")!r}).write_text("x")
    return {{}}
"""
    history = synthetic_history(DEFAULT_ACTIONS[:2])
    for source in (write_source, read_source, pathlib_source):
        record, _ = backtest_program(_program(tmp_path, source), history, _limits(), guards)
        assert record.failure_kind == "filesystem", record
    assert not (repo / "planted.txt").exists() and not (repo / "planted2.txt").exists()


def test_program_may_write_in_its_own_workdir_and_print(
    tmp_path: Path, guards: SandboxGuards
) -> None:
    source = (
        SYNTHETIC_PROGRAM_SOURCE
        + """
_inner = predict
def predict(history, action):
    print("noise on stdout", len(history))
    with open("scratch.txt", "a") as fh:
        fh.write("ok\\n")
    return _inner(history, action)
"""
    )
    history = synthetic_history(DEFAULT_ACTIONS)
    record, _ = backtest_program(_program(tmp_path, source), history, _limits(), guards)
    assert record.certified, record


def test_load_failures_are_recorded(tmp_path: Path, guards: SandboxGuards) -> None:
    history = synthetic_history(DEFAULT_ACTIONS[:2])
    for source, needle in (
        ("def predict(history, action:\n    pass\n", "SyntaxError"),
        ("x = 1\n", "KeyError"),
        ("predict = 3\n", "not callable"),
    ):
        record, violations = backtest_program(
            _program(tmp_path, source), history, _limits(), guards
        )
        assert record.failure_kind == "load_failed" and record.history_length_checked == 0
        assert record.reason is not None and needle in record.reason, record.reason
        assert violations[0]["kind"] == "load_failed"
    record, _ = backtest_program(tmp_path / "absent.py", history, _limits(), guards)
    assert record.failure_kind == "load_failed"


def test_backtest_wallclock_limit_stops_a_slow_program(
    tmp_path: Path, guards: SandboxGuards
) -> None:
    source = "import time\n" + SYNTHETIC_PROGRAM_SOURCE.replace(
        "def predict(history, action):\n", "def predict(history, action):\n    time.sleep(0.3)\n", 1
    )
    history = synthetic_history(DEFAULT_ACTIONS)
    record, _ = backtest_program(
        _program(tmp_path, source), history, _limits(backtest_seconds_max=0.7), guards
    )
    assert not record.certified
    assert record.failure_kind in ("backtest_timeout", "predict_timeout")
    assert 0 < record.history_length_checked < len(history)


def test_sandbox_runs_outside_the_repository_without_credentials(
    tmp_path: Path, guards: SandboxGuards, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARC_API_KEY", "should-not-leak")
    source = """
import os
def predict(history, action):
    return {"frame": [[[len(os.environ.get("ARC_API_KEY", ""))] * 4] * 4],
            "state": os.getcwd(), "levels_completed": 0, "available_actions": []}
"""
    history = synthetic_history(DEFAULT_ACTIONS[:1])
    with SandboxedProgram(_program(tmp_path, source), _limits().sandbox_limits(), guards) as p:
        prediction = p.predict(history.prefix(0), act(1))
        assert prediction.frame[0][0][0] == 0
        assert p.workdir is not None
        assert Path(prediction.state).resolve() == p.workdir.resolve()
        assert not Path(prediction.state).resolve().is_relative_to(ROOT.resolve())
    assert p.workdir is None  # cleaned up on close


def test_limits_reject_non_positive_values() -> None:
    with pytest.raises(ValueError):
        SandboxLimits(0, 1, 1)
    with pytest.raises(ValueError):
        BacktestLimits(1, 1, 0)
    with pytest.raises(ValueError):
        SandboxViolation("not-a-kind", "x")


def test_program_can_import_numpy_under_the_address_space_limit(
    tmp_path: Path, guards: SandboxGuards
) -> None:
    source = (
        "import numpy as np\n"
        + SYNTHETIC_PROGRAM_SOURCE
        + """
_inner = predict
def predict(history, action):
    out = _inner(history, action)
    out["frame"] = [np.asarray(out["frame"][0], dtype=np.int64).tolist()]
    return out
"""
    )
    history = synthetic_history(DEFAULT_ACTIONS)
    record, _ = backtest_program(
        _program(tmp_path, source), history, _limits(address_space_bytes_max=2 * GIB), guards
    )
    assert record.certified, record
