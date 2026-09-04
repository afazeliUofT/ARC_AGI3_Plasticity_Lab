"""Seeded wrong models for the backtest-rejection experiment (preregistration/G3.yaml
``backtest_rejection_experiment.wrong_models``).

Each of the eight classes wraps a base :class:`WorldModel` (normally the
:class:`~arc_plasticity.hypotheses.true_model.TrueModel`) with one mutation whose parameters
are drawn from a ``numpy.random.Generator`` and recorded in a :class:`MutationSpec`, so a
trial is reproducible from its seed and its spec is JSON. The backtester never sees the spec.

Index-targeted classes mutate the prediction for exactly one transition ``index`` (0-based;
the prediction made from ``history.prefix(index)``), drawn uniformly over the whole history
including the first and the last transition.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from arc_plasticity.environments.arc_interface import ActionRecord
from arc_plasticity.hypotheses.interface import (
    Grid,
    History,
    Observation,
    Transition,
    WorldModel,
)

MUTATION_CLASSES: tuple[str, ...] = (
    "identity_model",
    "stale_frame",
    "single_cell_flip",
    "colour_permutation",
    "action_semantics_swap",
    "levels_completed_off_by_one",
    "state_field_wrong",
    "other_game_simulator",
)

ARC_COLOURS = 16
NOT_FINISHED = "NOT_FINISHED"
GAME_OVER = "GAME_OVER"


class MutationError(ValueError):
    """A mutation spec is malformed for the history it is applied to."""


@dataclass(frozen=True)
class MutationSpec:
    """One mutation: its class and JSON-serialisable parameters."""

    mutation_class: str
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mutation_class not in MUTATION_CLASSES:
            raise MutationError(f"unknown mutation class {self.mutation_class!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"mutation_class": self.mutation_class, "params": dict(self.params)}


def draw_mutation(
    mutation_class: str,
    rng: np.random.Generator,
    history: History,
    other_game_ids: Sequence[str] = (),
) -> MutationSpec:
    """Draw the parameters of ``mutation_class`` for ``history`` from ``rng``."""
    n = len(history)
    if n < 1:
        raise MutationError("a mutation needs a history with at least one transition")
    if mutation_class in ("identity_model", "stale_frame"):
        return MutationSpec(mutation_class)
    if mutation_class == "single_cell_flip":
        index = int(rng.integers(0, n))
        target = history.transitions[index].observation
        grid_index = int(rng.integers(0, len(target.frame)))
        grid = target.frame[grid_index]
        row = int(rng.integers(0, len(grid)))
        col = int(rng.integers(0, len(grid[row])))
        delta = int(rng.integers(1, ARC_COLOURS))
        return MutationSpec(
            mutation_class,
            {"index": index, "grid": grid_index, "row": row, "col": col, "colour_delta": delta},
        )
    if mutation_class == "colour_permutation":
        index = int(rng.integers(0, n))
        permutation = [int(v) for v in rng.permutation(ARC_COLOURS)]
        return MutationSpec(mutation_class, {"index": index, "permutation": permutation})
    if mutation_class == "action_semantics_swap":
        present = sorted({int(t.action.action) for t in history.transitions})
        pool = present if len(present) >= 2 else sorted(set(present) | {1, 2, 3, 4})
        a, b = (int(v) for v in rng.choice(pool, size=2, replace=False))
        return MutationSpec(mutation_class, {"action_a": a, "action_b": b})
    if mutation_class == "levels_completed_off_by_one":
        index = int(rng.integers(0, n))
        delta = int(rng.choice([-1, 1]))
        return MutationSpec(mutation_class, {"index": index, "delta": delta})
    if mutation_class == "state_field_wrong":
        return MutationSpec(mutation_class, {"index": int(rng.integers(0, n))})
    if mutation_class == "other_game_simulator":
        if not other_game_ids:
            raise MutationError("other_game_simulator needs at least one other game id")
        other = str(rng.choice(list(other_game_ids)))
        return MutationSpec(mutation_class, {"other_game_id": other})
    raise MutationError(f"unknown mutation class {mutation_class!r}")


def _flip_cell(grid: Grid, row: int, col: int, delta: int) -> Grid:
    rows = [list(r) for r in grid]
    rows[row][col] = (rows[row][col] + delta) % ARC_COLOURS
    return tuple(tuple(r) for r in rows)


def _permute_colours(grid: Grid, permutation: Sequence[int]) -> Grid:
    return tuple(tuple(int(permutation[v % ARC_COLOURS]) for v in row) for row in grid)


def _swap_action(action: ActionRecord, a: int, b: int) -> ActionRecord:
    if action.action == a:
        return ActionRecord(b, action.data)
    if action.action == b:
        return ActionRecord(a, action.data)
    return action


class MutatedModel:
    """``base`` with one :class:`MutationSpec` applied; a :class:`WorldModel`."""

    def __init__(
        self, base: WorldModel, spec: MutationSpec, other_model: WorldModel | None = None
    ) -> None:
        self.base = base
        self.spec = spec
        self.other_model = other_model
        if spec.mutation_class == "other_game_simulator" and other_model is None:
            raise MutationError("other_game_simulator needs the other game's model")

    def predict(self, history: History, action: ActionRecord) -> Observation:
        cls, params = self.spec.mutation_class, self.spec.params
        index = len(history)
        if cls == "identity_model":
            return history.last_observation()
        if cls == "stale_frame":
            stale = history.observation_at(max(index - 2, 0))
            true = self.base.predict(history, action)
            return Observation(
                stale.frame, true.state, true.levels_completed, true.available_actions
            )
        if cls == "action_semantics_swap":
            a, b = int(params["action_a"]), int(params["action_b"])
            swapped = History(
                history.initial,
                tuple(
                    Transition(_swap_action(t.action, a, b), t.observation)
                    for t in history.transitions
                ),
            )
            return self.base.predict(swapped, _swap_action(action, a, b))
        if cls == "other_game_simulator":
            assert self.other_model is not None
            return self.other_model.predict(history, action)
        true = self.base.predict(history, action)
        if index != int(params["index"]):
            return true
        if cls == "single_cell_flip":
            grids = list(true.frame)
            g = int(params["grid"])
            if g >= len(grids):
                raise MutationError(f"grid {g} not in a frame of {len(grids)} grids")
            grids[g] = _flip_cell(
                grids[g], int(params["row"]), int(params["col"]), int(params["colour_delta"])
            )
            return Observation(
                tuple(grids), true.state, true.levels_completed, true.available_actions
            )
        if cls == "colour_permutation":
            frame = tuple(_permute_colours(g, params["permutation"]) for g in true.frame)
            return Observation(frame, true.state, true.levels_completed, true.available_actions)
        if cls == "levels_completed_off_by_one":
            wrong = true.levels_completed + int(params["delta"])
            if wrong < 0:
                wrong = true.levels_completed + 1
            return Observation(true.frame, true.state, wrong, true.available_actions)
        if cls == "state_field_wrong":
            wrong_state = GAME_OVER if true.state == NOT_FINISHED else NOT_FINISHED
            return Observation(
                true.frame, wrong_state, true.levels_completed, true.available_actions
            )
        raise MutationError(f"unknown mutation class {cls!r}")


__all__ = [
    "ARC_COLOURS",
    "MUTATION_CLASSES",
    "MutatedModel",
    "MutationError",
    "MutationSpec",
    "draw_mutation",
]
