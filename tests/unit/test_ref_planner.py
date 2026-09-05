"""The REF planner and the exploration fallback (G3.4), on the synthetic world and on the
true offline simulator with zero model calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arc_plasticity.core.guards import Deadline
from arc_plasticity.environments.arc_interface import ActionRecord
from arc_plasticity.evaluation import level_accounting as la
from arc_plasticity.hypotheses.interface import History, Observation, WorldModelError
from arc_plasticity.planning import ref_planner as rp
from tests.g3_synthetic import INITIAL, SyntheticModel, act, synthetic_history

ROOT = Path(__file__).resolve().parents[2]
ENV_DIR = ROOT / "environment_files"
needs_toolkit_cache = pytest.mark.skipif(
    not (ENV_DIR / "ar25").exists(), reason="offline environment cache is absent"
)
LIMITS = rp.PlannerLimits(max_depth=4, max_nodes=500)


def _plan(history: History, budget: rp.SimulationBudget, limits: rp.PlannerLimits = LIMITS,
          model: SyntheticModel | None = None, deadline: Deadline | None = None) -> rp.Plan:  # fmt: skip
    return rp.plan_to_next_level(
        model or SyntheticModel(),
        history,
        hypothesis_id="h1",
        certification_history_length=len(history),
        budget=budget,
        limits=limits,
        deadline=deadline,
    )


# --------------------------------------------------------------------------- pieces


def test_simulation_budget_charges_only_what_fits() -> None:
    budget = rp.SimulationBudget(3)
    assert budget.try_consume() and budget.try_consume(2)
    assert budget.exhausted and not budget.try_consume() and budget.used == 3
    assert budget.to_dict() == {"max_steps": 3, "used": 3}
    with pytest.raises(rp.PlannerError):
        rp.SimulationBudget(0)
    with pytest.raises(rp.PlannerError):
        budget.try_consume(0)


def test_candidate_actions_fan_out_clicks_in_order() -> None:
    out = rp.candidate_actions((1, 6, 0), ((3, 4), (0, 0)))
    assert out == [
        ActionRecord(1),
        ActionRecord(6, {"x": 3, "y": 4}),
        ActionRecord(6, {"x": 0, "y": 0}),
        ActionRecord(0),
    ]
    assert rp.candidate_actions((6,), ()) == []


def test_observation_digest_ignores_available_actions_only() -> None:
    a = INITIAL
    b = Observation(a.frame, a.state, a.levels_completed, (1,))
    c = Observation(a.frame, "GAME_OVER", a.levels_completed, a.available_actions)
    d = Observation(a.frame, a.state, 1, a.available_actions)
    assert rp.observation_digest(a) == rp.observation_digest(b)
    assert len({rp.observation_digest(x) for x in (a, c, d)}) == 3


def test_plan_record_validation() -> None:
    with pytest.raises(rp.PlannerError):
        rp.Plan((), "h", 0, 0, 1, 0, 0, "found")
    with pytest.raises(rp.PlannerError):
        rp.Plan((act(1),), "h", 0, 0, 1, 0, 0, "not_found")
    with pytest.raises(rp.PlannerError):
        rp.Plan((), "h", 0, 0, 1, 0, 0, "maybe")
    with pytest.raises(rp.PlannerError):
        rp.PlannerLimits(max_depth=0, max_nodes=1)


# --------------------------------------------------------------------------- planner (synthetic)


def test_bfs_finds_the_one_step_completion() -> None:
    history = synthetic_history([act(1)] * 15)
    budget = rp.SimulationBudget(1000)
    plan = _plan(history, budget)
    assert plan.outcome == rp.PLAN_FOUND and plan.actions == (act(1),)
    assert plan.target_levels_completed == 1 and plan.planned_from_history_length == 15
    assert plan.steps_simulated == budget.used == 1  # action 1 is tried first
    assert plan.to_dict()["actions"] == [{"action": 1, "data": {}}]


def test_bfs_finds_the_shortest_multi_step_plan_and_dedupes_no_ops() -> None:
    history = synthetic_history([act(1)] * 13)
    budget = rp.SimulationBudget(10_000)
    plan = _plan(history, budget, rp.PlannerLimits(max_depth=3, max_nodes=10_000))
    assert plan.outcome == rp.PLAN_FOUND
    assert plan.actions == (act(1), act(1), act(1))
    # 4 branching actions (1,2,3,4; no click points) with action 3 a no-op that is never
    # re-expanded and action 4 a GAME_OVER state expanding only RESET.
    assert plan.nodes_expanded < 40 and plan.steps_simulated == budget.used


def test_bfs_reports_simulation_budget_exhaustion_without_overspending() -> None:
    history = synthetic_history([act(1)] * 10)
    budget = rp.SimulationBudget(7)
    plan = _plan(history, budget)
    assert plan.outcome == rp.PLAN_SIMULATION_BUDGET_EXHAUSTED and plan.actions == ()
    assert budget.used == 7 == plan.steps_simulated and budget.exhausted


def test_bfs_reports_node_limit_and_not_found() -> None:
    history = synthetic_history([act(1)] * 10)
    limited = _plan(history, rp.SimulationBudget(10_000), rp.PlannerLimits(2, 2))
    assert limited.outcome == rp.PLAN_NODE_LIMIT and limited.nodes_expanded == 2
    shallow = _plan(history, rp.SimulationBudget(10_000), rp.PlannerLimits(1, 10_000))
    assert shallow.outcome == rp.PLAN_NOT_FOUND and shallow.nodes_expanded == 1


def test_bfs_stops_on_deadline_and_on_model_error() -> None:
    history = synthetic_history([act(1)] * 10)
    ticks = iter([0.0, 0.0, 100.0, 100.0, 100.0, 100.0, 100.0])
    deadline = Deadline(1.0, clock=lambda: next(ticks))
    timed = _plan(history, rp.SimulationBudget(1000), deadline=deadline)
    assert timed.outcome == rp.PLAN_DEADLINE and timed.actions == ()

    class Broken:
        def predict(self, history: History, action: ActionRecord) -> Observation:
            raise WorldModelError("boom")

    broken = rp.plan_to_next_level(
        Broken(), history, hypothesis_id="h", certification_history_length=10,
        budget=rp.SimulationBudget(10), limits=LIMITS,
    )  # fmt: skip
    assert broken.outcome == rp.PLAN_MODEL_ERROR and broken.reason == "boom"
    with pytest.raises(rp.PlannerError, match="exceeds"):
        rp.plan_to_next_level(
            SyntheticModel(), history, hypothesis_id="h", certification_history_length=11,
            budget=rp.SimulationBudget(10), limits=LIMITS,
        )  # fmt: skip


# --------------------------------------------------------------------------- diagnostics (G3.6b)


def _obs(value: int, levels: int = 0, actions: tuple[int, ...] = (1, 2)) -> Observation:
    return Observation((((value,),),), "NOT_FINISHED", levels, actions)


class TwoStateModel:
    """A closed world: action 1 toggles between two frames, action 2 is a no-op. No action
    ever raises ``levels_completed``, so a BFS over it must exhaust its queue by dedup alone."""

    def predict(self, history: History, action: ActionRecord) -> Observation:
        last = history.last_observation()
        value = last.frame[0][0][0]
        return _obs(1 - value if action.action == 1 else value)


class ChainModel:
    """An open world: action 1 always produces a never-seen frame (a counter), the level
    never completes, so only the depth cap can stop the search."""

    def predict(self, history: History, action: ActionRecord) -> Observation:
        return _obs(history.last_observation().frame[0][0][0] + 1, actions=(1,))


def _diag(model: object, limits: rp.PlannerLimits, trace: list[dict[str, object]] | None = None,
          root: Observation | None = None) -> rp.Plan:  # fmt: skip
    return rp.plan_to_next_level(
        model,  # type: ignore[arg-type]
        History(root or _obs(0)),
        hypothesis_id="h",
        certification_history_length=0,
        budget=rp.SimulationBudget(10_000),
        limits=limits,
        trace=trace,
    )


def test_closed_world_exhausts_the_queue_by_deduplication_alone() -> None:
    trace: list[dict[str, object]] = []
    plan = _diag(TwoStateModel(), rp.PlannerLimits(max_depth=8, max_nodes=100), trace)
    assert plan.outcome == rp.PLAN_NOT_FOUND and plan.reason is None
    assert plan.queue_exhausted is True
    assert plan.nodes_expanded == 2 and plan.steps_simulated == 4
    assert plan.distinct_states == 2 and plan.duplicate_predictions == 3
    assert plan.successors_dropped_at_depth_cap == 0  # the reachable set closed on its own
    assert plan.max_depth_reached == 2 and plan.predicted_levels_completed_max == 0
    assert plan.predicted_state_counts == {"NOT_FINISHED": 4}
    assert plan.frame_unchanged_predictions == 2  # the two no-op predictions
    assert "queue exhausted after 2 nodes" in plan.stop_detail
    assert "0 new states dropped at depth cap 8" in plan.stop_detail
    d = plan.to_dict()
    assert d["queue_exhausted"] is True and d["predicted_state_counts"] == {"NOT_FINISHED": 4}
    assert d["stop_detail"] == plan.stop_detail
    # One trace record per prediction, in search order, with the flags the counts came from.
    assert len(trace) == 4
    assert [t["node_index"] for t in trace] == [0, 0, 1, 1]
    assert [t["depth"] for t in trace] == [1, 1, 2, 2]
    assert [t["action"] for t in trace] == [1, 2, 1, 2]
    assert [t["duplicate"] for t in trace] == [False, True, True, True]
    assert [t["enqueued"] for t in trace] == [True, False, False, False]
    assert [t["frame_unchanged"] for t in trace] == [False, True, False, True]
    assert all(t["found"] is False and t["state"] == "NOT_FINISHED" for t in trace)
    assert all(len(t["predicted_digest"]) == rp.TRACE_DIGEST_PREFIX for t in trace)
    assert json.dumps(trace)  # serialisable as written to plan_traces.jsonl


def test_open_world_is_truncated_by_the_depth_cap_and_says_so() -> None:
    chain_root = _obs(0, actions=(1,))
    plan = _diag(ChainModel(), rp.PlannerLimits(max_depth=3, max_nodes=100), root=chain_root)
    assert plan.outcome == rp.PLAN_NOT_FOUND and plan.queue_exhausted is True
    assert plan.nodes_expanded == 3 and plan.steps_simulated == 3
    assert plan.distinct_states == 4 and plan.duplicate_predictions == 0
    assert plan.successors_dropped_at_depth_cap == 1  # the depth-3 child was never expanded
    assert plan.max_depth_reached == 3 and plan.frame_unchanged_predictions == 0
    assert "1 new states dropped at depth cap 3" in plan.stop_detail
    # A node limit is reported as before, and is not a queue exhaustion.
    limited = _diag(ChainModel(), rp.PlannerLimits(max_depth=10, max_nodes=2), root=chain_root)
    assert limited.outcome == rp.PLAN_NODE_LIMIT and limited.queue_exhausted is False
    assert limited.stop_detail == f"{rp.PLAN_NODE_LIMIT}: max_nodes 2 reached"


def test_found_plan_diagnostics_and_trace() -> None:
    history = synthetic_history([act(1)] * 15)
    trace: list[dict[str, object]] = []
    plan = rp.plan_to_next_level(
        SyntheticModel(), history, hypothesis_id="h1", certification_history_length=15,
        budget=rp.SimulationBudget(1000), limits=LIMITS, trace=trace,
    )  # fmt: skip
    assert plan.outcome == rp.PLAN_FOUND and plan.actions == (act(1),)
    assert plan.queue_exhausted is False and plan.successors_dropped_at_depth_cap == 0
    assert plan.predicted_levels_completed_max == 1 == plan.target_levels_completed
    assert plan.stop_detail == "found at depth 1 after 1 nodes"
    assert len(trace) == 1 and trace[0]["found"] is True and trace[0]["levels_completed"] == 1
    assert trace[0]["enqueued"] is False and trace[0]["duplicate"] is False
    # Without a trace list the search records nothing extra and returns the same plan.
    again = _plan(synthetic_history([act(1)] * 15), rp.SimulationBudget(1000))
    assert again.to_dict() == plan.to_dict()


# --------------------------------------------------------------------------- exploration (synthetic)


def _explore_synthetic(seed: int, steps: int) -> list[ActionRecord]:
    model, policy = SyntheticModel(), rp.ExplorationPolicy(seed, 0, grid_size=4)
    history = History(INITIAL)
    chosen: list[ActionRecord] = []
    for _ in range(steps):
        obs = history.last_observation()
        action = ActionRecord(0) if obs.state == "GAME_OVER" else policy.choose(obs)
        chosen.append(action)
        history = history.extend(action, model.predict(history, action))
    return chosen


def test_exploration_is_deterministic_per_seed_and_differs_across_seeds() -> None:
    a, b, c = (
        _explore_synthetic(12345, 30),
        _explore_synthetic(12345, 30),
        _explore_synthetic(7, 30),
    )
    assert a == b and a != c
    assert all(0 <= v < 4 for x in a if x.action == 6 for v in x.data.values())


def test_exploration_prefers_untested_pairs_and_avoids_voluntary_reset() -> None:
    policy = rp.ExplorationPolicy(1, 3)
    obs = Observation(INITIAL.frame, "NOT_FINISHED", 0, (0, 1, 2))
    first, second = policy.choose(obs), policy.choose(obs)
    assert {first.action, second.action} == {1, 2}  # both untested, never RESET
    third = policy.choose(obs)
    assert third.action in (1, 2) and policy.untested_choices == 2 and policy.actions_chosen == 3
    only_reset = Observation(INITIAL.frame, "GAME_OVER", 0, (0,))
    assert policy.choose(only_reset) == ActionRecord(0)
    with pytest.raises(rp.ExplorationError):
        policy.choose(Observation(INITIAL.frame, "NOT_FINISHED", 0, ()))
    assert policy.to_dict()["pairs_tested"] == 3


# --------------------------------------------------------------------------- the true simulator


def _explore_true_game(
    game_id: str, seed: int, game_index: int, multiplier: int, max_actions: int
) -> tuple[la.LevelAccounting, list[ActionRecord]]:
    """The model-free control loop the E300 runner will use, on the real offline toolkit."""
    from arc_plasticity.hypotheses.true_model import TrueModel

    model = TrueModel(ENV_DIR, game_id, seed)
    policy = rp.ExplorationPolicy(seed, game_index)
    acc = la.LevelAccounting(
        la.load_official_baselines(ENV_DIR, game_id), multiplier, game_id=game_id
    )
    history = History(model.initial_observation())
    chosen: list[ActionRecord] = []
    while not acc.stopped:
        obs = history.last_observation()
        action = ActionRecord(0) if obs.state == "GAME_OVER" else policy.choose(obs)
        predicted = model.predict(history, action)
        history = history.extend(action, predicted)
        chosen.append(action)
        acc.record_action(action.action, predicted.levels_completed, predicted.state)
        reason = acc.evaluate_stop(predicted.state)
        if reason is None and acc.actions_total >= max_actions:
            reason = la.STOP_WALLCLOCK  # the runner's own reason, standing in for its deadline
        if reason is not None:
            acc.stop(reason)
    assert model.rebuilds == 1 and model.steps == len(chosen)  # the prefix fast path held
    return acc, chosen


@needs_toolkit_cache
@pytest.mark.parametrize("stem", ["ar25", "ls20"])
def test_model_free_loop_on_the_true_simulator_respects_the_stop_rule(stem: str) -> None:
    manifest = json.loads((ROOT / "experiments" / "environment_cache_manifest.json").read_text())
    game_id = next(
        str(
            g.get("game_id")
            or Path(str(g["local_dir"])).parent.name + "-" + Path(str(g["local_dir"])).name
        )
        for g in manifest["games"]
        if str(g.get("stem") or g.get("game_id") or g["local_dir"]).find(stem) >= 0
    )
    acc, chosen = _explore_true_game(game_id, 12345, 0, 5, max_actions=400)
    again, chosen_again = _explore_true_game(game_id, 12345, 0, 5, max_actions=400)
    assert chosen == chosen_again and acc.to_dict() == again.to_dict()
    assert acc.stop_reason in la.STOP_REASONS and acc.over_budget_levels() == []
    assert acc.actions_total == len(chosen)
    if acc.stop_reason == la.STOP_LEVEL_BUDGET_EXHAUSTED:
        level = acc.level_records()[acc.levels_completed]
        assert level.actions_attributed == level.budget == 5 * level.official_baseline_actions
    assert acc.rhae_environment_score() >= 0.0
    d = acc.to_dict()
    assert d["stem"] == stem and d["win_levels"] == len(d["levels"])


@needs_toolkit_cache
def test_planner_on_the_true_simulator_is_bounded_by_the_simulation_budget() -> None:
    from arc_plasticity.hypotheses.true_model import TrueModel

    game_id = "ar25-0c556536"
    model = TrueModel(ENV_DIR, game_id, 12345)
    history = History(model.initial_observation())
    budget = rp.SimulationBudget(30)
    plan = rp.plan_to_next_level(
        model, history, hypothesis_id="true_model", certification_history_length=0,
        budget=budget, limits=rp.PlannerLimits(max_depth=3, max_nodes=50),
    )  # fmt: skip
    assert plan.outcome in rp.PLAN_OUTCOMES and plan.outcome != rp.PLAN_MODEL_ERROR
    assert plan.steps_simulated == budget.used <= 30
    assert plan.target_levels_completed == 1
    if plan.outcome == rp.PLAN_FOUND:
        assert 1 <= len(plan.actions) <= 3
