"""A tiny deterministic world for testing the world-model interface, sandbox and backtester
without the toolkit. The rule is written once, as a candidate-program source
(:data:`SYNTHETIC_PROGRAM_SOURCE`), and the in-process :class:`SyntheticModel` executes that
same source, so the two views of the contract cannot disagree.

World: one 4x4 grid, colours 0-15.
  action 1: cell (0,0) += 1 mod 16; levels_completed = floor(total action-1 count / 16)
  action 2: cell (1,1) += 3 mod 16
  action 3: no change
  action 4: state becomes GAME_OVER (frame unchanged)
  action 6 with data x, y: cell (y mod 4, x mod 4) += 5 mod 16
  action 0 (RESET): back to the reset observation
available_actions is (1, 2, 3, 4, 6) while NOT_FINISHED and (0,) while GAME_OVER.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from arc_plasticity.environments.arc_interface import ActionRecord
from arc_plasticity.hypotheses.interface import (
    History,
    Observation,
    action_to_wire,
    history_to_wire,
    observation_from_wire,
)

SYNTHETIC_PROGRAM_SOURCE = """
def predict(history, action):
    last = history[-1]
    grid = [list(row) for row in last["frame"][0]]
    state = last["state"]
    ones = sum(1 for rec in history[1:] if rec["action"]["action"] == 1)
    aid = action["action"]
    if aid == 0:
        first = history[0]
        return {
            "frame": [[list(row) for row in first["frame"][0]]],
            "state": "NOT_FINISHED",
            "levels_completed": first["levels_completed"],
            "available_actions": [1, 2, 3, 4, 6],
        }
    if state == "GAME_OVER":
        return {"frame": [grid], "state": state, "levels_completed": last["levels_completed"],
                "available_actions": [0]}
    if aid == 1:
        grid[0][0] = (grid[0][0] + 1) % 16
        ones += 1
    elif aid == 2:
        grid[1][1] = (grid[1][1] + 3) % 16
    elif aid == 4:
        state = "GAME_OVER"
    elif aid == 6:
        x, y = action["data"]["x"] % 4, action["data"]["y"] % 4
        grid[y][x] = (grid[y][x] + 5) % 16
    available = [0] if state == "GAME_OVER" else [1, 2, 3, 4, 6]
    return {"frame": [grid], "state": state, "levels_completed": ones // 16,
            "available_actions": available}
"""

INITIAL = Observation(
    frame=(tuple(tuple(0 for _ in range(4)) for _ in range(4)),),
    state="NOT_FINISHED",
    levels_completed=0,
    available_actions=(1, 2, 3, 4, 6),
)


class SyntheticModel:
    """The correct in-process model of the synthetic world (a ``WorldModel``)."""

    def __init__(self) -> None:
        namespace: dict[str, Any] = {}
        exec(SYNTHETIC_PROGRAM_SOURCE, namespace)  # noqa: S102 - test-owned source
        self._predict = namespace["predict"]
        self.calls = 0

    def predict(self, history: History, action: ActionRecord) -> Observation:
        self.calls += 1
        return observation_from_wire(
            self._predict(history_to_wire(history), action_to_wire(action))
        )


def act(action: int, **data: int) -> ActionRecord:
    return ActionRecord(action, dict(data))


def synthetic_history(actions: Sequence[ActionRecord]) -> History:
    model = SyntheticModel()
    history = History(INITIAL)
    for action in actions:
        history = history.extend(action, model.predict(history, action))
    return history


DEFAULT_ACTIONS: tuple[ActionRecord, ...] = (
    act(1),
    act(2),
    act(3),
    act(6, x=2, y=3),
    act(1),
    act(1),
    act(2),
    act(6, x=0, y=0),
)
