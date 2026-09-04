"""A trivial seeded grid environment and the smoke runner that drives it.

This exists for G0 only. It exercises the canonical entry point, the artifact contract, the
guards and the provenance layer with no network and no model, so a G0 failure can only be a
laboratory failure (preregistration/G0.yaml, smoke_experiment.reasoning). It is not an ARC
environment and makes no claim about anything scientific.

Determinism: all randomness comes from one ``numpy.random.default_rng(seed)``. The start and
goal cells depend on the seed, so different seeds give different trajectories, which is what
the contrast run in the determinism protocol checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from arc_plasticity.core.artifacts import RunArtifactWriter
from arc_plasticity.core.config import ExperimentConfig
from arc_plasticity.core.guards import Deadline
from arc_plasticity.core.runner import RunOutcome, register_runner

ENVIRONMENT_GENERATOR_VERSION = "toy-grid-1.0.0"
RUNNER_NAME = "smoke_toy_grid"

# Up, down, left, right.
_MOVES: tuple[tuple[int, int], ...] = ((-1, 0), (1, 0), (0, -1), (0, 1))


@dataclass(frozen=True)
class ToyStep:
    step: int
    action: int
    row: int
    col: int
    reward: float
    done: bool


class ToyGridEnvironment:
    """Agent walks on a ``size`` x ``size`` grid toward a goal cell. Reward 1.0 on arrival."""

    def __init__(self, size: int, rng: np.random.Generator) -> None:
        if size < 2:
            raise ValueError("size must be at least 2")
        self.size = size
        self._rng = rng
        cells = rng.choice(size * size, size=2, replace=False)
        self.start = (int(cells[0]) // size, int(cells[0]) % size)
        self.goal = (int(cells[1]) // size, int(cells[1]) % size)
        self.position = self.start
        self.visited: set[tuple[int, int]] = {self.start}
        self.steps = 0

    def act(self, action: int) -> ToyStep:
        dr, dc = _MOVES[action]
        r = min(max(self.position[0] + dr, 0), self.size - 1)
        c = min(max(self.position[1] + dc, 0), self.size - 1)
        self.position = (r, c)
        self.visited.add(self.position)
        self.steps += 1
        done = self.position == self.goal
        return ToyStep(self.steps, action, r, c, 1.0 if done else 0.0, done)

    def policy(self) -> int:
        """Greedy toward the goal with probability 0.7, otherwise a random move."""
        if self._rng.random() < 0.7:
            dr = self.goal[0] - self.position[0]
            dc = self.goal[1] - self.position[1]
            if abs(dr) >= abs(dc) and dr != 0:
                return 0 if dr < 0 else 1
            if dc != 0:
                return 2 if dc < 0 else 3
        return int(self._rng.integers(0, len(_MOVES)))


class SmokeToyGridRunner:
    name = RUNNER_NAME
    environment_generator_version = ENVIRONMENT_GENERATOR_VERSION

    def run(
        self, config: ExperimentConfig, writer: RunArtifactWriter, deadline: Deadline
    ) -> RunOutcome:
        size = int(config.runner_params.get("grid_size", 8))
        rng = np.random.default_rng(config.seed)
        env = ToyGridEnvironment(size, rng)
        budget = config.budgets.action_budget
        writer.log(
            f"toy grid size={size} seed={config.seed} start={env.start} goal={env.goal} "
            f"action_budget={budget}"
        )
        total_reward = 0.0
        solved = False
        for _ in range(budget):
            deadline.check()
            step = env.act(env.policy())
            total_reward += step.reward
            writer.append_transition(
                {
                    "step": step.step,
                    "action": step.action,
                    "row": step.row,
                    "col": step.col,
                    "reward": step.reward,
                    "done": step.done,
                }
            )
            if step.done:
                solved = True
                break
        writer.log(f"finished after {env.steps} steps solved={solved} reward={total_reward}")

        manhattan = abs(env.goal[0] - env.start[0]) + abs(env.goal[1] - env.start[1])
        metrics: list[dict[str, Any]] = [
            {"metric": "steps", "value": env.steps},
            {"metric": "solved", "value": int(solved)},
            {"metric": "total_reward", "value": total_reward},
            {"metric": "cells_visited", "value": len(env.visited)},
            {"metric": "optimal_steps", "value": manhattan},
        ]
        results: dict[str, Any] = {
            "environment_generator_version": ENVIRONMENT_GENERATOR_VERSION,
            "grid_size": size,
            "start": list(env.start),
            "goal": list(env.goal),
            "steps": env.steps,
            "solved": solved,
            "total_reward": total_reward,
            "cells_visited": len(env.visited),
            "optimal_steps": manhattan,
        }
        env_rows = [
            {
                "environment": f"toy_grid_{size}",
                "seed": config.seed,
                "steps": env.steps,
                "solved": int(solved),
                "reward": total_reward,
            }
        ]
        return RunOutcome(
            results=results,
            metrics=metrics,
            environment_results=env_rows,
            environment_columns=("environment", "seed", "steps", "solved", "reward"),
            model_calls=0,
        )


register_runner(RUNNER_NAME, SmokeToyGridRunner)
