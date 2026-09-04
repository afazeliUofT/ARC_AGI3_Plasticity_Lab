"""Human-Relative Action Efficiency (RHAE) adapter.

This module does **not** implement RHAE. Per ``CLAUDE.md`` and the G2 pre-registration
(``rhae.implementation.delegation_rule``), the reference implementation is
``arc_agi.scorecard.EnvironmentScoreCalculator``; this module only adapts the project's
level-outcome records to that calculator's ``add_level`` interface and computes the plain mean
over environments, which is what the toolkit's own ``EnvironmentScorecard`` does.

At arc-agi 0.9.9 the calculator computes, per completed level with ``actions > 0``,
``min(((baseline / actions) ** 2) * 100, 115.0)``; weights level ``l`` (1-indexed, passed as
``level_index = position + 1``) by ``w_l = l``; and caps the environment at
``(weight of levels with positive score) / (total weight) * 100``. Every number this module
returns is a percent. The formula lives in the toolkit so that a toolkit change is a substrate
finding, never a silent divergence between the project's ruler and the platform's.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from arc_agi.scorecard import EnvironmentScoreCalculator


class RhaeInputError(ValueError):
    """A level outcome that the reference calculator cannot score meaningfully."""


@dataclass(frozen=True)
class LevelOutcome:
    """One level of one environment, as the agent left it.

    ``human_baseline_actions`` is the official per-level baseline from the environment's
    ``metadata.json`` (or, in G2, the value derived from replays). ``agent_actions`` is the
    number of actions the agent spent on the level; for a level not completed it is the count
    spent before the run stopped (0 if never attempted) and does not influence the score.
    """

    human_baseline_actions: int
    agent_actions: int
    completed: bool

    def __post_init__(self) -> None:
        if isinstance(self.human_baseline_actions, bool) or not isinstance(
            self.human_baseline_actions, int
        ):
            raise RhaeInputError(
                f"human_baseline_actions must be an int, got {self.human_baseline_actions!r}"
            )
        if isinstance(self.agent_actions, bool) or not isinstance(self.agent_actions, int):
            raise RhaeInputError(f"agent_actions must be an int, got {self.agent_actions!r}")
        if not isinstance(self.completed, bool):
            raise RhaeInputError(f"completed must be a bool, got {self.completed!r}")
        if self.human_baseline_actions <= 0:
            raise RhaeInputError(
                f"human_baseline_actions must be positive, got {self.human_baseline_actions}"
            )
        if self.agent_actions < 0:
            raise RhaeInputError(f"agent_actions must be non-negative, got {self.agent_actions}")


def environment_score(levels: Sequence[LevelOutcome], *, game_id: str | None = None) -> float:
    """Score one environment in percent by delegating every level to the toolkit calculator.

    Levels are passed in order with ``level_index = position + 1`` so the toolkit's
    ``w_l = l`` weighting applies exactly as pre-registered. An environment with no levels
    scores 0.0, which is also what the toolkit returns for an empty calculator.
    """
    calculator = EnvironmentScoreCalculator(id=game_id)
    for position, level in enumerate(levels):
        if not isinstance(level, LevelOutcome):
            raise RhaeInputError(f"level {position} is not a LevelOutcome: {level!r}")
        calculator.add_level(
            level_index=position + 1,
            completed=level.completed,
            actions_taken=level.agent_actions,
            baseline_actions=level.human_baseline_actions,
            game_id=game_id,
        )
    return float(calculator.to_score().score)


def total_score(env_scores: Sequence[float]) -> float:
    """Plain (unweighted) mean of per-environment percent scores.

    An empty sequence returns 0.0: nothing was scored, so nothing was earned. Callers that
    need to distinguish "no environments" from "all zero" must check the length themselves.
    """
    if len(env_scores) == 0:
        return 0.0
    return float(sum(float(s) for s in env_scores) / len(env_scores))


def outcomes_from_vector(levels: Sequence[Mapping[str, Any]]) -> list[LevelOutcome]:
    """Build outcomes from the pre-registration's synthetic-vector level records.

    Each record is ``{human: h, agent: a, completed: bool}`` (G2 ``rhae.synthetic_vector_format``).
    Shared by the unit test and the verifier so both exercise the adapter through one path.
    """
    return [
        LevelOutcome(
            human_baseline_actions=record["human"],
            agent_actions=record["agent"],
            completed=record["completed"],
        )
        for record in levels
    ]


def score_vector_case(case: Mapping[str, Any]) -> tuple[list[float], float]:
    """Score one synthetic-vector case: per-environment percents in order, then the total."""
    env_scores = [
        environment_score(outcomes_from_vector(environment["levels"]))
        for environment in case["environments"]
    ]
    return env_scores, total_score(env_scores)
