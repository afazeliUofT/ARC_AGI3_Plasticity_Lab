"""Smoke tests. These must pass for G0. They are deliberately about the traps."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_state_file_is_valid_json_with_required_keys() -> None:
    st = json.loads((ROOT / "state" / "PROJECT_STATE.json").read_text())
    for key in ("current_gate", "gate_status", "next_action", "mechanisms"):
        assert key in st, f"PROJECT_STATE.json missing {key}"
    assert set(st["mechanisms"]) == {"M1", "M2", "M3", "M4", "M5"}


def test_licence_is_mit_zero() -> None:
    # ARC prize terms require CC0 or MIT-0 for authored code. Plain MIT is not enough,
    # and retrofitting a licence later is painful.
    assert "MIT No Attribution" in (ROOT / "LICENSE").read_text()


def test_arc_toolkit_imports_and_exposes_the_verified_surface() -> None:
    from arc_agi import Arcade, OperationMode
    from arcengine import GameAction, GameState  # noqa: F401
    assert {m.value for m in OperationMode} >= {"normal", "online", "offline", "competition"}
    assert OperationMode.NORMAL.value == "normal", "NORMAL is the default; OFFLINE never downloads"
    assert hasattr(Arcade, "make") and hasattr(Arcade, "get_environments")


def test_rhae_reference_implementation_matches_the_evidence_base() -> None:
    # Settles the arXiv-v1 vs current contradiction from the reference implementation:
    # cap is 1.15 and the square is INSIDE the min.
    from arc_agi.scorecard import EnvironmentScoreCalculator

    c = EnvironmentScoreCalculator(id="t")
    c.add_level(level_index=1, completed=True, actions_taken=10, baseline_actions=10)
    assert c.level_scores[0] == 100.0

    c2 = EnvironmentScoreCalculator(id="t2")
    c2.add_level(level_index=1, completed=True, actions_taken=100, baseline_actions=10)
    assert abs(c2.level_scores[0] - 1.0) < 1e-9, "squared ratio: (10/100)**2 * 100 == 1.0"

    c3 = EnvironmentScoreCalculator(id="t3")
    c3.add_level(level_index=1, completed=True, actions_taken=1, baseline_actions=100)
    assert c3.level_scores[0] == 115.0, "cap is 115, not 100"

    c4 = EnvironmentScoreCalculator(id="t4")
    c4.add_level(level_index=1, completed=False, actions_taken=50, baseline_actions=10)
    assert c4.level_scores[0] == 0.0


def test_offline_mode_finds_nothing_without_a_populated_cache() -> None:
    # Documents the trap rather than asserting a bug: make() returns None, it does not raise.
    import tempfile

    from arc_agi import Arcade, OperationMode

    with tempfile.TemporaryDirectory() as d:
        arc = Arcade(operation_mode=OperationMode.OFFLINE, environments_dir=d)
        assert arc.get_environments() == []
        assert arc.make("ls20") is None, "make() signals failure by returning None"
