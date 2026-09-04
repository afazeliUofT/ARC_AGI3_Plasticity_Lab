"""The world-model interface every candidate program and every backtest agree on.

This module fixes the signature that ``preregistration/G3.yaml`` ``reference_architecture``
``world_model_interface`` leaves to the code: its SHA-256 (:func:`interface_sha256`) is
recorded in every E300 and E310 manifest, so the file is kept small and stable. It carries
no numeric threshold; limits come from the pre-registration through the caller.

Two views of the same contract:

* **In-process objects** implement :class:`WorldModel`: ``predict(history, action)`` returns
  an :class:`Observation`. ``history`` is a :class:`History` - the reset observation plus every
  recorded transition up to the point of prediction. A stateful model (``reset(first)`` then
  ``step(action)``) is wrapped by :class:`StatefulAdapter`; the functional form is canonical.
* **Candidate programs** (the Python source the language model proposes) define a module-level
  ``predict(history, action)`` over plain JSON values, described in :data:`PROGRAM_CONTRACT`.
  :func:`history_to_wire`, :func:`action_to_wire` and :func:`observation_from_wire` are the
  one encoding/decoding used by the sandbox, so parent and worker cannot drift.

Certification fields are ``frame``, ``state`` and ``levels_completed`` (``CERTIFICATION_FIELDS``).
``available_actions`` is predicted, compared and recorded, but never certifies.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from arc_plasticity.environments.arc_interface import ActionRecord, FrameSummary

Grid = tuple[tuple[int, ...], ...]
Frame = tuple[Grid, ...]

CERTIFICATION_FIELDS: tuple[str, ...] = ("frame", "state", "levels_completed")
COMPARED_FIELDS: tuple[str, ...] = CERTIFICATION_FIELDS + ("available_actions",)

PROGRAM_CONTRACT = """\
A candidate program is a Python source file defining, at module level:

    def predict(history: list[dict], action: dict) -> dict

history[0] is the reset observation and history[i] (i >= 1) the observation after the i-th
recorded action. Every record is {"action": {"action": int, "data": {..}} | None,
"frame": list[list[list[int]]], "state": str, "levels_completed": int,
"available_actions": list[int]}; history[0]["action"] is None. ``action`` is
{"action": int, "data": {"x": int, "y": int} or {}}. The return value is
{"frame": list[list[list[int]]], "state": str, "levels_completed": int,
"available_actions": list[int]}: the observation the program expects after ``action``.
The program must be a pure function of its arguments; it runs in a sandbox with no network,
no repository writes and the limits given in preregistration/G3.yaml thresholds.
"""


class WorldModelError(RuntimeError):
    """A prediction could not be produced or decoded. The backtester records it; never certifies."""


class HistoryError(ValueError):
    """A history or observation is malformed."""


@dataclass(frozen=True)
class Observation:
    """What the toolkit returned after an action (or after the reset that started the game)."""

    frame: Frame
    state: str
    levels_completed: int
    available_actions: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.frame, tuple):
            raise HistoryError("frame must be a tuple of grids")
        for grid in self.frame:
            if not isinstance(grid, tuple) or any(not isinstance(row, tuple) for row in grid):
                raise HistoryError("every grid must be a tuple of tuples of ints")

    @classmethod
    def from_summary(cls, summary: FrameSummary) -> Observation:
        return cls(
            frame=summary.frames,
            state=summary.state,
            levels_completed=int(summary.levels_completed),
            available_actions=tuple(int(a) for a in summary.available_actions),
        )

    def field(self, name: str) -> Any:
        if name not in COMPARED_FIELDS:
            raise KeyError(name)
        return getattr(self, name)


@dataclass(frozen=True)
class Transition:
    """One recorded action and the observation that followed it."""

    action: ActionRecord
    observation: Observation


@dataclass(frozen=True)
class History:
    """The reset observation and every transition so far, in order. ``len`` counts transitions."""

    initial: Observation
    transitions: tuple[Transition, ...] = field(default_factory=tuple)

    def __len__(self) -> int:
        return len(self.transitions)

    def prefix(self, n: int) -> History:
        """The history after the first ``n`` transitions."""
        if n < 0 or n > len(self.transitions):
            raise HistoryError(f"prefix length {n} outside 0..{len(self.transitions)}")
        return History(self.initial, self.transitions[:n])

    def last_observation(self) -> Observation:
        return self.transitions[-1].observation if self.transitions else self.initial

    def observation_at(self, index: int) -> Observation:
        """Observation after ``index`` transitions; 0 is the reset observation."""
        if index == 0:
            return self.initial
        return self.transitions[index - 1].observation

    def actions(self) -> tuple[ActionRecord, ...]:
        return tuple(t.action for t in self.transitions)

    def extend(self, action: ActionRecord, observation: Observation) -> History:
        return History(self.initial, self.transitions + (Transition(action, observation),))

    def is_prefix_of(self, other: History) -> bool:
        if self.initial != other.initial or len(self) > len(other):
            return False
        return all(a is b or a == b for a, b in zip(self.transitions, other.transitions))


@runtime_checkable
class WorldModel(Protocol):
    """The canonical (functional) contract."""

    def predict(self, history: History, action: ActionRecord) -> Observation: ...


@runtime_checkable
class StatefulWorldModel(Protocol):
    """The equivalent stateful form: ``reset`` to the first frame, then ``step`` per action."""

    def reset(self, initial: Observation) -> None: ...

    def step(self, action: ActionRecord) -> Observation: ...


class StatefulAdapter:
    """Presents a :class:`StatefulWorldModel` as a :class:`WorldModel`.

    Every ``predict`` replays the history from ``reset`` so the stateful model can never see
    a history it was not given; correctness over speed, which is what a certification needs.
    """

    def __init__(self, model: StatefulWorldModel) -> None:
        self._model = model

    def predict(self, history: History, action: ActionRecord) -> Observation:
        self._model.reset(history.initial)
        for transition in history.transitions:
            self._model.step(transition.action)
        return self._model.step(action)


# --------------------------------------------------------------------------- wire encoding


def action_to_wire(action: ActionRecord) -> dict[str, Any]:
    return {"action": int(action.action), "data": {str(k): int(v) for k, v in action.data.items()}}


def action_from_wire(value: Any) -> ActionRecord:
    if not isinstance(value, Mapping):
        raise HistoryError(f"action must be a mapping, got {type(value).__name__}")
    try:
        return ActionRecord.from_mapping(value)
    except Exception as exc:  # ReplayError or int() failures; the message names the record
        raise HistoryError(f"malformed action {dict(value)!r}: {exc}") from exc


def observation_to_wire(observation: Observation) -> dict[str, Any]:
    return {
        "frame": [[list(row) for row in grid] for grid in observation.frame],
        "state": observation.state,
        "levels_completed": int(observation.levels_completed),
        "available_actions": list(observation.available_actions),
    }


def _grid_from_wire(grid: Any) -> Grid:
    if not isinstance(grid, Sequence) or isinstance(grid, str | bytes):
        raise HistoryError("a grid must be a sequence of rows")
    rows: list[tuple[int, ...]] = []
    for row in grid:
        if not isinstance(row, Sequence) or isinstance(row, str | bytes):
            raise HistoryError("a grid row must be a sequence of ints")
        try:
            rows.append(tuple(int(v) for v in row))
        except (TypeError, ValueError) as exc:
            raise HistoryError(f"a grid cell is not an int: {exc}") from exc
    return tuple(rows)


def observation_from_wire(value: Any) -> Observation:
    """Decode a program's return value (or a history record). Raises :class:`HistoryError`."""
    if not isinstance(value, Mapping):
        raise HistoryError(f"prediction must be a mapping, got {type(value).__name__}")
    missing = [k for k in COMPARED_FIELDS if k not in value]
    if missing:
        raise HistoryError(f"prediction lacks fields {missing}")
    frame_value = value["frame"]
    if not isinstance(frame_value, Sequence) or isinstance(frame_value, str | bytes):
        raise HistoryError("frame must be a sequence of grids")
    state = value["state"]
    if not isinstance(state, str):
        raise HistoryError(f"state must be a str, got {type(state).__name__}")
    try:
        levels = int(value["levels_completed"])
        available = tuple(int(a) for a in value["available_actions"])
    except (TypeError, ValueError) as exc:
        raise HistoryError(f"levels_completed/available_actions not ints: {exc}") from exc
    return Observation(
        frame=tuple(_grid_from_wire(g) for g in frame_value),
        state=state,
        levels_completed=levels,
        available_actions=available,
    )


def history_to_wire(history: History) -> list[dict[str, Any]]:
    """The list a candidate program receives: record 0 is the reset observation."""
    records = [{"action": None, **observation_to_wire(history.initial)}]
    for transition in history.transitions:
        records.append(
            {
                "action": action_to_wire(transition.action),
                **observation_to_wire(transition.observation),
            }
        )
    return records


def transition_to_wire(transition: Transition) -> dict[str, Any]:
    return {
        "action": action_to_wire(transition.action),
        **observation_to_wire(transition.observation),
    }


def history_from_wire(records: Any) -> History:
    if not isinstance(records, Sequence) or not records:
        raise HistoryError("a history needs at least the reset observation")
    first = records[0]
    if not isinstance(first, Mapping) or first.get("action") is not None:
        raise HistoryError("history[0] must be the reset observation with action null")
    initial = observation_from_wire(first)
    transitions: list[Transition] = []
    for record in records[1:]:
        if not isinstance(record, Mapping):
            raise HistoryError("history records must be mappings")
        transitions.append(
            Transition(action_from_wire(record.get("action")), observation_from_wire(record))
        )
    return History(initial, tuple(transitions))


# --------------------------------------------------------------------------- identity


def interface_sha256() -> str:
    """SHA-256 of this file, the value every E300 and E310 manifest records."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


__all__ = [
    "CERTIFICATION_FIELDS",
    "COMPARED_FIELDS",
    "PROGRAM_CONTRACT",
    "Frame",
    "Grid",
    "History",
    "HistoryError",
    "Observation",
    "StatefulAdapter",
    "StatefulWorldModel",
    "Transition",
    "WorldModel",
    "WorldModelError",
    "action_from_wire",
    "action_to_wire",
    "history_from_wire",
    "history_to_wire",
    "interface_sha256",
    "observation_from_wire",
    "observation_to_wire",
    "transition_to_wire",
]
