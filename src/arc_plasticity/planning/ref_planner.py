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

**Diagnostics (G3.6b, 2026-09-05).** Every one of the 513 pre-flight searches ended
``not_found`` with ``reason`` ``None``, which only says the queue emptied. A :class:`Plan` now
also records *why* the queue emptied (``queue_exhausted``, ``distinct_states``,
``duplicate_predictions``, ``successors_dropped_at_depth_cap``, ``max_depth_reached``,
``predicted_levels_completed_max``, ``predicted_state_counts``,
``frame_unchanged_predictions``, ``stop_detail``), and :func:`plan_to_next_level` accepts an
optional ``trace`` list that receives one record per prediction. Outcomes and their semantics
are unchanged; the diagnostics are always on and cost one extra digest per expanded node.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
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
    """A plans.jsonl record. ``actions`` is empty unless ``outcome`` is ``found``.

    The diagnostic fields describe the search that produced the record:

    * ``queue_exhausted`` - the BFS queue emptied (the only way to reach ``not_found``).
    * ``distinct_states`` - distinct ``(digest, levels_completed, state)`` keys seen,
      including the start state.
    * ``duplicate_predictions`` - predictions whose key was already seen (not enqueued).
    * ``successors_dropped_at_depth_cap`` - new states predicted at depth ``max_depth`` and
      therefore never expanded; zero with ``queue_exhausted`` means the model's reachable set
      closed on its own, non-zero means the depth cap truncated the frontier.
    * ``max_depth_reached`` - the deepest path length of any prediction.
    * ``predicted_levels_completed_max`` - the largest ``levels_completed`` any prediction
      carried (``None`` when nothing was predicted).
    * ``predicted_state_counts`` - predictions per predicted ``state`` string.
    * ``frame_unchanged_predictions`` - predictions whose digest equals the parent's.
    * ``stop_detail`` - one human-readable sentence summarising the above.
    """

    actions: tuple[ActionRecord, ...]
    hypothesis_id: str
    certification_history_length: int
    planned_from_history_length: int
    target_levels_completed: int
    nodes_expanded: int
    steps_simulated: int
    outcome: str
    reason: str | None = None
    queue_exhausted: bool = False
    distinct_states: int = 0
    duplicate_predictions: int = 0
    successors_dropped_at_depth_cap: int = 0
    max_depth_reached: int = 0
    predicted_levels_completed_max: int | None = None
    predicted_state_counts: dict[str, int] = field(default_factory=dict)
    frame_unchanged_predictions: int = 0
    stop_detail: str = ""

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
            "queue_exhausted": self.queue_exhausted,
            "distinct_states": self.distinct_states,
            "duplicate_predictions": self.duplicate_predictions,
            "successors_dropped_at_depth_cap": self.successors_dropped_at_depth_cap,
            "max_depth_reached": self.max_depth_reached,
            "predicted_levels_completed_max": self.predicted_levels_completed_max,
            "predicted_state_counts": dict(sorted(self.predicted_state_counts.items())),
            "frame_unchanged_predictions": self.frame_unchanged_predictions,
            "stop_detail": self.stop_detail,
        }


TRACE_DIGEST_PREFIX = 12


def _trace_record(
    *,
    node_index: int,
    depth: int,
    action: ActionRecord,
    parent_digest: str,
    predicted: Observation,
    predicted_digest: str,
    duplicate: bool,
    enqueued: bool,
    found: bool,
) -> dict[str, Any]:
    return {
        "node_index": node_index,
        "depth": depth,
        "action": action.action,
        "data": {k: int(v) for k, v in action.data.items()},
        "parent_digest": parent_digest[:TRACE_DIGEST_PREFIX],
        "predicted_digest": predicted_digest[:TRACE_DIGEST_PREFIX],
        "levels_completed": predicted.levels_completed,
        "state": predicted.state,
        "frame_unchanged": predicted_digest == parent_digest,
        "duplicate": duplicate,
        "enqueued": enqueued,
        "found": found,
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
    trace: list[dict[str, Any]] | None = None,
) -> Plan:
    """Breadth-first search in ``model`` from ``history`` for the shortest action sequence
    after which ``levels_completed`` exceeds its current value.

    Each ``predict`` is one program step charged to ``budget`` before it is made; when the
    budget cannot pay, the search stops with ``simulation_budget_exhausted`` and the plan
    carries no actions. Predicted observations are de-duplicated on
    ``(digest, levels_completed, state)`` so a no-op action never re-expands a state.

    ``trace``, when given, receives one record per prediction (node index, depth, action,
    parent and predicted digest prefixes, predicted ``levels_completed`` and ``state``, and
    the duplicate / enqueued / found flags) in search order.
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
    duplicates = 0
    dropped_at_depth_cap = 0
    max_depth_reached = 0
    levels_max: int | None = None
    state_counts: dict[str, int] = {}
    frame_unchanged = 0

    while queue and outcome == PLAN_NOT_FOUND:
        if nodes_expanded >= limits.max_nodes:
            outcome, reason = PLAN_NODE_LIMIT, f"max_nodes {limits.max_nodes} reached"
            break
        node, path = queue.popleft()
        node_index = nodes_expanded
        nodes_expanded += 1
        last = node.last_observation()
        parent_digest = observation_digest(last)
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
            depth = len(next_path)
            max_depth_reached = max(max_depth_reached, depth)
            levels_max = (
                predicted.levels_completed
                if levels_max is None
                else max(levels_max, predicted.levels_completed)
            )
            state_counts[predicted.state] = state_counts.get(predicted.state, 0) + 1
            key = _state_key(predicted)
            predicted_digest = key[0]
            if predicted_digest == parent_digest:
                frame_unchanged += 1
            is_goal = predicted.levels_completed >= target
            duplicate = not is_goal and key in seen
            enqueued = not is_goal and not duplicate and depth < limits.max_depth
            if trace is not None:
                trace.append(
                    _trace_record(
                        node_index=node_index,
                        depth=depth,
                        action=action,
                        parent_digest=parent_digest,
                        predicted=predicted,
                        predicted_digest=predicted_digest,
                        duplicate=duplicate,
                        enqueued=enqueued,
                        found=is_goal,
                    )
                )
            if is_goal:
                outcome, found = PLAN_FOUND, next_path
                break
            if duplicate:
                duplicates += 1
                continue
            seen.add(key)
            if enqueued:
                queue.append((node.extend(action, predicted), next_path))
            else:
                dropped_at_depth_cap += 1

    queue_exhausted = outcome == PLAN_NOT_FOUND and not queue
    if outcome == PLAN_FOUND:
        stop_detail = f"found at depth {len(found)} after {nodes_expanded} nodes"
    elif queue_exhausted:
        stop_detail = (
            f"queue exhausted after {nodes_expanded} nodes and {steps} predictions: "
            f"{len(seen)} distinct states, {duplicates} duplicates, "
            f"{dropped_at_depth_cap} new states dropped at depth cap {limits.max_depth}, "
            f"max depth reached {max_depth_reached}, predicted levels max {levels_max} "
            f"(target {target}), states {dict(sorted(state_counts.items()))}, "
            f"{frame_unchanged} frame-unchanged predictions"
        )
    else:
        stop_detail = f"{outcome}: {reason}"

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
        queue_exhausted=queue_exhausted,
        distinct_states=len(seen),
        duplicate_predictions=duplicates,
        successors_dropped_at_depth_cap=dropped_at_depth_cap,
        max_depth_reached=max_depth_reached,
        predicted_levels_completed_max=levels_max,
        predicted_state_counts=state_counts,
        frame_unchanged_predictions=frame_unchanged,
        stop_detail=stop_detail,
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
    "TRACE_DIGEST_PREFIX",
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
