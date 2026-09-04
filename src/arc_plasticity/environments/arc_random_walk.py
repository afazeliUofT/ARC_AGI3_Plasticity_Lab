"""E100: a seeded uniform-random walk over every cached ARC-AGI-3 game (G1's experiment).

Pre-registered in ``preregistration/G1.yaml`` ``experiment``. The runner exists to show that
the offline interface loads all 25 public games, steps them at the documented rate, records
every action, and replays identically from its own log. The policy is deliberately trivial:
G1 tests the interface, not intelligence.

Policy (``experiment.policy``): at each step choose uniformly among the previous response's
``available_actions``, excluding RESET whenever any other action is available; ACTION6 gets
``x`` and ``y`` drawn independently and uniformly from ``0..63``. One ``numpy`` Generator per
game, seeded from ``[experiment seed, game index]``, so the action sequence is a pure
function of ``(seed, game)``.

Stop rule (``experiment.per_game_stop_rule``): the first WIN or GAME_OVER response, the
per-game action budget, or a ``None`` from ``step()`` (recorded as ``step_failed``, never
skipped). ``reset()`` is issued once per game and is not an action. A response listing no
available actions also stops the game (recorded as ``stop_reason`` ``no_available_actions``);
the pre-registration does not name this case and stopping is the only choice that keeps the
transition log equal to what was stepped.

What it writes, in the layout ``scripts/verify_run.py`` consumes: ``results.json["results"]``
with ``operation_mode``, ``network_guard`` and one ``games[]`` record per game;
``transitions.jsonl`` with one record per action; ``metrics.csv`` with counts only (no
timing, so the G0 exclusion list is reused unchanged); ``environment_results.csv`` one row per
game; and ``throughput.json`` (an extra artifact declared in the config) with the per-step
``perf_counter`` timing around ``step()``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from arc_agi import Arcade

from arc_plasticity.core.artifacts import RunArtifactWriter
from arc_plasticity.core.config import ExperimentConfig
from arc_plasticity.core.guards import Deadline, NetworkGuard
from arc_plasticity.core.runner import RunOutcome, register_runner
from arc_plasticity.environments import arc_interface as ai

RUNNER_NAME = "arc_random_walk"
ENVIRONMENT_GENERATOR_VERSION = "arc-agi-offline-cache-1.0.0"
OPERATION_MODE = "OFFLINE"
THROUGHPUT_FILE = "throughput.json"

RESET_ACTION = 0
CLICK_ACTION = 6
GRID_SIZE = 64

PROJECT_ROOT = Path(__file__).resolve().parents[3]

ENVIRONMENT_COLUMNS: tuple[str, ...] = (
    "environment",
    "steps",
    "final_state",
    "levels_completed",
    "terminal",
)


class RunnerConfigError(ValueError):
    """``runner_params`` are missing or malformed for this runner."""


class GameListError(RuntimeError):
    """A requested game stem is not in the offline cache (``Arcade.make`` would return ``None``)."""


@dataclass(frozen=True)
class RandomWalkParams:
    environments_dir: Path
    action_budget_per_game: int
    games: tuple[str, ...] | None  # None means every public stem
    extra_artifacts: tuple[str, ...]

    @classmethod
    def from_config(cls, config: ExperimentConfig, root: Path = PROJECT_ROOT) -> RandomWalkParams:
        params = config.runner_params
        env_rel = params.get("environments_dir")
        if not isinstance(env_rel, str) or not env_rel:
            raise RunnerConfigError("runner_params.environments_dir must be a non-empty string")
        budget = params.get("action_budget_per_game")
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
            raise RunnerConfigError("runner_params.action_budget_per_game must be a positive int")
        games_raw = params.get("games", "all")
        games: tuple[str, ...] | None
        if games_raw == "all":
            games = None
        elif (
            isinstance(games_raw, list) and games_raw and all(isinstance(g, str) for g in games_raw)
        ):
            games = tuple(games_raw)
        else:
            raise RunnerConfigError(
                "runner_params.games must be 'all' or a non-empty list of stems"
            )
        extras_raw = params.get("extra_artifacts", [])
        if not isinstance(extras_raw, list) or not all(isinstance(e, str) for e in extras_raw):
            raise RunnerConfigError("runner_params.extra_artifacts must be a list of file names")
        if THROUGHPUT_FILE not in extras_raw:
            raise RunnerConfigError(
                f"runner_params.extra_artifacts must list {THROUGHPUT_FILE!r}; timing lives there"
            )
        env_dir = Path(env_rel)
        if not env_dir.is_absolute():
            env_dir = root / env_dir
        return cls(env_dir, budget, games, tuple(extras_raw))


class UniformRandomPolicy:
    """The pre-registered policy. All randomness comes from the Generator handed in."""

    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng

    def choose(self, available_actions: tuple[int, ...]) -> ai.ActionRecord | None:
        """Uniform over ``available_actions`` minus RESET when anything else is offered.

        Returns ``None`` when nothing can be chosen.
        """
        candidates = sorted({int(a) for a in available_actions})
        non_reset = [a for a in candidates if a != RESET_ACTION]
        if non_reset:
            candidates = non_reset
        if not candidates:
            return None
        action = candidates[int(self._rng.integers(0, len(candidates)))]
        if action == CLICK_ACTION:
            x = int(self._rng.integers(0, GRID_SIZE))
            y = int(self._rng.integers(0, GRID_SIZE))
            return ai.ActionRecord(action, {"x": x, "y": y})
        return ai.ActionRecord(action)


def game_rng(seed: int, game_index: int) -> np.random.Generator:
    """One Generator per game, seeded from the experiment seed and the game's index."""
    return np.random.default_rng([int(seed), int(game_index)])


@dataclass
class GamePlay:
    """Everything one game produced. ``results.json`` and the CSV row are views of this."""

    game_index: int
    game_id: str
    seed: int
    steps_taken: int = 0
    final_state: str = "UNAVAILABLE"
    levels_completed: int = 0
    win_levels: int = 0
    terminal: bool = False
    final_frame_sha256: str = ""
    step_failed: bool = False
    stop_reason: str = "unknown"
    step_seconds: float = 0.0
    reset_seconds: float = 0.0
    step_times: list[float] = field(default_factory=list, repr=False)

    def record(self) -> dict[str, Any]:
        return {
            "game_index": self.game_index,
            "game_id": self.game_id,
            "seed": self.seed,
            "steps_taken": self.steps_taken,
            "final_state": self.final_state,
            "levels_completed": self.levels_completed,
            "win_levels": self.win_levels,
            "terminal": self.terminal,
            "final_frame_sha256": self.final_frame_sha256,
            "step_failed": self.step_failed,
            "stop_reason": self.stop_reason,
        }

    def environment_row(self) -> dict[str, Any]:
        return {
            "environment": self.game_id,
            "steps": self.steps_taken,
            "final_state": self.final_state,
            "levels_completed": self.levels_completed,
            "terminal": int(self.terminal),
        }

    def throughput(self) -> dict[str, Any]:
        fps = (self.steps_taken / self.step_seconds) if self.step_seconds > 0 else None
        return {
            "game_id": self.game_id,
            "steps": self.steps_taken,
            "step_seconds": self.step_seconds,
            "fps": fps,
            "reset_seconds": self.reset_seconds,
            "step_seconds_max": max(self.step_times) if self.step_times else None,
        }


def resolve_game_ids(arcade: Arcade, stems: list[str]) -> list[str]:
    """Full game ids for the requested stems, in the requested order. Fails on any miss."""
    by_stem: dict[str, str] = {}
    for info in arcade.get_environments():
        by_stem.setdefault(ai.game_stem(str(info.game_id)), str(info.game_id))
    missing = [s for s in stems if s not in by_stem]
    if missing:
        raise GameListError(f"stems not in the offline cache: {missing}")
    return [by_stem[s] for s in stems]


def play_game(
    arcade: Arcade,
    game_index: int,
    game_id: str,
    seed: int,
    budget: int,
    writer: RunArtifactWriter,
    deadline: Deadline,
) -> GamePlay:
    """Reset once, then walk until terminal, budget, a ``None`` step, or no actions."""
    play = GamePlay(game_index=game_index, game_id=game_id, seed=seed)
    policy = UniformRandomPolicy(game_rng(seed, game_index))
    env = ai.make_environment(arcade, game_id, seed)

    t0 = time.perf_counter()
    reset = env.reset()
    play.reset_seconds = time.perf_counter() - t0
    if reset is None:
        play.step_failed = True
        play.stop_reason = "reset_failed"
        return play
    current = ai.summarize_response(reset)
    play.final_frame_sha256 = current.digest()

    play.stop_reason = "budget"
    for step_index in range(1, budget + 1):
        deadline.check()
        if current.terminal:
            play.stop_reason = "terminal"
            break
        record = policy.choose(current.available_actions)
        if record is None:
            play.stop_reason = "no_available_actions"
            break
        t0 = time.perf_counter()
        nxt = ai.step_environment(env, record)
        dt = time.perf_counter() - t0
        play.step_times.append(dt)
        play.step_seconds += dt
        play.steps_taken = step_index
        if nxt is None:
            play.step_failed = True
            play.stop_reason = "step_failed"
            writer.append_transition(
                {
                    "game_index": game_index,
                    "game_id": game_id,
                    "step_index": step_index,
                    "action": record.action,
                    "data": dict(record.data),
                    "frame_sha256": None,
                }
            )
            break
        current = nxt
        play.final_frame_sha256 = current.digest()
        writer.append_transition(
            {
                "game_index": game_index,
                "game_id": game_id,
                "step_index": step_index,
                "action": record.action,
                "data": dict(record.data),
                "frame_sha256": play.final_frame_sha256,
            }
        )
    else:
        if current.terminal:
            play.stop_reason = "terminal"

    play.final_state = current.state
    play.levels_completed = current.levels_completed
    play.win_levels = current.win_levels
    play.terminal = current.terminal
    return play


class ArcRandomWalkRunner:
    name = RUNNER_NAME
    environment_generator_version = ENVIRONMENT_GENERATOR_VERSION

    def run(
        self, config: ExperimentConfig, writer: RunArtifactWriter, deadline: Deadline
    ) -> RunOutcome:
        params = RandomWalkParams.from_config(config)
        stems = (
            list(params.games) if params.games is not None else ai.public_game_stems(PROJECT_ROOT)
        )
        if not stems:
            raise GameListError("no game stems: docs/EVIDENCE_ARC.md section 1.1 yielded none")

        arcade = ai.open_offline_arcade(params.environments_dir)
        game_ids = resolve_game_ids(arcade, stems)
        writer.log(
            f"arc_random_walk seed={config.seed} games={len(game_ids)} "
            f"action_budget_per_game={params.action_budget_per_game} "
            f"environments_dir={params.environments_dir} operation_mode={OPERATION_MODE}"
        )

        plays: list[GamePlay] = []
        for index, game_id in enumerate(game_ids):
            deadline.check()
            play = play_game(
                arcade, index, game_id, config.seed, params.action_budget_per_game, writer, deadline
            )
            plays.append(play)
            writer.log(
                f"game {index} {game_id}: steps={play.steps_taken} final_state={play.final_state} "
                f"levels={play.levels_completed}/{play.win_levels} stop={play.stop_reason} "
                f"step_seconds={play.step_seconds:.4f}"
            )

        total_steps = sum(p.steps_taken for p in plays)
        total_seconds = sum(p.step_seconds for p in plays)
        aggregate_fps = (total_steps / total_seconds) if total_seconds > 0 else None
        throughput: dict[str, Any] = {
            "aggregate": {
                "steps": total_steps,
                "step_seconds": total_seconds,
                "fps": aggregate_fps,
                "definition": "one step() call is one frame; fps = steps / summed step() "
                "perf_counter seconds; reset() and digest time excluded",
            },
            "per_game": [p.throughput() for p in plays],
        }
        writer.write_extra_json(THROUGHPUT_FILE, throughput)

        terminal = sum(1 for p in plays if p.terminal)
        failures = sum(1 for p in plays if p.step_failed)
        metrics: list[dict[str, Any]] = [
            {"metric": "games_attempted", "value": len(plays)},
            {"metric": "terminal_games", "value": terminal},
            {"metric": "step_failures", "value": failures},
            {"metric": "total_steps", "value": total_steps},
            {"metric": "levels_completed_total", "value": sum(p.levels_completed for p in plays)},
        ]
        results: dict[str, Any] = {
            "environment_generator_version": ENVIRONMENT_GENERATOR_VERSION,
            "operation_mode": OPERATION_MODE,
            "network_guard": NetworkGuard.__name__,
            "action_budget_per_game": params.action_budget_per_game,
            "games": [p.record() for p in plays],
        }
        writer.log(
            f"finished games={len(plays)} terminal={terminal} step_failures={failures} "
            f"total_steps={total_steps} fps={aggregate_fps}"
        )
        return RunOutcome(
            results=results,
            metrics=metrics,
            environment_results=[p.environment_row() for p in plays],
            environment_columns=ENVIRONMENT_COLUMNS,
            model_calls=0,
        )


register_runner(RUNNER_NAME, ArcRandomWalkRunner)
