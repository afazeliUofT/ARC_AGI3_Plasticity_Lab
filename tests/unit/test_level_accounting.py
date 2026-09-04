"""Level accounting and the per-game stop rule (G3.4).

The rule under test is preregistration/G3.yaml level_accounting_rule / per_game_stop_rule.
The multiplier and baselines are test inputs; nothing here asserts a pre-registered number
except by reading it from the pre-registration through the verifier's loader.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from arc_plasticity.evaluation import level_accounting as la
from arc_plasticity.evaluation import rhae
from arc_plasticity.evaluation.human_replays import attribute_levels

ROOT = Path(__file__).resolve().parents[2]
ENV_DIR = ROOT / "environment_files"
needs_toolkit_cache = pytest.mark.skipif(
    not (ENV_DIR / "ar25").exists(), reason="offline environment cache is absent"
)


def _load_verify_run() -> ModuleType:
    if "verify_run" in sys.modules:
        return sys.modules["verify_run"]
    spec = importlib.util.spec_from_file_location("verify_run", ROOT / "scripts" / "verify_run.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_run"] = mod
    spec.loader.exec_module(mod)
    return mod


def _play(acc: la.LevelAccounting, outcomes: list[tuple[int, int, str]]) -> list[str | None]:
    """Record (action, levels_completed_after, state) triples; return each stop evaluation."""
    reasons: list[str | None] = []
    for action, levels, state in outcomes:
        acc.record_action(action, levels, state)
        reasons.append(acc.evaluate_stop(state))
    return reasons


# --------------------------------------------------------------------------- the rule


def test_completion_indices_and_attribution_follow_the_rule() -> None:
    acc = la.LevelAccounting([3, 4, 5], 10)
    # actions 1..4: level 1 completes at action 4; level 2 at action 6; then a drop, ignored.
    _play(
        acc,
        [(1, 0, "NOT_FINISHED"), (2, 0, "NOT_FINISHED"), (1, 0, "NOT_FINISHED"),
         (1, 1, "NOT_FINISHED"), (3, 1, "NOT_FINISHED"), (1, 2, "NOT_FINISHED"),
         (0, 0, "NOT_FINISHED"), (1, 0, "NOT_FINISHED")],
    )  # fmt: skip
    assert acc.completion_indices == [4, 6]
    assert acc.levels_completed == 2 and acc.current_level == 3
    assert acc.actions_total == 8 and acc.resets_issued == 1
    records = acc.level_records()
    assert [r.actions_attributed for r in records] == [4, 2, 2]
    assert [r.completed for r in records] == [True, True, False]
    assert [r.completion_action_index for r in records] == [4, 6, None]
    assert [r.budget for r in records] == [30, 40, 50]
    assert acc.over_budget_levels() == []


def test_levels_after_the_first_uncompleted_one_carry_no_actions() -> None:
    acc = la.LevelAccounting([2, 2, 2, 2], 100)
    _play(acc, [(1, 1, "NOT_FINISHED"), (1, 1, "NOT_FINISHED"), (1, 1, "NOT_FINISHED")])
    assert [r.actions_attributed for r in acc.level_records()] == [1, 2, 0, 0]


def test_two_levels_completed_by_one_action_share_the_index() -> None:
    acc = la.LevelAccounting([1, 1, 1], 100)
    _play(acc, [(1, 0, "NOT_FINISHED"), (1, 2, "NOT_FINISHED")])
    assert acc.completion_indices == [2, 2]
    assert [r.actions_attributed for r in acc.level_records()] == [2, 0, 0]


def test_attribution_agrees_with_the_g2_replay_rule_on_random_logs() -> None:
    rng = np.random.default_rng(2026_09_04)
    for _ in range(200):
        n_levels = int(rng.integers(1, 6))
        length = int(rng.integers(0, 40))
        log: list[int] = []
        current = 0
        for _step in range(length):
            roll = rng.random()
            if roll < 0.15:
                current = 0  # full reset drop
            elif roll < 0.45:
                current = min(n_levels, current + int(rng.integers(1, 3)))
            log.append(current)
        acc = la.LevelAccounting([int(rng.integers(1, 9)) for _ in range(n_levels)], 10**6)
        for levels in log:
            acc.record_action(1, levels, "NOT_FINISHED")
        expected = attribute_levels(log)
        got = [r.actions_attributed for r in acc.level_records() if r.completed]
        assert got == expected, (log, got, expected)


# --------------------------------------------------------------------------- stop rule


def test_win_stops_first() -> None:
    acc = la.LevelAccounting([1], 1)
    reasons = _play(acc, [(1, 1, "WIN")])
    assert reasons == [la.STOP_WIN]
    acc.stop(la.STOP_WIN)
    assert acc.stopped and acc.to_dict()["stop_reason"] == "win"


def test_level_budget_exhausted_exactly_at_multiplier_times_baseline() -> None:
    acc = la.LevelAccounting([3, 5], 2)  # level-1 cap is 6 actions
    reasons = _play(acc, [(1, 0, "NOT_FINISHED")] * 6)
    assert reasons[:5] == [None] * 5
    assert reasons[5] == la.STOP_LEVEL_BUDGET_EXHAUSTED
    assert acc.actions_on_current_level == 6 and acc.remaining_on_current_level == 0
    with pytest.raises(la.LevelAccountingError, match="cap"):
        acc.record_action(1, 0, "NOT_FINISHED")
    acc.stop(la.STOP_LEVEL_BUDGET_EXHAUSTED)
    assert acc.over_budget_levels() == []
    assert acc.level_records()[0].actions_attributed == 6


def test_budget_is_per_level_and_resets_after_a_completion() -> None:
    acc = la.LevelAccounting([2, 1], 2)  # caps 4 then 2
    reasons = _play(acc, [(1, 0, "NOT_FINISHED")] * 3 + [(1, 1, "NOT_FINISHED")])
    assert reasons[-1] is None  # level 1 done at action 4 (== its cap), level 2 fresh
    assert acc.actions_on_current_level == 0
    reasons = _play(acc, [(0, 1, "GAME_OVER"), (1, 1, "NOT_FINISHED")])
    assert reasons == [None, la.STOP_LEVEL_BUDGET_EXHAUSTED]
    assert acc.resets_issued == 1


def test_game_over_is_not_a_stop() -> None:
    acc = la.LevelAccounting([9], 9)
    assert _play(acc, [(1, 0, "GAME_OVER")]) == [None]


def test_all_levels_completed_without_win_is_the_defensive_reason() -> None:
    acc = la.LevelAccounting([1], 9)
    assert _play(acc, [(1, 1, "NOT_FINISHED")]) == [la.STOP_ALL_LEVELS_COMPLETED]
    assert acc.current_level is None and acc.remaining_on_current_level is None


def test_recording_after_a_stop_or_an_unknown_reason_raises() -> None:
    acc = la.LevelAccounting([2], 9)
    acc.stop(la.STOP_WALLCLOCK)
    with pytest.raises(la.LevelAccountingError, match="after stop_reason"):
        acc.record_action(1, 0, "NOT_FINISHED")
    with pytest.raises(la.LevelAccountingError, match="already set"):
        acc.stop(la.STOP_STEP_FAILED)
    with pytest.raises(la.LevelAccountingError, match="unknown stop_reason"):
        la.LevelAccounting([2], 9).stop("gave_up")


def test_malformed_inputs_raise() -> None:
    with pytest.raises(la.LevelAccountingError):
        la.LevelAccounting([], 5)
    with pytest.raises(la.LevelAccountingError):
        la.LevelAccounting([0, 3], 5)
    with pytest.raises(la.LevelAccountingError):
        la.LevelAccounting([3], 0)
    acc = la.LevelAccounting([3], 5)
    with pytest.raises(la.LevelAccountingError):
        acc.record_action(1, 2, "NOT_FINISHED")  # more levels than the game has
    with pytest.raises(la.LevelAccountingError):
        acc.record_action(1, -1, "NOT_FINISHED")
    with pytest.raises(la.LevelAccountingError):
        acc.budget(2)


def test_stop_reason_sets_are_the_pre_registered_five_plus_the_defensive_one() -> None:
    assert set(la.STOP_REASONS) == {
        "win", "level_budget_exhausted", "model_budget_exhausted", "wallclock",
        "step_failed", "all_levels_completed",
    }  # fmt: skip
    assert set(la.ACCOUNTING_STOP_REASONS) <= set(la.STOP_REASONS)


# --------------------------------------------------------------------------- scoring and report


def test_rhae_numbers_come_from_the_toolkit_through_the_adapter() -> None:
    acc = la.LevelAccounting([4, 6, 8], 100, game_id="zz99-00000000")
    # level 1 in 4 actions (100), level 2 in 3 actions (400 -> 115 cap), level 3 unfinished
    _play(acc, [(1, 0, "NOT_FINISHED")] * 3 + [(1, 1, "NOT_FINISHED")] * 1)
    _play(acc, [(1, 1, "NOT_FINISHED")] * 2 + [(1, 2, "NOT_FINISHED")])
    _play(acc, [(1, 2, "NOT_FINISHED")] * 5)
    outcomes = acc.level_outcomes()
    assert [(o.agent_actions, o.completed) for o in outcomes] == [(4, True), (3, True), (5, False)]
    assert acc.rhae_level_scores() == [100.0, 115.0, 0.0]
    assert acc.rhae_environment_score() == rhae.environment_score(outcomes, game_id="zz99-00000000")
    assert acc.rhae_environment_score() == pytest.approx(min((100 + 230) / 6, 3 / 6 * 100))


def test_to_dict_has_the_contract_fields_and_reconstructs_from_a_log() -> None:
    acc = la.LevelAccounting([2, 3], 4, game_id="ar25-0c556536")
    log = [
        {"action": 1, "levels_completed": 0, "state": "NOT_FINISHED"},
        {"action": 6, "levels_completed": 1, "state": "NOT_FINISHED"},
        {"action": 0, "levels_completed": 1, "state": "NOT_FINISHED"},
    ]
    for rec in log:
        acc.record_action(int(rec["action"]), int(rec["levels_completed"]), str(rec["state"]))
    rebuilt = la.accounting_from_log([2, 3], 4, log, game_id="ar25-0c556536")
    assert rebuilt.to_dict() == acc.to_dict()
    d = acc.to_dict()
    assert d["stem"] == "ar25" and d["action_budget_total"] == 20
    assert d["completion_action_indices"] == [2] and d["resets_issued"] == 1
    assert {
        "level",
        "official_baseline_actions",
        "budget",
        "actions_attributed",
        "completed",
    } <= set(d["levels"][0])
    assert d["states_seen"] == {"NOT_FINISHED": 3}
    json.dumps(d)  # serialisable as written


# --------------------------------------------------------------------------- baselines from the cache


def test_load_official_baselines_refuses_a_version_mismatch(tmp_path: Path) -> None:
    meta_dir = tmp_path / "ab12" / "deadbeef"
    meta_dir.mkdir(parents=True)
    (meta_dir / "metadata.json").write_text(
        json.dumps({"game_id": "ab12-cafebabe", "baseline_actions": [3, 4]})
    )
    with pytest.raises(la.LevelAccountingError, match="carries game_id"):
        la.load_official_baselines(tmp_path, "ab12-deadbeef")
    with pytest.raises(la.LevelAccountingError, match="no cached metadata"):
        la.load_official_baselines(tmp_path, "ab12-00000000")
    with pytest.raises(la.LevelAccountingError, match="version suffix"):
        la.load_official_baselines(tmp_path, "ab12")
    (meta_dir / "metadata.json").write_text(
        json.dumps({"game_id": "ab12-deadbeef", "baseline_actions": [3, 4]})
    )
    assert la.load_official_baselines(tmp_path, "ab12-deadbeef") == [3, 4]


@needs_toolkit_cache
def test_official_baselines_and_multiplier_from_the_cache_and_the_pre_registration() -> None:
    vr = _load_verify_run()
    prereg = vr.load_preregistration("G3")[0]
    multiplier = int(prereg["thresholds"]["action_budget_multiplier"])
    manifest = json.loads((ROOT / "experiments" / "environment_cache_manifest.json").read_text())
    text = json.dumps(manifest)
    assert "ar25-0c556536" in text
    baselines = la.load_official_baselines(ENV_DIR, "ar25-0c556536")
    assert baselines == [32, 50, 75, 37, 89, 159, 233, 73]
    acc = la.LevelAccounting(baselines, multiplier, game_id="ar25-0c556536")
    assert acc.budget(1) == multiplier * 32
    assert acc.action_budget_total == multiplier * sum(baselines)
