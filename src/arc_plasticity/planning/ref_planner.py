"""The REF planner and the seeded exploration fallback.

Implements ``preregistration/G3.yaml`` ``reference_architecture`` ``planner``,
``predict_before_act`` (the digest the runner records) and ``exploration_fallback``.

* :func:`plan_to_next_level` runs a breadth-first search **inside a world model** for the
  shortest action sequence that raises ``levels_completed`` by one, charging one program step
  per ``predict`` call to a :class:`SimulationBudget` whose ceiling the runner reads from the
  pre-registration (``simulation_steps_per_game_max``). The search is exact over the model;
  it never touches the environment. Every returned :class:`Plan` names the hypothesis it was
  derived from and that hypothesis's certification ``history_length`` (``plans.jsonl``).
* :class:`ExplorationPolicy` is the only source of randomness in REF: one numpy Generator
  seeded from ``(experiment seed, game index)``, preferring ``(frame digest, action)`` pairs
  not yet tried from the current frame.
* :func:`observation_digest` is the predicted-frame digest recorded before every action.

This module defines no threshold; limits arrive through :class:`PlannerLimits` and
:class:`SimulationBudget`.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from arc_plasticity.core.guards import Deadline
from arc_plasticity.environments.arc_interface import ActionRecord
from arc_plasticity.hypotheses.interface import (
    History,
    Observation,
    WorldModel,
    WorldModelError,
    observation_to_wire,
)

CLICK_ACTION_ID = 6
RESET_ACTION_ID = 0

PLAN_FOUND = "found"
PLAN_NOT_FOUND = "not_found"
PLAN_SIMULATION_BUDGET_EXHAUSTED = "simulation_budget_exhausted"
PLAN_NODE_LIMIT = "node_limit"
PLAN_DEADLINE = "deadline"
PLAN_MODEL_ERROR = "model_error"
PLAN_OUTCOMES: tuple[str, ...] = (
    PLAN_FOUND,
    PLAN_NOT_FOUND,
    PLAN_SIMULATION_BUDGET_EXHAUSTED,
    PLAN_NODE_LIMIT,
    PLAN_DEADLINE,
    PLAN_MODEL_ERROR,
)


class PlannerError(ValueError):
    """Malformed planner inputs."""


class ExplorationError(RuntimeError):
    """The exploration policy has no action to choose from."""


def observation_digest(observation: Observation) -> str:
    """SHA-256 of the certification fields (frame, state, levels_completed) of an observation.

    ``available_actions`` is excluded because it never certifies; two observations with the
    same digest are the same for planning and for the predict-before-act comparison.
    """
    wire = observation_to_wire(observation)
    payload = {
        "frame": wire["frame"],
        "state": wire["state"],
        "levels_completed": wire["levels_completed"],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class SimulationBudget:
    """Counts program steps against a per-run ceiling. Shared by every plan of a game-run."""

    def __init__(self, max_steps: int) -> None:
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps <= 0:
            raise PlannerError(f"max_steps must be a positive int, got {max_steps!r}")
        self.max_steps = max_steps
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.max_steps - self.used

    @property
    def exhausted(self) -> bool:
        return self.used >= self.max_steps

    def try_consume(self, steps: int = 1) -> bool:
        """Charge ``steps`` if they fit; otherwise charge nothing and return ``False``."""
        if steps <= 0:
            raise PlannerError("steps must be positive")
        if self.used + steps > self.max_steps:
            return False
        self.used += steps
        return True

    def to_dict(self) -> dict[str, int]:
        return {"max_steps": self.max_steps, "used": self.used}


@dataclass(frozen=True)
class PlannerLimits:
    """Search bounds below the simulation budget: depth, nodes and the click coordinates
    offered for ACTION6 (empty means clicks are not planned over)."""

    max_depth: int
    max_nodes: int
    click_points: tuple[tuple[int, int], ...] = ()

    def __post_init__(self) -> None:
        if self.max_depth <= 0 or self.max_nodes <= 0:
            raise PlannerError("max_depth and max_nodes must be positive")
        for point in self.click_points:
            if len(point) != 2 or any(v < 0 for v in point):
                raise PlannerError(f"click point {point!r} must be a non-negative (x, y) pair")


@dataclass(frozen=True)
class Plan:
    """A plans.jsonl record. ``actions`` is empty unless ``outcome`` is ``found``."""

    actions: tuple[ActionRecord, ...]
    hypothesis_id: str
    certification_history_length: int
    planned_from_history_length: int
    target_levels_completed: int
    nodes_expanded: int
    steps_simulated: int
    outcome: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in PLAN_OUTCOMES:
            raise PlannerError(f"unknown plan outcome {self.outcome!r}")
        if (self.outcome == PLAN_FOUND) != bool(self.actions):
            raise PlannerError("a plan has actions exactly when its outcome is found")

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [
                {"action": a.action, "data": {k: int(v) for k, v in a.data.items()}}
                for a in self.actions
            ],
            "hypothesis_id": self.hypothesis_id,
            "certification_history_length": self.certification_history_length,
            "planned_from_history_length": self.planned_from_history_length,
            "target_levels_completed": self.target_levels_completed,
            "nodes_expanded": self.nodes_expanded,
            "steps_simulated": self.steps_simulated,
            "outcome": self.outcome,
            "reason": self.reason,
        }


def candidate_actions(
    available_actions: Sequence[int], click_points: Sequence[tuple[int, int]]
) -> list[ActionRecord]:
    """The actions a node expands, in a fixed order: the available ids as given, ACTION6
    fanned out over ``click_points``."""
    out: list[ActionRecord] = []
    for raw in available_actions:
        action = int(raw)
        if action == CLICK_ACTION_ID:
            out.extend(ActionRecord(action, {"x": int(x), "y": int(y)}) for x, y in click_points)
        else:
            out.append(ActionRecord(action))
    return out


def _state_key(observation: Observation) -> tuple[str, int, str]:
    return (observation_digest(observation), observation.levels_completed, observation.state)


def plan_to_next_level(
    model: WorldModel,
    history: History,
    *,
    hypothesis_id: str,
    certification_history_length: int,
    budget: SimulationBudget,
    limits: PlannerLimits,
    deadline: Deadline | None = None,
) -> Plan:
    """Breadth-first search in ``model`` from ``history`` for the shortest action sequence
    after which ``levels_completed`` exceeds its current value.

    Each ``predict`` is one program step charged to ``budget`` before it is made; when the
    budget cannot pay, the search stops with ``simulation_budget_exhausted`` and the plan
    carries no actions. Predicted observations are de-duplicated on
    ``(digest, levels_completed, state)`` so a no-op action never re-expands a state.
    """
    if certification_history_length > len(history):
        raise PlannerError(
            f"certification history_length {certification_history_length} exceeds the "
            f"history planned from ({len(history)})"
        )
    start = history.last_observation()
    target = start.levels_completed + 1
    queue: deque[tuple[History, tuple[ActionRecord, ...]]] = deque([(history, ())])
    seen: set[tuple[str, int, str]] = {_state_key(start)}
    nodes_expanded = 0
    steps = 0
    outcome = PLAN_NOT_FOUND
    reason: str | None = None
    found: tuple[ActionRecord, ...] = ()

    while queue and outcome == PLAN_NOT_FOUND:
        if nodes_expanded >= limits.max_nodes:
            outcome, reason = PLAN_NODE_LIMIT, f"max_nodes {limits.max_nodes} reached"
            break
        node, path = queue.popleft()
        nodes_expanded += 1
        last = node.last_observation()
        for action in candidate_actions(last.available_actions, limits.click_points):
            if deadline is not None and deadline.expired():
                outcome, reason = PLAN_DEADLINE, "planner deadline expired"
                break
            if not budget.try_consume(1):
                outcome = PLAN_SIMULATION_BUDGET_EXHAUSTED
                reason = f"simulation budget {budget.max_steps} exhausted"
                break
            steps += 1
            try:
                predicted = model.predict(node, action)
            except WorldModelError as exc:
                outcome, reason = PLAN_MODEL_ERROR, str(exc)
                break
            except Exception as exc:  # noqa: BLE001 - recorded in the plan, never hidden
                outcome, reason = PLAN_MODEL_ERROR, f"{type(exc).__name__}: {exc}"
                break
            next_path = path + (action,)
            if predicted.levels_completed >= target:
                outcome, found = PLAN_FOUND, next_path
                break
            key = _state_key(predicted)
            if key in seen:
                continue
            seen.add(key)
            if len(next_path) < limits.max_depth:
                queue.append((node.extend(action, predicted), next_path))

    return Plan(
        actions=found,
        hypothesis_id=hypothesis_id,
        certification_history_length=certification_history_length,
        planned_from_history_length=len(history),
        target_levels_completed=target,
        nodes_expanded=nodes_expanded,
        steps_simulated=steps,
        outcome=outcome,
        reason=reason,
    )


class ExplorationPolicy:
    """The deterministic, seeded, model-free fallback (``exploration_fallback``).

    ``choose`` prefers a ``(frame digest, action)`` pair not yet tried from the current frame;
    among the preferred (or, failing that, all) candidates it draws uniformly from the one
    Generator seeded from ``[seed, game_index]``. RESET is chosen only when it is the sole
    available action, because the runner issues RESET itself on GAME_OVER and a voluntary
    reset never tests anything new. ACTION6 coordinates are drawn from the same Generator
    over ``0..grid_size-1`` each time ACTION6 is available, so the stream of draws depends on
    the observation sequence alone.
    """

    def __init__(self, seed: int, game_index: int, *, grid_size: int = 64) -> None:
        if grid_size <= 0:
            raise PlannerError("grid_size must be positive")
        self.seed = int(seed)
        self.game_index = int(game_index)
        self.grid_size = int(grid_size)
        self._rng = np.random.default_rng([self.seed, self.game_index])
        self._tested: set[tuple[str, int, int, int]] = set()
        self.actions_chosen = 0
        self.untested_choices = 0

    def choose(self, observation: Observation) -> ActionRecord:
        available = [int(a) for a in observation.available_actions]
        if not available:
            raise ExplorationError("no available actions to explore")
        if len(available) > 1 and RESET_ACTION_ID in available:
            available = [a for a in available if a != RESET_ACTION_ID]
        digest = observation_digest(observation)
        candidates: list[tuple[ActionRecord, tuple[str, int, int, int]]] = []
        for action in available:
            if action == CLICK_ACTION_ID:
                x = int(self._rng.integers(0, self.grid_size))
                y = int(self._rng.integers(0, self.grid_size))
                candidates.append((ActionRecord(action, {"x": x, "y": y}), (digest, action, x, y)))
            else:
                candidates.append((ActionRecord(action), (digest, action, -1, -1)))
        untested = [c for c in candidates if c[1] not in self._tested]
        pool = untested or candidates
        chosen, key = pool[int(self._rng.integers(0, len(pool)))]
        self._tested.add(key)
        self.actions_chosen += 1
        if untested:
            self.untested_choices += 1
        return chosen

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "game_index": self.game_index,
            "grid_size": self.grid_size,
            "actions_chosen": self.actions_chosen,
            "untested_choices": self.untested_choices,
            "pairs_tested": len(self._tested),
        }


__all__ = [
    "CLICK_ACTION_ID",
    "PLAN_DEADLINE",
    "PLAN_FOUND",
    "PLAN_MODEL_ERROR",
    "PLAN_NODE_LIMIT",
    "PLAN_NOT_FOUND",
    "PLAN_OUTCOMES",
    "PLAN_SIMULATION_BUDGET_EXHAUSTED",
    "RESET_ACTION_ID",
    "ExplorationError",
    "ExplorationPolicy",
    "Plan",
    "PlannerError",
    "PlannerLimits",
    "SimulationBudget",
    "candidate_actions",
    "observation_digest",
    "plan_to_next_level",
]
