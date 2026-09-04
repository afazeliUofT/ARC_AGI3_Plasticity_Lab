"""Level accounting and the per-game stop rule for REF game-runs.

Implements ``preregistration/G3.yaml`` ``reference_architecture`` ``level_accounting_rule``
and ``per_game_stop_rule`` (budget_enforcement: enforced by the runner, never by the model).

The rule, restated: the initial ``env.reset()`` that starts the game is not an action; every
action issued afterwards, RESET included, is counted; level ``l`` is completed at the first
action index ``c_l`` at which ``levels_completed`` reaches at least ``l``; the actions
attributed to level ``l`` are ``c_l - c_(l-1)`` with ``c_0 = 0``; a later full reset and
re-completion are ignored; a level never reached has no completion, and the first uncompleted
level's actions are the run's remaining actions after ``c_(l-1)`` (levels after it have none).
This is the same rule as ``human_replays.attribute_levels`` (G2) and the toolkit's scorecard;
``tests/unit/test_level_accounting.py`` binds the two implementations on random logs.

The per-level cap is ``action_budget_multiplier x official_baseline_actions[l]``; both numbers
come from the caller (the runner reads them from the pre-registration and the cached
``metadata.json``). This module defines no threshold.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arc_plasticity.environments.arc_interface import game_stem
from arc_plasticity.evaluation.rhae import LevelOutcome, environment_score, level_scores

STOP_WIN = "win"
STOP_LEVEL_BUDGET_EXHAUSTED = "level_budget_exhausted"
STOP_MODEL_BUDGET_EXHAUSTED = "model_budget_exhausted"
STOP_WALLCLOCK = "wallclock"
STOP_STEP_FAILED = "step_failed"
# Defensive: the toolkit reports WIN once every level is completed, so this reason should be
# unreachable; it exists so a run with no current level can never loop, and is recorded
# distinctly so the referee sees it if it ever fires.
STOP_ALL_LEVELS_COMPLETED = "all_levels_completed"

STOP_REASONS: tuple[str, ...] = (
    STOP_WIN,
    STOP_LEVEL_BUDGET_EXHAUSTED,
    STOP_MODEL_BUDGET_EXHAUSTED,
    STOP_WALLCLOCK,
    STOP_STEP_FAILED,
    STOP_ALL_LEVELS_COMPLETED,
)

# Stop reasons the accounting itself decides from (state, counts); the other three are the
# runner's (model budget, wall-clock, a failed step) and are passed to ``stop``.
ACCOUNTING_STOP_REASONS: tuple[str, ...] = (
    STOP_WIN,
    STOP_LEVEL_BUDGET_EXHAUSTED,
    STOP_ALL_LEVELS_COMPLETED,
)

RESET_ACTION_ID = 0
WIN_STATE = "WIN"

LEVEL_ACCOUNTING_RULE = (
    "initial reset not an action; every later action counted, RESET included; level l "
    "completed at the first action index c_l with levels_completed >= l; actions attributed "
    "to level l are c_l - c_(l-1), c_0 = 0; later full reset and re-completion ignored; a "
    "level never reached has no completion and the first uncompleted level takes the "
    "remaining actions"
)


class LevelAccountingError(ValueError):
    """Malformed inputs, or an action recorded past a stop or past the per-level cap."""


def _positive_int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LevelAccountingError(f"{what} must be a positive int, got {value!r}")
    return value


@dataclass(frozen=True)
class LevelRecord:
    """One level of one game-run in the ``results.json`` ``levels`` shape, plus the index."""

    level: int
    official_baseline_actions: int
    budget: int
    actions_attributed: int
    completed: bool
    completion_action_index: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "official_baseline_actions": self.official_baseline_actions,
            "budget": self.budget,
            "actions_attributed": self.actions_attributed,
            "completed": self.completed,
            "completion_action_index": self.completion_action_index,
        }

    def outcome(self) -> LevelOutcome:
        return LevelOutcome(
            human_baseline_actions=self.official_baseline_actions,
            agent_actions=self.actions_attributed,
            completed=self.completed,
        )


class LevelAccounting:
    """Incremental accounting for one game-run.

    Call :meth:`record_action` after every executed action with the ``levels_completed`` the
    toolkit returned, then :meth:`evaluate_stop` with the returned ``state``; when it names a
    reason, or when the runner has one of its own, call :meth:`stop`. Recording past a stop,
    or past the current level's cap, raises: ``per_level_actions_over_budget_max`` is 0 and
    the accounting refuses to produce a record that would violate it.
    """

    def __init__(
        self,
        baselines: Sequence[int],
        action_budget_multiplier: int,
        *,
        game_id: str | None = None,
    ) -> None:
        if len(baselines) == 0:
            raise LevelAccountingError("a game needs at least one level baseline")
        self.baselines: tuple[int, ...] = tuple(
            _positive_int(b, f"baseline_actions[{i}]") for i, b in enumerate(baselines)
        )
        self.multiplier = _positive_int(action_budget_multiplier, "action_budget_multiplier")
        self.game_id = game_id
        self.actions_total = 0
        self.resets_issued = 0
        self.completion_indices: list[int] = []
        self.stop_reason: str | None = None
        self._states_seen: dict[str, int] = {}

    # ------------------------------------------------------------------ derived views

    @property
    def win_levels(self) -> int:
        return len(self.baselines)

    @property
    def levels_completed(self) -> int:
        return len(self.completion_indices)

    @property
    def current_level(self) -> int | None:
        """1-based first uncompleted level, or ``None`` once every level is completed."""
        return None if self.levels_completed >= self.win_levels else self.levels_completed + 1

    def budget(self, level: int) -> int:
        if level < 1 or level > self.win_levels:
            raise LevelAccountingError(f"level {level} outside 1..{self.win_levels}")
        return self.multiplier * self.baselines[level - 1]

    @property
    def action_budget_total(self) -> int:
        """``multiplier x sum(baseline_actions)``, the manifest's action_budget."""
        return self.multiplier * sum(self.baselines)

    @property
    def actions_on_current_level(self) -> int:
        previous = self.completion_indices[-1] if self.completion_indices else 0
        return self.actions_total - previous

    @property
    def remaining_on_current_level(self) -> int | None:
        level = self.current_level
        if level is None:
            return None
        return self.budget(level) - self.actions_on_current_level

    @property
    def stopped(self) -> bool:
        return self.stop_reason is not None

    # ------------------------------------------------------------------ recording

    def record_action(self, action_id: int, levels_completed_after: int, state: str) -> None:
        """Count one executed action and its outcome.

        ``levels_completed_after`` and ``state`` are what the toolkit returned for it. A drop
        in ``levels_completed`` (a full reset) never removes a recorded completion.
        """
        if self.stopped:
            raise LevelAccountingError(
                f"action recorded after stop_reason {self.stop_reason!r} at action "
                f"{self.actions_total}"
            )
        remaining = self.remaining_on_current_level
        if remaining is not None and remaining <= 0:
            raise LevelAccountingError(
                f"level {self.current_level} cap {self.budget(self.current_level or 1)} already "
                f"reached at action {self.actions_total}; the runner must stop first"
            )
        if isinstance(levels_completed_after, bool) or not isinstance(levels_completed_after, int):
            raise LevelAccountingError(
                f"levels_completed must be an int, got {levels_completed_after!r}"
            )
        if levels_completed_after < 0 or levels_completed_after > self.win_levels:
            raise LevelAccountingError(
                f"levels_completed {levels_completed_after} outside 0..{self.win_levels}"
            )
        self.actions_total += 1
        if int(action_id) == RESET_ACTION_ID:
            self.resets_issued += 1
        while len(self.completion_indices) < levels_completed_after:
            self.completion_indices.append(self.actions_total)
        self._states_seen[state] = self._states_seen.get(state, 0) + 1

    def evaluate_stop(self, state: str) -> str | None:
        """The accounting's own stop reason after the last recorded action, if any.

        (a) ``WIN`` wins; then (b) the current level's attributed actions reaching its cap;
        then the defensive all-levels-completed case. ``None`` means keep playing.
        """
        if state == WIN_STATE:
            return STOP_WIN
        level = self.current_level
        if level is None:
            return STOP_ALL_LEVELS_COMPLETED
        if self.actions_on_current_level >= self.budget(level):
            return STOP_LEVEL_BUDGET_EXHAUSTED
        return None

    def stop(self, reason: str) -> None:
        if reason not in STOP_REASONS:
            raise LevelAccountingError(f"unknown stop_reason {reason!r}; expected {STOP_REASONS}")
        if self.stopped:
            raise LevelAccountingError(
                f"stop_reason already set to {self.stop_reason!r}, refusing {reason!r}"
            )
        self.stop_reason = reason

    # ------------------------------------------------------------------ reports

    def level_records(self) -> list[LevelRecord]:
        records: list[LevelRecord] = []
        previous = 0
        for index, baseline in enumerate(self.baselines):
            level = index + 1
            if index < len(self.completion_indices):
                c_l = self.completion_indices[index]
                attributed, completed, completion = c_l - previous, True, c_l
                previous = c_l
            elif index == len(self.completion_indices):
                attributed, completed, completion = self.actions_total - previous, False, None
            else:
                attributed, completed, completion = 0, False, None
            records.append(
                LevelRecord(
                    level=level,
                    official_baseline_actions=baseline,
                    budget=self.multiplier * baseline,
                    actions_attributed=attributed,
                    completed=completed,
                    completion_action_index=completion,
                )
            )
        return records

    def over_budget_levels(self) -> list[int]:
        """Levels whose attributed actions exceed their cap (must be empty; see thresholds)."""
        return [r.level for r in self.level_records() if r.actions_attributed > r.budget]

    def level_outcomes(self) -> list[LevelOutcome]:
        return [record.outcome() for record in self.level_records()]

    def rhae_environment_score(self) -> float:
        """Percent, from the toolkit calculator through the G2 adapter (never reimplemented)."""
        return environment_score(self.level_outcomes(), game_id=self.game_id)

    def rhae_level_scores(self) -> list[float]:
        return level_scores(self.level_outcomes(), game_id=self.game_id)

    def to_dict(self) -> dict[str, Any]:
        """The ``level_accounting.json`` artifact: every count the verifier recomputes."""
        return {
            "game_id": self.game_id,
            "stem": game_stem(self.game_id) if self.game_id else None,
            "level_accounting_rule": LEVEL_ACCOUNTING_RULE,
            "action_budget_multiplier": self.multiplier,
            "official_baseline_actions": list(self.baselines),
            "action_budget_total": self.action_budget_total,
            "win_levels": self.win_levels,
            "levels_completed": self.levels_completed,
            "completion_action_indices": list(self.completion_indices),
            "actions_total": self.actions_total,
            "resets_issued": self.resets_issued,
            "states_seen": dict(sorted(self._states_seen.items())),
            "stop_reason": self.stop_reason,
            "over_budget_levels": self.over_budget_levels(),
            "levels": [record.to_dict() for record in self.level_records()],
            "rhae_environment_score": self.rhae_environment_score(),
            "rhae_level_scores": self.rhae_level_scores(),
        }


def load_official_baselines(environments_dir: Path, game_id: str) -> list[int]:
    """``baseline_actions`` from the cached ``metadata.json`` of the exact ``game_id``.

    The cache lays a game out as ``<environments_dir>/<stem>/<version>/metadata.json`` and
    the file's own ``game_id`` must equal the requested one, so a version mismatch is an
    error, never a silent substitution (carry_forward_from_g2_verdict item 1 and 3).
    """
    stem = game_stem(game_id)
    if "-" not in game_id:
        raise LevelAccountingError(f"game_id {game_id!r} lacks its version suffix")
    version = game_id.split("-", 1)[1]
    path = Path(environments_dir) / stem / version / "metadata.json"
    if not path.exists():
        raise LevelAccountingError(f"no cached metadata.json for {game_id} at {path}")
    meta = json.loads(path.read_text(encoding="utf-8"))
    if meta.get("game_id") != game_id:
        raise LevelAccountingError(
            f"{path} carries game_id {meta.get('game_id')!r}, expected {game_id!r}"
        )
    raw = meta.get("baseline_actions")
    if not isinstance(raw, list) or not raw:
        raise LevelAccountingError(f"{path} has no baseline_actions list")
    return [_positive_int(b, f"{game_id} baseline_actions[{i}]") for i, b in enumerate(raw)]


def accounting_from_log(
    baselines: Sequence[int],
    action_budget_multiplier: int,
    log: Sequence[Mapping[str, Any]],
    *,
    game_id: str | None = None,
) -> LevelAccounting:
    """Rebuild the accounting from a step log of ``{action, levels_completed, state}`` records.

    This is what the verifier does from ``transitions.jsonl``; the runner's live object and
    this reconstruction must agree on every count.
    """
    accounting = LevelAccounting(baselines, action_budget_multiplier, game_id=game_id)
    for record in log:
        accounting.record_action(
            int(record["action"]), int(record["levels_completed"]), str(record["state"])
        )
    return accounting


__all__ = [
    "ACCOUNTING_STOP_REASONS",
    "LEVEL_ACCOUNTING_RULE",
    "RESET_ACTION_ID",
    "STOP_ALL_LEVELS_COMPLETED",
    "STOP_LEVEL_BUDGET_EXHAUSTED",
    "STOP_MODEL_BUDGET_EXHAUSTED",
    "STOP_REASONS",
    "STOP_STEP_FAILED",
    "STOP_WALLCLOCK",
    "STOP_WIN",
    "WIN_STATE",
    "LevelAccounting",
    "LevelAccountingError",
    "LevelRecord",
    "accounting_from_log",
    "load_official_baselines",
]
