"""Unit tests for the E100 runner's policy, parameter validation and game-list resolution.

The policy is what makes the action sequence a pure function of (seed, game). These tests
pin that property without touching the toolkit; the integration test covers the real cache.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from arc_plasticity.core.config import ExperimentConfig
from arc_plasticity.environments import arc_random_walk as rw

ROOT = Path(__file__).resolve().parents[2]


def _sequence(seed: int, game_index: int, available: tuple[int, ...], n: int = 200) -> list[tuple[int, dict[str, int]]]:
    policy = rw.UniformRandomPolicy(rw.game_rng(seed, game_index))
    out: list[tuple[int, dict[str, int]]] = []
    for _ in range(n):
        rec = policy.choose(available)
        assert rec is not None
        out.append((rec.action, dict(rec.data)))
    return out


def test_same_seed_same_game_gives_identical_actions() -> None:
    a = _sequence(12345, 3, (1, 2, 3, 4, 6))
    b = _sequence(12345, 3, (1, 2, 3, 4, 6))
    assert a == b


def test_contrast_seed_and_other_game_index_differ() -> None:
    base = _sequence(12345, 3, (1, 2, 3, 4, 6))
    assert _sequence(12346, 3, (1, 2, 3, 4, 6)) != base
    assert _sequence(12345, 4, (1, 2, 3, 4, 6)) != base


def test_policy_draws_only_from_available_actions_and_excludes_reset() -> None:
    seq = _sequence(7, 0, (0, 2, 5), n=500)
    assert {a for a, _ in seq} == {2, 5}


def test_policy_uses_reset_only_when_nothing_else_is_offered() -> None:
    seq = _sequence(7, 0, (0,), n=20)
    assert {a for a, _ in seq} == {0}


def test_policy_returns_none_when_no_actions_are_available() -> None:
    policy = rw.UniformRandomPolicy(rw.game_rng(1, 0))
    assert policy.choose(()) is None


def test_click_gets_x_y_in_grid() -> None:
    seq = _sequence(99, 1, (6,), n=2000)
    xs = {d["x"] for _, d in seq}
    ys = {d["y"] for _, d in seq}
    assert all(0 <= v < rw.GRID_SIZE for v in xs | ys)
    assert min(xs) == 0 and max(xs) == rw.GRID_SIZE - 1
    assert min(ys) == 0 and max(ys) == rw.GRID_SIZE - 1
    assert all(set(d) == {"x", "y"} for _, d in seq)


def test_non_click_actions_carry_no_data() -> None:
    seq = _sequence(5, 2, (1, 2, 3, 4), n=50)
    assert all(d == {} for _, d in seq)


def test_policy_is_uniform_over_candidates() -> None:
    seq = _sequence(2024, 0, (1, 2, 3, 4), n=20000)
    counts = np.bincount([a for a, _ in seq], minlength=5)[1:5]
    assert counts.min() > 0.2 * len(seq) and counts.max() < 0.3 * len(seq)


# ------------------------------------------------------------------ params


def _config(**runner_params: Any) -> ExperimentConfig:
    base: dict[str, Any] = {
        "environments_dir": "environment_files",
        "action_budget_per_game": 10,
        "games": "all",
        "extra_artifacts": ["throughput.json"],
    }
    base.update(runner_params)
    return ExperimentConfig.model_validate(
        {
            "schema_version": 1,
            "experiment_id": "E100_arc_interface",
            "runner": rw.RUNNER_NAME,
            "seed": 1,
            "wallclock_limit_seconds": 60,
            "network_calls_allowed": 0,
            "model_calls_allowed": 0,
            "budgets": {
                "action_budget": 250,
                "simulation_budget": 0,
                "token_budget": 0,
                "persistent_state_size_cap_bytes": 0,
            },
            "runner_params": base,
        }
    )


def test_params_resolve_relative_environments_dir_against_root(tmp_path: Path) -> None:
    p = rw.RandomWalkParams.from_config(_config(), root=tmp_path)
    assert p.environments_dir == tmp_path / "environment_files"
    assert p.games is None
    assert p.action_budget_per_game == 10
    assert p.extra_artifacts == ("throughput.json",)


def test_params_accept_explicit_stem_list() -> None:
    p = rw.RandomWalkParams.from_config(_config(games=["ls20", "ft09"]))
    assert p.games == ("ls20", "ft09")


@pytest.mark.parametrize(
    "bad",
    [
        {"environments_dir": ""},
        {"action_budget_per_game": 0},
        {"action_budget_per_game": True},
        {"games": []},
        {"games": "some"},
        {"extra_artifacts": []},
        {"extra_artifacts": "throughput.json"},
    ],
)
def test_params_reject_malformed(bad: dict[str, Any]) -> None:
    with pytest.raises(rw.RunnerConfigError):
        rw.RandomWalkParams.from_config(_config(**bad))


# ------------------------------------------------------------------ game list


class _Info:
    def __init__(self, game_id: str) -> None:
        self.game_id = game_id


class _FakeArcade:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def get_environments(self) -> list[_Info]:
        return [_Info(i) for i in self._ids]


def test_resolve_game_ids_keeps_requested_order() -> None:
    arcade = _FakeArcade(["ft09-aaaa", "ls20-bbbb", "ar25-cccc"])
    assert rw.resolve_game_ids(arcade, ["ls20", "ar25"]) == ["ls20-bbbb", "ar25-cccc"]  # type: ignore[arg-type]


def test_resolve_game_ids_fails_on_any_missing_stem() -> None:
    arcade = _FakeArcade(["ls20-bbbb"])
    with pytest.raises(rw.GameListError, match="zz99"):
        rw.resolve_game_ids(arcade, ["ls20", "zz99"])  # type: ignore[arg-type]


def test_runner_is_registered_under_the_preregistered_name() -> None:
    from arc_plasticity.core.runner import get_runner

    runner = get_runner("arc_random_walk")
    assert runner.name == rw.RUNNER_NAME
    assert runner.environment_generator_version == rw.ENVIRONMENT_GENERATOR_VERSION
