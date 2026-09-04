"""Determinism of the G0 toy environment: same seed same trajectory, different seed different."""

from __future__ import annotations

import numpy as np

from arc_plasticity.environments.toy import ToyGridEnvironment


def _trajectory(seed: int, size: int = 8, steps: int = 64) -> list[tuple[int, int, int]]:
    env = ToyGridEnvironment(size, np.random.default_rng(seed))
    out: list[tuple[int, int, int]] = []
    for _ in range(steps):
        s = env.act(env.policy())
        out.append((s.action, s.row, s.col))
        if s.done:
            break
    return out


def test_same_seed_is_identical() -> None:
    assert _trajectory(12345) == _trajectory(12345)


def test_different_seed_differs() -> None:
    assert _trajectory(12345) != _trajectory(12346)


def test_start_and_goal_differ_and_stay_in_bounds() -> None:
    env = ToyGridEnvironment(5, np.random.default_rng(0))
    assert env.start != env.goal
    for cell in (env.start, env.goal):
        assert 0 <= cell[0] < 5 and 0 <= cell[1] < 5
