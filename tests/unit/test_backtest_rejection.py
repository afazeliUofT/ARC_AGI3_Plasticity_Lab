"""Unit tests for the E310 wrong-model generator and runner (``backtest_rejection``).

The synthetic world (tests/g3_synthetic.py) stands in for the toolkit with a fake history
source, so the trial derivation, the discrimination re-draw, the vacuous accounting, the
control trials and the results assembly are tested without the environment cache. One
toolkit-backed test runs the registered runner on a single cached game through the canonical
entry point into a temporary artifacts root (skipped when the cache or the G1 run is absent).
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest
import yaml

from arc_plasticity.core.config import ExperimentConfig
from arc_plasticity.core.guards import Deadline
from arc_plasticity.environments.arc_interface import ActionRecord
from arc_plasticity.evaluation import backtest_rejection as br
from arc_plasticity.hypotheses import backtest as bt
from arc_plasticity.hypotheses import mutations as mu
from arc_plasticity.hypotheses.interface import (
    CERTIFICATION_FIELDS,
    History,
    Observation,
    WorldModel,
)
from tests.g3_synthetic import DEFAULT_ACTIONS, SyntheticModel, act, synthetic_history

ROOT = Path(__file__).resolve().parents[2]
ENV_DIR = ROOT / "environment_files"
G1_RUN = ROOT / "artifacts" / "E100_arc_interface" / "20260904T074939Z_seed12345_8383cad8"
CONFIG = ROOT / "configs" / "experiments" / "E310_ref_backtest_rejection.yaml"

needs_toolkit_cache = pytest.mark.skipif(
    not (ENV_DIR / "ar25").exists() or not (G1_RUN / "transitions.jsonl").exists(),
    reason="offline environment cache or the graded G1 run is absent",
)

LIMITS = bt.BacktestLimits(
    backtest_seconds_max=30.0, predict_seconds_max=5.0, address_space_bytes_max=2**31
)


class OtherWorldModel:
    """A different synthetic world: action 1 adds 2 to cell (0,0) instead of 1."""

    def __init__(self) -> None:
        self._inner = SyntheticModel()

    def predict(self, history: History, action: ActionRecord) -> Observation:
        true = self._inner.predict(history, action)
        if action.action != 1:
            return true
        grid = [list(row) for row in true.frame[0]]
        grid[0][0] = (grid[0][0] + 1) % 16
        return Observation(
            (tuple(tuple(r) for r in grid),),
            true.state,
            true.levels_completed,
            true.available_actions,
        )


def factory(game_id: str) -> WorldModel:
    return OtherWorldModel() if game_id.startswith("other") else SyntheticModel()


def game(
    index: int, game_id: str, actions: tuple[ActionRecord, ...] = DEFAULT_ACTIONS
) -> br.GameHistory:
    history = synthetic_history(actions)
    return br.GameHistory(
        game_index=index,
        game_id=game_id,
        history=history,
        final_frame_sha256_expected="x",
        final_frame_sha256_replayed="x",
        frame_digest_mismatches=0,
    )


def params(**overrides: Any) -> br.RejectionParams:
    values: dict[str, Any] = {
        "environments_dir": ROOT / "environment_files",
        "history_source": ROOT / "nowhere" / "transitions.jsonl",
        "history_source_sha256sums_sha256": "0" * 64,
        "games": None,
        "trial_seeds_per_game": 10,
        "control_trials_per_game": 1,
        "redraw_max": 20,
        "limits": LIMITS,
    }
    values.update(overrides)
    return br.RejectionParams(**values)


# ------------------------------------------------------------------ derivation


def test_class_plan_is_balanced_and_seeded() -> None:
    plan = br.class_plan(12345, 3, 10)
    assert len(plan) == 10
    assert set(plan[:8]) == set(mu.MUTATION_CLASSES)  # first block is a permutation
    assert plan == br.class_plan(12345, 3, 10)
    assert plan != br.class_plan(12346, 3, 10) or br.class_plan(12345, 4, 10) != plan
    counts = {c: plan.count(c) for c in mu.MUTATION_CLASSES}
    assert min(counts.values()) >= 1 and max(counts.values()) <= 2


def test_trial_rng_is_a_pure_function_of_seed_game_trial() -> None:
    a = br.trial_rng(1, 2, 3).integers(0, 1 << 30, size=4)
    b = br.trial_rng(1, 2, 3).integers(0, 1 << 30, size=4)
    c = br.trial_rng(1, 2, 4).integers(0, 1 << 30, size=4)
    assert np.array_equal(a, b) and not np.array_equal(a, c)


# ------------------------------------------------------------------ discrimination


def test_discrimination_site_for_index_targeted_class() -> None:
    g = game(0, "syn")
    spec = mu.MutationSpec(
        "single_cell_flip", {"index": 5, "grid": 0, "row": 2, "col": 2, "colour_delta": 3}
    )
    site, why = br.discrimination_site(mu.MutatedModel(SyntheticModel(), spec), g.history, spec)
    assert site == 5 and why == "frame"


def test_discrimination_site_vacuous_colour_permutation() -> None:
    g = game(0, "syn")
    # A permutation fixing every colour present in the frame at index 0 (only 0 and 1 present
    # after the first action) is vacuous for that transition.
    frame = g.history.transitions[0].observation.frame[0]
    present = {v for row in frame for v in row}
    perm = list(range(16))
    free = [v for v in range(16) if v not in present]
    perm[free[0]], perm[free[1]] = perm[free[1]], perm[free[0]]
    spec = mu.MutationSpec("colour_permutation", {"index": 0, "permutation": perm})
    site, why = br.discrimination_site(mu.MutatedModel(SyntheticModel(), spec), g.history, spec)
    assert site is None and why is None


def test_discrimination_site_whole_history_classes_scan_in_order() -> None:
    g = game(0, "syn")
    spec = mu.MutationSpec("identity_model")
    site, why = br.discrimination_site(mu.MutatedModel(SyntheticModel(), spec), g.history, spec)
    assert site == 0 and why == "frame"
    # identity is vacuous on a history whose transitions change nothing (action 3 is a no-op)
    static = game(1, "syn", (act(3), act(3), act(3)))
    site, why = br.discrimination_site(
        mu.MutatedModel(SyntheticModel(), spec), static.history, spec
    )
    assert site is None


class RaisingModel:
    def predict(self, history: History, action: ActionRecord) -> Observation:
        raise RuntimeError("boom")


def test_discrimination_site_counts_a_raise_as_discriminating() -> None:
    g = game(0, "syn")
    spec = mu.MutationSpec("other_game_simulator", {"other_game_id": "other"})
    mutated = mu.MutatedModel(SyntheticModel(), spec, other_model=RaisingModel())
    site, why = br.discrimination_site(mutated, g.history, spec)
    assert site == 0 and why == "raised:RuntimeError"


def test_redraw_stops_at_first_discriminating_draw_and_counts() -> None:
    g = game(0, "syn")
    rng = np.random.default_rng(7)
    spec, redraws, site, why = br.draw_discriminating_mutation(
        "single_cell_flip", rng, g, factory, ["other"], redraw_max=20
    )
    assert spec.mutation_class == "single_cell_flip" and redraws == 0
    assert site == spec.params["index"] and why == "frame"


def test_redraw_gives_up_after_redraw_max_on_a_vacuous_class() -> None:
    static = game(1, "syn", (act(3), act(3), act(3)))
    rng = np.random.default_rng(3)
    spec, redraws, site, _why = br.draw_discriminating_mutation(
        "identity_model", rng, static, factory, ["other"], redraw_max=20
    )
    assert redraws == 0 and site is None  # no parameters: checked once, then vacuous
    spec, redraws, site, _why = br.draw_discriminating_mutation(
        "colour_permutation", rng, game(2, "syn", (act(3),)), factory, ["other"], redraw_max=4
    )
    # a single no-op transition leaves only colour 0 present; almost every permutation moves
    # 0, so at most 4 re-draws happen and the result is either discriminating or vacuous
    assert redraws <= 4
    assert (site is None) == (spec.params["permutation"][0] == 0)


# ------------------------------------------------------------------ trials and summary


def test_run_game_trials_shapes_and_backtester_sees_only_history_and_model() -> None:
    g = game(0, "syn")
    trials = br.run_game_trials(g, 12345, params(), factory, ["other"], Deadline(60))
    assert len(trials) == 11
    wrong = [t for t in trials if t.kind == "wrong_model"]
    controls = [t for t in trials if t.kind == "control"]
    assert [t.mutation_class for t in wrong] == br.class_plan(12345, 0, 10)
    assert all(t.record is not None for t in trials)
    assert all(t.record is not None and t.record.certified for t in controls)
    for t in wrong:
        assert t.record is not None
        assert t.record.history_length == len(g.history)
        if not t.vacuous:
            assert t.rejected, (t.mutation_class, t.mutation_params)
            # rejected by a mismatch, or by a raise (a swapped id the synthetic world's
            # program cannot execute); the backtester certifies neither
            assert t.record.first_mismatch_index is not None or t.record.failure_kind
            if t.record.first_mismatch_index is not None and t.discrimination_index is not None:
                assert t.record.first_mismatch_index <= t.discrimination_index
        assert t.record.backtest_module_sha256 == bt.backtest_module_sha256()
        assert "mutation" not in json.dumps(t.record.to_dict())  # the record never carries the spec


def test_run_game_trials_is_deterministic_and_seed_sensitive() -> None:
    g = game(0, "syn")
    a = br.run_game_trials(g, 12345, params(), factory, ["other"], Deadline(60))
    b = br.run_game_trials(g, 12345, params(), factory, ["other"], Deadline(60))
    c = br.run_game_trials(g, 12346, params(), factory, ["other"], Deadline(60))

    def strip(ts: list[br.TrialResult]) -> list[dict[str, Any]]:
        return [dict(t.transition_row()) for t in ts]

    assert strip(a) == strip(b)
    assert strip(a) != strip(c)


def test_summary_excludes_vacuous_from_denominator_and_counts_controls() -> None:
    g = game(0, "syn")
    trials = br.run_game_trials(g, 12345, params(), factory, ["other"], Deadline(60))
    # force one trial vacuous by hand to exercise the accounting
    victim = next(t for t in trials if t.kind == "wrong_model")
    victim.vacuous = True
    summary = br.summarize_trials(trials)
    assert summary["wrong_model_trials"] == 10
    assert summary["vacuous_trials"] >= 1
    assert summary["non_vacuous_trials"] == 10 - summary["vacuous_trials"]
    assert summary["rejected_trials"] <= summary["non_vacuous_trials"]
    assert (
        summary["rejection_fraction"] == summary["rejected_trials"] / summary["non_vacuous_trials"]
    )
    assert summary["control_trials"] == 1 and summary["control_accepted"] == 1
    assert summary["correct_model_acceptance_fraction"] == 1.0
    # the synthetic world raises on a swapped id it cannot execute, so the only trials with
    # history_length_checked != history_length are those with a recorded failure_kind
    raised = [t for t in trials if t.record is not None and t.record.failure_kind]
    assert summary["history_length_checked_equal_length_all"] is (not raised)
    assert len(summary["history_length_checked_unequal_trials"]) == len(raised)
    per_class = summary["per_class"]
    assert set(per_class) == set(mu.MUTATION_CLASSES)
    assert sum(c["trials"] for c in per_class.values()) == 10
    assert sum(c["vacuous_trials"] for c in per_class.values()) == summary["vacuous_trials"]


def test_run_experiment_core_without_writer_and_other_game_pool() -> None:
    games = [game(0, "syn-a"), game(1, "other-b"), game(2, "syn-c")]
    trials, summary = br.run_experiment_core(
        games, 12345, params(trial_seeds_per_game=8), factory, None, Deadline(120)
    )
    assert summary["wrong_model_trials"] == 24 and summary["control_trials"] == 3
    assert all(
        c["trials"] == 3 for c in summary["per_class"].values()
    )  # 8 trials = one block per game
    others = [
        t.mutation_params["other_game_id"]
        for t in trials
        if t.mutation_class == "other_game_simulator"
    ]
    assert others and all(o in {"syn-a", "other-b", "syn-c"} for o in others)
    for t in trials:
        if t.mutation_class == "other_game_simulator":
            assert t.mutation_params["other_game_id"] != t.game_id
    assert summary["games"][1]["game_id"] == "other-b"
    assert summary["replay_identity_games"] == 3 and summary["replay_divergent_games"] == 0
    assert summary["backtest_module_sha256"] == bt.backtest_module_sha256()
    assert summary["class_assignment"] == br.CLASS_ASSIGNMENT
    rows = br.metrics_rows(summary, games)
    assert {r["metric"] for r in rows} >= {
        "rejection_fraction",
        "correct_model_acceptance_fraction",
    }
    assert all(not str(r["metric"]).endswith("seconds") for r in rows)
    env_rows = br.environment_rows(games, trials)
    assert [set(r) == set(br.ENVIRONMENT_COLUMNS) for r in env_rows] == [True] * 3


# ------------------------------------------------------------------ parameters


def _config(**runner_params: Any) -> ExperimentConfig:
    raw = yaml.safe_load(CONFIG.read_text())
    raw["runner_params"].update(runner_params)
    return ExperimentConfig.model_validate(raw)


def test_committed_config_parses_and_matches_the_locked_history_digest() -> None:
    cfg = _config()
    p = br.RejectionParams.from_config(cfg)
    assert p.trial_seeds_per_game == 10 and p.control_trials_per_game == 1 and p.redraw_max == 20
    assert p.games is None
    assert p.history_source_sha256sums_sha256 == (
        "6db258830174e76b032943689552631a7b458ffe0f3fad97429af8e1b75e5190"
    )
    assert cfg.network_calls_allowed == 0 and cfg.model_calls_allowed == 0


def test_config_limits_equal_the_preregistered_thresholds() -> None:
    vr = _load_module("verify_run")
    data, _, _ = vr.load_preregistration("G3", ROOT)
    p = br.RejectionParams.from_config(_config())
    assert p.limits.backtest_seconds_max == float(
        vr.threshold(data, "sandbox_backtest_seconds_max")
    )
    assert p.limits.predict_seconds_max == float(vr.threshold(data, "sandbox_predict_seconds_max"))
    assert p.limits.address_space_bytes_max == int(
        vr.threshold(data, "sandbox_address_space_bytes_max")
    )
    assert p.history_source_sha256sums_sha256 == vr.threshold(
        data, "g1_history_run_sha256sums_sha256"
    )
    assert p.trial_seeds_per_game * 25 >= int(vr.threshold(data, "backtest_wrong_model_trials_min"))
    assert p.control_trials_per_game * 25 >= int(vr.threshold(data, "backtest_control_trials_min"))


@pytest.mark.parametrize(
    "bad",
    [
        {"trial_seeds_per_game": 0},
        {"redraw_max": -1},
        {"history_source_sha256sums_sha256": "abc"},
        {"games": []},
        {"sandbox_limits": {"backtest_seconds_max": 1}},
        {
            "sandbox_limits": {
                "backtest_seconds_max": 0,
                "predict_seconds_max": 1,
                "address_space_bytes_max": 1,
            }
        },
        {"extra_artifacts": ["x.json"]},
    ],
)
def test_bad_runner_params_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(br.RunnerConfigError):
        br.RejectionParams.from_config(_config(**bad))


def test_history_source_digest_mismatch_is_refused(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "transitions.jsonl").write_text('{"game_id":"g","step_index":1,"action":1}\n')
    (run / "results.json").write_text(
        json.dumps(
            {
                "seed": 1,
                "results": {
                    "games": [{"game_id": "g", "final_frame_sha256": "f", "steps_taken": 1}]
                },
            }
        )
    )
    sums = "".join(
        f"{hashlib.sha256((run / n).read_bytes()).hexdigest()}  {n}\n"
        for n in ("results.json", "transitions.jsonl")
    )
    (run / "SHA256SUMS").write_text(sums)
    good = hashlib.sha256((run / "SHA256SUMS").read_bytes()).hexdigest()
    source = br.load_history_source(run / "transitions.jsonl", good)
    assert source.environment_seed == 1 and source.final_digests == {"g": "f"}
    with pytest.raises(br.HistorySourceError):
        br.load_history_source(run / "transitions.jsonl", "0" * 64)
    (run / "transitions.jsonl").write_text("{}\n")  # tampered after sealing
    with pytest.raises(br.HistorySourceError):
        br.load_history_source(run / "transitions.jsonl", good)


def _load_module(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ toolkit end to end


@needs_toolkit_cache
def test_runner_end_to_end_on_one_cached_game(tmp_path: Path) -> None:
    run_experiment = _load_module("run_experiment")
    cfg_path = tmp_path / "e310_smoke.yaml"
    raw = yaml.safe_load(CONFIG.read_text())
    # two games so other_game_simulator has a pool; sp80 (30 actions) and tu93 (50 actions)
    raw["runner_params"].update(
        {"games": ["sp80", "tu93"], "trial_seeds_per_game": 8, "control_trials_per_game": 1}
    )
    raw["wallclock_limit_seconds"] = 600
    cfg_path.write_text(yaml.safe_dump(raw))
    run_dir, status = run_experiment.run(
        cfg_path, artifacts_root=tmp_path / "artifacts", run_id="smoke"
    )
    assert status == "completed", (run_dir / "stderr.log").read_text()
    results = json.loads((run_dir / "results.json").read_text())["results"]
    assert results["operation_mode"] == "OFFLINE" and results["replay_divergent_games"] == 0
    assert [g["replay_identity"] for g in results["games"]] == [True, True]
    assert [g["history_length"] for g in results["games"]] == [30, 50]
    assert results["wrong_model_trials"] == 16 and results["control_trials"] == 2
    assert results["correct_model_acceptance_fraction"] == 1.0
    assert results["history_length_checked_equal_length_all"] is True
    assert results["backtest_module_sha256"] == bt.backtest_module_sha256()
    assert all(c["trials"] == 2 for c in results["per_class"].values())
    assert results["rejection_fraction"] == 1.0, results["per_class"]
    rows = [json.loads(line) for line in (run_dir / "transitions.jsonl").read_text().splitlines()]
    assert len(rows) == 18
    others = [r for r in rows if r["mutation_class"] == "other_game_simulator"]
    assert {r["mutation_params"]["other_game_id"] for r in others} <= {
        "sp80-589a99af",
        "tu93-0768757b",
    }
    hyps = [json.loads(line) for line in (run_dir / "hypotheses.jsonl").read_text().splitlines()]
    assert len(hyps) == 18
    assert all(h["history_length_checked"] == h["history_length"] for h in hyps)
    with (run_dir / "metrics.csv").open() as fh:
        metrics = {r["metric"]: r["value"] for r in csv.DictReader(fh)}
    assert metrics["control_accepted"] == "2" and metrics["rejection_fraction"] == "1.0"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["network_attempts"] == 0 and manifest["model_calls"] == 0
    assert all(f in CERTIFICATION_FIELDS for f in results["certification_fields"])
