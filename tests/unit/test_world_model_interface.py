"""Unit tests for src/arc_plasticity/hypotheses/interface.py: the wire encoding round-trips,
malformed values are refused with informative errors, the stateful adapter equals the
functional form, and the interface digest is the file's digest."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from arc_plasticity.environments.arc_interface import ActionRecord
from arc_plasticity.hypotheses import interface as wi
from tests.g3_synthetic import DEFAULT_ACTIONS, INITIAL, SyntheticModel, act, synthetic_history


def test_history_round_trips_through_wire() -> None:
    history = synthetic_history(DEFAULT_ACTIONS)
    wire = wi.history_to_wire(history)
    assert wire[0]["action"] is None
    assert wire[1]["action"] == {"action": 1, "data": {}}
    assert wire[4]["action"] == {"action": 6, "data": {"x": 2, "y": 3}}
    assert wi.history_from_wire(wire) == history


def test_observation_from_wire_rejects_missing_and_malformed_fields() -> None:
    good = wi.observation_to_wire(INITIAL)
    assert wi.observation_from_wire(good) == INITIAL
    with pytest.raises(wi.HistoryError, match="lacks fields"):
        wi.observation_from_wire({k: v for k, v in good.items() if k != "state"})
    with pytest.raises(wi.HistoryError, match="not a mapping|must be a mapping"):
        wi.observation_from_wire([1, 2, 3])
    bad_cell = dict(good, frame=[[["x", 0, 0, 0]] + [[0] * 4] * 3])
    with pytest.raises(wi.HistoryError, match="not an int"):
        wi.observation_from_wire(bad_cell)
    with pytest.raises(wi.HistoryError, match="state must be a str"):
        wi.observation_from_wire(dict(good, state=3))


def test_history_from_wire_requires_reset_record_first() -> None:
    wire = wi.history_to_wire(synthetic_history(DEFAULT_ACTIONS[:2]))
    with pytest.raises(wi.HistoryError, match="reset observation"):
        wi.history_from_wire(wire[1:])
    with pytest.raises(wi.HistoryError, match="at least the reset"):
        wi.history_from_wire([])


def test_prefix_and_is_prefix_of() -> None:
    history = synthetic_history(DEFAULT_ACTIONS)
    assert len(history) == len(DEFAULT_ACTIONS)
    p3 = history.prefix(3)
    assert len(p3) == 3 and p3.is_prefix_of(history) and not history.is_prefix_of(p3)
    assert history.prefix(0).transitions == ()
    assert history.observation_at(0) == INITIAL
    assert history.observation_at(3) == history.transitions[2].observation
    other = synthetic_history((act(2),) + DEFAULT_ACTIONS[1:3])
    assert not other.is_prefix_of(history)
    with pytest.raises(wi.HistoryError):
        history.prefix(len(history) + 1)


def test_stateful_adapter_matches_functional_model() -> None:
    class Stateful:
        def __init__(self) -> None:
            self.model = SyntheticModel()
            self.history: wi.History | None = None

        def reset(self, initial: wi.Observation) -> None:
            self.history = wi.History(initial)

        def step(self, action: ActionRecord) -> wi.Observation:
            assert self.history is not None
            observation = self.model.predict(self.history, action)
            self.history = self.history.extend(action, observation)
            return observation

    history = synthetic_history(DEFAULT_ACTIONS)
    adapter = wi.StatefulAdapter(Stateful())
    functional = SyntheticModel()
    assert isinstance(adapter, wi.WorldModel)
    for i, transition in enumerate(history.transitions):
        prefix = history.prefix(i)
        assert adapter.predict(prefix, transition.action) == functional.predict(
            prefix, transition.action
        )


def test_interface_sha256_is_the_file_digest() -> None:
    path = Path(wi.__file__)
    assert wi.interface_sha256() == hashlib.sha256(path.read_bytes()).hexdigest()
    assert wi.CERTIFICATION_FIELDS == ("frame", "state", "levels_completed")
    assert "available_actions" in wi.COMPARED_FIELDS
    assert "available_actions" not in wi.CERTIFICATION_FIELDS
