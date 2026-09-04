"""The correct-by-construction world model: the offline toolkit itself.

:class:`TrueModel` answers ``predict(history, action)`` by replaying the history's actions
through a fresh offline environment and stepping the action. It keeps the environment
between calls and only steps the difference when the new history extends the actions already
applied, which is what a backtest does; any other history rebuilds from ``reset``. Either
way the answer is the toolkit's own, so the model is exact by construction and is the
E310 control (``backtest_correct_model_acceptance_min``).

:func:`record_history` builds a full-frame :class:`History` from an action log, and
:func:`read_action_log` reads a G1-format ``transitions.jsonl`` for one game.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from arc_agi.wrapper import EnvironmentWrapper

from arc_plasticity.environments.arc_interface import (
    ActionRecord,
    make_environment,
    open_offline_arcade,
    step_environment,
    summarize_response,
)
from arc_plasticity.hypotheses.interface import (
    History,
    Observation,
    WorldModelError,
)


class TrueModel:
    """``predict`` by replaying through the real offline environment for ``game_id``."""

    def __init__(self, environments_dir: Path, game_id: str, seed: int) -> None:
        self.environments_dir = Path(environments_dir)
        self.game_id = game_id
        self.seed = int(seed)
        self._env: EnvironmentWrapper | None = None
        self._applied: list[ActionRecord] = []
        self.rebuilds = 0
        self.steps = 0

    def _rebuild(self) -> Observation:
        arcade = open_offline_arcade(self.environments_dir)
        env = make_environment(arcade, self.game_id, self.seed)
        reset = env.reset()
        if reset is None:
            raise WorldModelError(f"{self.game_id}: reset() returned None")
        self._env = env
        self._applied = []
        self.rebuilds += 1
        return Observation.from_summary(summarize_response(reset))

    def _step(self, action: ActionRecord) -> Observation:
        assert self._env is not None
        summary = step_environment(self._env, action)
        if summary is None:
            raise WorldModelError(
                f"{self.game_id}: step({action.action}, {dict(action.data)}) returned None"
            )
        self._applied.append(action)
        self.steps += 1
        return Observation.from_summary(summary)

    def initial_observation(self) -> Observation:
        return self._rebuild()

    def predict(self, history: History, action: ActionRecord) -> Observation:
        actions = list(history.actions())
        n = len(self._applied)
        if self._env is None or n > len(actions) or actions[:n] != self._applied:
            self._rebuild()
            n = 0
        for pending in actions[n:]:
            self._step(pending)
        return self._step(action)


def record_history(
    environments_dir: Path, game_id: str, seed: int, actions: Sequence[ActionRecord]
) -> History:
    """Reset a fresh offline environment and apply ``actions`` in order, keeping every frame."""
    model = TrueModel(environments_dir, game_id, seed)
    history = History(model.initial_observation())
    for action in actions:
        history = history.extend(action, model._step(action))
    return history


def read_action_log(transitions_jsonl: Path, game_id: str) -> list[ActionRecord]:
    """The actions recorded for ``game_id`` in a G1-format transitions.jsonl, in step order."""
    records: list[tuple[int, ActionRecord]] = []
    with transitions_jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("game_id") != game_id:
                continue
            records.append((int(row["step_index"]), ActionRecord.from_mapping(row)))
    records.sort(key=lambda item: item[0])
    return [record for _, record in records]


def game_ids_in_action_log(transitions_jsonl: Path) -> list[str]:
    """Every game id in the log, in first-appearance order."""
    seen: dict[str, None] = {}
    with transitions_jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                seen.setdefault(str(json.loads(line)["game_id"]), None)
    return list(seen)


__all__ = ["TrueModel", "game_ids_in_action_log", "read_action_log", "record_history"]
