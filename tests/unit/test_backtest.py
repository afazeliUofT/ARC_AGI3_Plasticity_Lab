"""Unit tests for the full-history exact backtester and the E310 wrong models.

Synthetic-world tests need no toolkit. The offline-toolkit tests use the cached public games
and the graded G1 action log (skipped when either is absent): the true simulator wrapper is
certified on a short real history, and each of the eight pre-registered mutation classes is
rejected."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from arc_plasticity.environments.arc_interface import ActionRecord
from arc_plasticity.hypotheses import backtest as bt
from arc_plasticity.hypotheses import mutations as mu
from arc_plasticity.hypotheses.interface import History, Observation, WorldModelError
from tests.g3_synthetic import DEFAULT_ACTIONS, SyntheticModel, act, synthetic_history

ROOT = Path(__file__).resolve().parents[2]
ENV_DIR = ROOT / "environment_files"
G1_RUN = ROOT / "artifacts" / "E100_arc_interface" / "20260904T074939Z_seed12345_8383cad8"
SEED = 12345
HISTORY_STEPS = 12

needs_toolkit_cache = pytest.mark.skipif(
    not (ENV_DIR / "ar25").exists() or not (G1_RUN / "transitions.jsonl").exists(),
    reason="offline environment cache or the graded G1 run is absent",
)


def _load_module(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def prereg_limits() -> bt.BacktestLimits:
    """The three sandbox limits exactly as the G3 pre-registration locks them."""
    vr = _load_module("verify_run")
    data, _, _ = vr.load_preregistration("G3", ROOT)
    return bt.BacktestLimits(
        backtest_seconds_max=float(vr.threshold(data, "sandbox_backtest_seconds_max")),
        predict_seconds_max=float(vr.threshold(data, "sandbox_predict_seconds_max")),
        address_space_bytes_max=int(vr.threshold(data, "sandbox_address_space_bytes_max")),
    )


LIMITS = bt.BacktestLimits(
    backtest_seconds_max=60.0, predict_seconds_max=5.0, address_space_bytes_max=1 << 31
)


# --------------------------------------------------------------------------- synthetic


def test_correct_synthetic_model_is_certified_over_the_whole_history() -> None:
    history = synthetic_history(DEFAULT_ACTIONS)
    model = SyntheticModel()
    record = bt.backtest(model, history, LIMITS)
    assert record.certified
    assert record.history_length == record.history_length_checked == len(history)
    assert record.mismatches == 0 and record.first_mismatch_index is None
    assert record.available_actions_mismatches == 0
    assert model.calls == len(history)  # one prediction per transition, every transition
    assert record.backtester == "full_history_exact"
    assert record.certification_fields == ("frame", "state", "levels_completed")
    assert record.interface_sha256 and record.backtest_module_sha256


def test_empty_history_is_certified_vacuously_and_says_so() -> None:
    record = bt.backtest(SyntheticModel(), synthetic_history(()), LIMITS)
    assert record.certified and record.history_length == 0


def test_available_actions_mismatch_is_recorded_but_does_not_decertify() -> None:
    class WrongAvailable:
        def __init__(self) -> None:
            self.inner = SyntheticModel()

        def predict(self, history: History, action: ActionRecord) -> Observation:
            true = self.inner.predict(history, action)
            return Observation(true.frame, true.state, true.levels_completed, (9,))

    record = bt.backtest(WrongAvailable(), synthetic_history(DEFAULT_ACTIONS), LIMITS)
    assert record.certified
    assert record.available_actions_mismatches == len(DEFAULT_ACTIONS)
    assert record.field_mismatch_counts["available_actions"] == len(DEFAULT_ACTIONS)
    assert record.field_mismatch_counts["frame"] == 0


def test_all_transitions_are_checked_even_after_a_mismatch() -> None:
    history = synthetic_history(DEFAULT_ACTIONS)
    spec = mu.MutationSpec("levels_completed_off_by_one", {"index": 0, "delta": 1})
    record = bt.backtest(mu.MutatedModel(SyntheticModel(), spec), history, LIMITS)
    assert not record.certified
    assert record.first_mismatch_index == 0 and record.mismatches == 1
    assert record.history_length_checked == len(history)  # kept going after the mismatch
    assert record.field_mismatch_counts["levels_completed"] == 1


def test_raising_model_is_not_certified_with_reason() -> None:
    class Raises:
        def predict(self, history: History, action: ActionRecord) -> Observation:
            if len(history) == 2:
                raise WorldModelError("simulated step failure")
            return SyntheticModel().predict(history, action)

    record = bt.backtest(Raises(), synthetic_history(DEFAULT_ACTIONS), LIMITS)
    assert not record.certified
    assert record.failure_kind == "raised" and record.failed_at_index == 2
    assert record.reason == "simulated step failure"
    assert record.history_length_checked == 2 and record.mismatches == 0

    class RaisesOther:
        def predict(self, history: History, action: ActionRecord) -> Observation:
            raise KeyError("boom")

    record = bt.backtest(RaisesOther(), synthetic_history(DEFAULT_ACTIONS), LIMITS)
    assert record.failure_kind == "raised" and "KeyError" in (record.reason or "")


def test_backtest_deadline_is_enforced_between_predictions() -> None:
    ticks = iter(range(0, 1000, 10))

    def clock() -> float:
        return float(next(ticks))

    limits = bt.BacktestLimits(
        backtest_seconds_max=25.0, predict_seconds_max=5.0, address_space_bytes_max=1
    )
    record = bt.backtest(SyntheticModel(), synthetic_history(DEFAULT_ACTIONS), limits, clock=clock)
    assert not record.certified and record.failure_kind == "backtest_timeout"
    assert 0 < record.history_length_checked < len(DEFAULT_ACTIONS)


def test_record_to_dict_is_json_and_derives_certified() -> None:
    record = bt.backtest(SyntheticModel(), synthetic_history(DEFAULT_ACTIONS[:2]), LIMITS)
    as_dict = record.to_dict()
    json.dumps(as_dict)
    assert as_dict["certified"] is True and as_dict["certification_fields"] == list(
        bt.CERTIFICATION_FIELDS
    )
    path = Path(bt.__file__)
    assert bt.backtest_module_sha256() == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("mutation_class", mu.MUTATION_CLASSES)
def test_every_mutation_class_is_rejected_on_the_synthetic_world(mutation_class: str) -> None:
    history = synthetic_history(DEFAULT_ACTIONS + (act(4), act(0), act(1)))
    rng = np.random.default_rng(7)
    base = SyntheticModel()
    other: Any = None
    if mutation_class == "other_game_simulator":

        class OtherWorld:
            def predict(self, h: History, a: ActionRecord) -> Observation:
                true = base.predict(h, a)
                return Observation(
                    true.frame, true.state, true.levels_completed + 1, true.available_actions
                )

        other = OtherWorld()
    spec = mu.draw_mutation(mutation_class, rng, history, other_game_ids=("other",))
    json.dumps(spec.to_dict())
    record = bt.backtest(mu.MutatedModel(base, spec, other_model=other), history, LIMITS)
    assert not record.certified, (mutation_class, spec, record)
    assert record.mismatches >= 1 and record.history_length_checked == len(history)


def test_index_targeted_mutations_cover_first_and_last_transition() -> None:
    history = synthetic_history(DEFAULT_ACTIONS)
    n = len(history)
    seen = {
        int(mu.draw_mutation("single_cell_flip", np.random.default_rng(s), history).params["index"])
        for s in range(200)
    }
    assert 0 in seen and n - 1 in seen and seen <= set(range(n))
    for index in (0, n - 1):
        spec = mu.MutationSpec(
            "single_cell_flip", {"index": index, "grid": 0, "row": 2, "col": 2, "colour_delta": 4}
        )
        record = bt.backtest(mu.MutatedModel(SyntheticModel(), spec), history, LIMITS)
        assert not record.certified and record.first_mismatch_index == index


def test_mutation_spec_validation() -> None:
    with pytest.raises(mu.MutationError):
        mu.MutationSpec("no_such_class")
    with pytest.raises(mu.MutationError):
        mu.MutatedModel(
            SyntheticModel(), mu.MutationSpec("other_game_simulator", {"other_game_id": "x"})
        )
    with pytest.raises(mu.MutationError):
        mu.draw_mutation(
            "other_game_simulator", np.random.default_rng(0), synthetic_history(DEFAULT_ACTIONS)
        )
    with pytest.raises(mu.MutationError):
        mu.draw_mutation("identity_model", np.random.default_rng(0), synthetic_history(()))


# --------------------------------------------------------------------------- offline toolkit


@pytest.fixture(scope="module")
def real_history() -> tuple[str, History, list[ActionRecord]]:
    from arc_plasticity.hypotheses import true_model as tm

    game_ids = tm.game_ids_in_action_log(G1_RUN / "transitions.jsonl")
    game_id = next(g for g in game_ids if g.startswith("ar25"))
    actions = tm.read_action_log(G1_RUN / "transitions.jsonl", game_id)[:HISTORY_STEPS]
    assert len(actions) == HISTORY_STEPS
    history = tm.record_history(ENV_DIR, game_id, SEED, actions)
    return game_id, history, actions


@needs_toolkit_cache
def test_true_model_is_certified_on_a_real_history(
    real_history: tuple[str, History, list[ActionRecord]], prereg_limits: bt.BacktestLimits
) -> None:
    from arc_plasticity.hypotheses.true_model import TrueModel

    game_id, history, _ = real_history
    frames_changed = sum(
        1
        for i in range(1, len(history) + 1)
        if history.observation_at(i).frame != history.observation_at(i - 1).frame
    )
    assert frames_changed >= 2, "the test history must contain frame changes"
    model = TrueModel(ENV_DIR, game_id, SEED)
    record = bt.backtest(model, history, prereg_limits)
    assert record.certified, record
    assert record.history_length_checked == len(history) == HISTORY_STEPS
    assert model.rebuilds == 1 and model.steps == HISTORY_STEPS  # the prefix fast path held


@needs_toolkit_cache
def test_true_model_rebuilds_on_a_non_prefix_history(
    real_history: tuple[str, History, list[ActionRecord]],
) -> None:
    from arc_plasticity.hypotheses.true_model import TrueModel

    game_id, history, _ = real_history
    model = TrueModel(ENV_DIR, game_id, SEED)
    a = model.predict(history.prefix(3), history.transitions[3].action)
    b = model.predict(history.prefix(1), history.transitions[1].action)  # goes backwards
    c = model.predict(history.prefix(3), history.transitions[3].action)
    assert a == c == history.transitions[3].observation
    assert b == history.transitions[1].observation
    # a: rebuild + 4 steps; b: rebuild + 2 steps; c extends b's applied prefix: 2 steps, no rebuild
    assert model.rebuilds == 2 and model.steps == 8


@needs_toolkit_cache
@pytest.mark.parametrize("mutation_class", mu.MUTATION_CLASSES)
def test_every_mutation_class_is_rejected_on_a_real_history(
    real_history: tuple[str, History, list[ActionRecord]],
    prereg_limits: bt.BacktestLimits,
    mutation_class: str,
) -> None:
    from arc_plasticity.hypotheses import true_model as tm

    game_id, history, _ = real_history
    rng = np.random.default_rng(SEED)
    other_ids = [g for g in tm.game_ids_in_action_log(G1_RUN / "transitions.jsonl") if g != game_id]
    spec = mu.draw_mutation(mutation_class, rng, history, other_game_ids=other_ids[:3])
    other = (
        tm.TrueModel(ENV_DIR, str(spec.params["other_game_id"]), SEED)
        if mutation_class == "other_game_simulator"
        else None
    )
    model = mu.MutatedModel(tm.TrueModel(ENV_DIR, game_id, SEED), spec, other_model=other)
    record = bt.backtest(model, history, prereg_limits)
    assert not record.certified, (mutation_class, spec, record)
    assert record.mismatches >= 1
    assert record.history_length_checked == record.history_length == len(history)
