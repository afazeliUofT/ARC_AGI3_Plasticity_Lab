"""Regression pin for preregistration/G3.yaml backtest_certification: a windowed backtester
(last N transitions only) certifies a model that is wrong at transition index 1, while the
full-history exact backtester rejects it with first_mismatch_index 1 and every transition
checked. Windowed, sampled and tolerance-based backtests are forbidden for exactly this
reason; this test is the counterfactual that shows what the forbidden ruler would do."""

from __future__ import annotations

from arc_plasticity.hypotheses import backtest as bt
from arc_plasticity.hypotheses import mutations as mu
from arc_plasticity.hypotheses.interface import CERTIFICATION_FIELDS, History, WorldModel
from tests.g3_synthetic import DEFAULT_ACTIONS, SyntheticModel, synthetic_history

LIMITS = bt.BacktestLimits(
    backtest_seconds_max=60.0, predict_seconds_max=5.0, address_space_bytes_max=1 << 31
)
WINDOW = 3
FLIP_INDEX = 1


def windowed_backtest(model: WorldModel, history: History, window: int) -> bool:
    """The forbidden ruler: checks only the last ``window`` transitions."""
    start = max(len(history) - window, 0)
    for index in range(start, len(history)):
        transition = history.transitions[index]
        predicted = model.predict(history.prefix(index), transition.action)
        if any(
            predicted.field(name) != transition.observation.field(name)
            for name in CERTIFICATION_FIELDS
        ):
            return False
    return True


def _flipped_model() -> WorldModel:
    spec = mu.MutationSpec(
        "single_cell_flip",
        {"index": FLIP_INDEX, "grid": 0, "row": 3, "col": 3, "colour_delta": 7},
    )
    return mu.MutatedModel(SyntheticModel(), spec)


def test_windowed_backtester_certifies_the_early_flip() -> None:
    history = synthetic_history(DEFAULT_ACTIONS)
    assert len(history) > WINDOW + FLIP_INDEX
    assert windowed_backtest(_flipped_model(), history, WINDOW) is True
    assert windowed_backtest(SyntheticModel(), history, WINDOW) is True


def test_full_history_backtester_rejects_the_early_flip() -> None:
    history = synthetic_history(DEFAULT_ACTIONS)
    record = bt.backtest(_flipped_model(), history, LIMITS)
    assert not record.certified
    assert record.first_mismatch_index == FLIP_INDEX
    assert record.mismatches == 1
    assert record.field_mismatch_counts["frame"] == 1
    assert record.history_length_checked == record.history_length == len(DEFAULT_ACTIONS)
    assert bt.backtest(SyntheticModel(), history, LIMITS).certified
