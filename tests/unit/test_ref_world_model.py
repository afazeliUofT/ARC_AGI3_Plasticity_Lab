"""The E300 runner (G3.4 second half): the REF control loop on the synthetic world with a
recorded-response model stub, the full entry point on one cached game, the preflight
refusals, the --game selection, and the run set manifest builder."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from arc_plasticity.agents import history_encoding as he
from arc_plasticity.agents import model_client as mc
from arc_plasticity.agents import ref_world_model as rwm
from arc_plasticity.core.artifacts import CONTRACT_FILES, RunArtifactWriter, RunManifest
from arc_plasticity.core.config import load_experiment_config, resolve_config
from arc_plasticity.core.guards import Deadline
from arc_plasticity.core.runner import RunPreflightError
from arc_plasticity.environments import arc_interface as ai
from arc_plasticity.evaluation import level_accounting as la
from arc_plasticity.hypotheses import backtest as bt
from arc_plasticity.hypotheses.interface import History, Observation, history_to_wire
from arc_plasticity.hypotheses.sandbox import SandboxGuards
from arc_plasticity.planning import ref_planner as rp
from tests.g3_synthetic import INITIAL, SYNTHETIC_PROGRAM_SOURCE, SyntheticModel

ROOT = Path(__file__).resolve().parents[2]
ENV_DIR = ROOT / "environment_files"
CONFIG = ROOT / "configs" / "experiments" / "E300_ref.yaml"
CACHE_MANIFEST = ROOT / "experiments" / "environment_cache_manifest.json"
needs_toolkit_cache = pytest.mark.skipif(
    not (ENV_DIR / "ar25").exists(), reason="offline environment cache is absent"
)

IDENTITY_PROGRAM = """
def predict(history, action):
    last = history[-1]
    return {"frame": last["frame"], "state": last["state"],
            "levels_completed": last["levels_completed"],
            "available_actions": last["available_actions"]}
"""


def _script(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _responses(path: Path, texts: list[str]) -> Path:
    items = [
        {
            "text": f"```python\n{t}\n```",
            "usage": {"input_tokens": 100 * (i + 1), "output_tokens": 50},
            "model": "stub",
        }
        for i, t in enumerate(texts)
    ]
    path.write_text(json.dumps({"schema_version": 1, "responses": items}))
    return path


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _manifest_stub() -> RunManifest:
    return RunManifest(
        experiment_id="E300_ref",
        run_id="t",
        timestamp_utc="2026-09-04T00:00:00Z",
        git_commit="0",
        git_dirty=False,
        python_version="3.12",
        dependency_lock_hash="0",
        config_hash="0",
        environment_generator_version="synthetic",
        seed=12345,
        model_identifier="stub",
        prompt_hash=None,
        action_budget=160,
        simulation_budget=100000,
        token_budget=1000000,
        persistent_state_size_cap=0,
        hardware="test",
        wallclock_limit_seconds=600,
        completion_status="completed",
        wallclock_seconds=0.0,
        network_calls_allowed=0,
        network_attempts=0,
        model_calls_allowed=5,
        model_calls=0,
    )


# --------------------------------------------------------------------------- synthetic world


class SyntheticEnvironment:
    """The synthetic world behind :class:`rwm.GameEnvironment`, with two levels."""

    WIN_LEVELS = 2

    def __init__(self) -> None:
        self._model = SyntheticModel()
        self._history: History | None = None
        self.steps = 0

    def _summary(self, obs: Observation) -> ai.FrameSummary:
        return ai.FrameSummary(
            state=obs.state,
            levels_completed=obs.levels_completed,
            win_levels=self.WIN_LEVELS,
            frames=obs.frame,
            available_actions=obs.available_actions,
        )

    def reset(self) -> ai.FrameSummary:
        self._history = History(INITIAL)
        return self._summary(INITIAL)

    def step(self, action: ai.ActionRecord) -> ai.FrameSummary:
        assert self._history is not None
        obs = self._model.predict(self._history, action)
        self._history = self._history.extend(action, obs)
        self.steps += 1
        return self._summary(obs)


def _params(**overrides: Any) -> rwm.RefParams:
    base: dict[str, Any] = {
        "environments_dir": ENV_DIR,
        "cache_manifest": CACHE_MANIFEST,
        "cache_manifest_sha256": "0" * 64,
        "games": ("syn0",),
        "game": "syn0",
        "action_budget_multiplier": 5,
        "simulation_steps_per_game_max": 100_000,
        "model_calls_per_game_max": 5,
        "tokens_per_game_max": 1_000_000,
        "model_effort": "high",
        "induction_min_history": 4,
        "wallclock_reserve_seconds": 0,
        "planner_limits": rp.PlannerLimits(max_depth=16, max_nodes=5000),
        "click_grid_step": 0,
        "limits": bt.BacktestLimits(60.0, 5.0, 2**31),
        "model_client": {"kind": "recorded"},
    }
    base.update(overrides)
    return rwm.RefParams(**base)


def _run_synthetic(
    tmp_path: Path, name: str, texts: list[str], **overrides: Any
) -> tuple[Path, rwm.GameRunReport]:
    responses = _responses(tmp_path / f"{name}_responses.json", texts)
    params = _params(**overrides)
    client = mc.RecordedResponseClient(responses) if texts else None
    if not texts:
        params = _params(model_client=None, model_calls_per_game_max=0, **overrides)
    run_dir = tmp_path / name
    with RunArtifactWriter(run_dir, rwm.EXTRA_ARTIFACTS) as writer:
        game = rwm.RefGameRun(
            game_id="syn0-00000000",
            game_index=0,
            seed=12345,
            environment=SyntheticEnvironment(),
            baselines=[16, 16],
            params=params,
            client=client,
            writer=writer,
            deadline=Deadline(600),
            model_identifier="stub",
            prompt_template="Write the world model.",
            guards=SandboxGuards(ROOT, (ENV_DIR, ROOT / "data")),
        )
        report = game.run()
        writer.write_resolved_config("synthetic: true\n")
        writer.write_git_state("none\n")
        writer.write_environment_info({})
        writer.write_results({"results": rwm.results_mapping(report, params, _config_stub())})
        writer.write_metrics(rwm.metrics_rows(report))
        writer.write_environment_results(rwm.environment_rows(report), rwm.ENVIRONMENT_COLUMNS)
        writer.write_manifest(_manifest_stub())
        writer.finalize()
    return run_dir, report


def _config_stub() -> Any:
    raw = yaml.safe_load(CONFIG.read_text())
    raw["language_model"] = {"identifier": "stub", "prompt": "Write the world model."}
    from arc_plasticity.core.config import ExperimentConfig

    return ExperimentConfig.model_validate(raw)


def test_synthetic_world_wrong_program_then_true_program_completes_every_level(
    tmp_path: Path,
) -> None:
    run_dir, report = _run_synthetic(
        tmp_path, "happy", [IDENTITY_PROGRAM, SYNTHETIC_PROGRAM_SOURCE]
    )
    acc = report.accounting
    assert acc.stop_reason == la.STOP_ALL_LEVELS_COMPLETED  # the synthetic world has no WIN
    assert acc.levels_completed == 2 and acc.over_budget_levels() == []
    assert report.model_calls == 2 and report.hypotheses_proposed == 2
    assert report.hypotheses_certified == 1 and report.plans_executed >= 2
    assert report.prediction_mismatches == 0 and report.predictions_compared == report.plan_actions
    assert report.tokens_by_kind == {
        "input": 300,
        "output": 100,
        "cache_creation": 0,
        "cache_read": 0,
    }
    assert report.exploration_actions + report.reset_actions >= 4  # induction_min_history
    assert report.model_unavailable_reason is None

    hyps = _jsonl(run_dir / "hypotheses.jsonl")
    assert [h["hypothesis_id"] for h in hyps] == ["h001", "h002"]
    assert hyps[0]["certified"] is False and hyps[0]["parent_hypothesis_id"] is None
    assert hyps[1]["certified"] is True and hyps[1]["parent_hypothesis_id"] == "h001"
    assert hyps[1]["purpose"] == "revise" and hyps[1]["model_call_index"] == 2
    for h in hyps:
        source = (run_dir / h["source_path"]).read_text()
        assert hashlib.sha256(source.encode()).hexdigest() == h["source_sha256"]
    assert (run_dir / "world_models" / "h002.py").read_text() == mc.extract_program_source(
        SYNTHETIC_PROGRAM_SOURCE
    )

    backtests = _jsonl(run_dir / "backtests.jsonl")
    assert [b["certified"] for b in backtests] == [False, True]
    assert backtests[1]["history_length_checked"] == backtests[1]["history_length"] > 0
    assert backtests[1]["mismatches"] == 0
    assert backtests[0]["first_mismatch_index"] is not None
    assert all(b["backtest_module_sha256"] == bt.backtest_module_sha256() for b in backtests)

    plans = _jsonl(run_dir / "plans.jsonl")
    found = [p for p in plans if p["outcome"] == "found"]
    assert len(found) == report.plans_executed >= 2
    certified_lengths = {
        b["hypothesis_id"]: b["history_length"] for b in backtests if b["certified"]
    }
    for p in plans:
        assert p["hypothesis_id"] == "h002"
        assert p["certification_history_length"] == certified_lengths["h002"]
        assert p["planned_from_history_length"] >= p["certification_history_length"]

    rows = _jsonl(run_dir / "transitions.jsonl")
    assert len(rows) == acc.actions_total == report.model_calls * 0 + len(rows)
    assert [r["step_index"] for r in rows] == list(range(1, len(rows) + 1))
    plan_rows = [r for r in rows if r["source"] == "plan"]
    assert len(plan_rows) == report.plan_actions
    assert all(r["hypothesis_id"] == "h002" and r["prediction_matched"] is True for r in plan_rows)
    assert all(r["predicted_observation_sha256"] == r["observation_sha256"] for r in plan_rows)
    pre_model = [r for r in rows if r["hypothesis_id"] is None]
    assert all(r["prediction_matched"] is None for r in pre_model)
    assert all(len(r["frame"]) == 1 and len(r["frame"][0]) == 4 for r in rows)

    rebuilt = la.accounting_from_log([16, 16], 5, rows, game_id="syn0-00000000")
    rebuilt.stop(acc.stop_reason or "")
    assert rebuilt.to_dict() == json.loads((run_dir / "level_accounting.json").read_text())

    calls = _jsonl(run_dir / "model_calls.jsonl")
    assert [c["call_index"] for c in calls] == [1, 2]
    assert [c["purpose"] for c in calls] == ["induce", "revise"]
    for c in calls:
        prompt = (run_dir / c["prompt_path"]).read_text()
        assert hashlib.sha256(prompt.encode()).hexdigest() == c["prompt_sha256"]
        response = (run_dir / c["response_path"]).read_text()
        assert hashlib.sha256(response.encode()).hexdigest() == c["response_sha256"]
        assert c["tools_disabled"] is True and not Path(c["cwd"]).is_relative_to(ROOT)
        assert c["effort"] == "high" and c["model_identifier_sent"] == "stub"
    second_prompt = (run_dir / "model_calls" / "2.prompt.txt").read_text()
    assert "## Rejected programs" in second_prompt and "## Counterexamples" in second_prompt
    assert '"hypothesis_id":"h001"' in second_prompt

    rhae = json.loads((run_dir / "rhae.json").read_text())
    assert rhae["rhae_environment_score"] == acc.rhae_environment_score() > 0.0
    results = json.loads((run_dir / "results.json").read_text())["results"]
    assert results["stop_reason"] == la.STOP_ALL_LEVELS_COMPLETED
    assert results["model_client_sha256"] == mc.model_client_sha256()
    assert results["interface_module_sha256"] and results["backtest_module_sha256"]
    assert results["resumptions"] == 0 and results["exploration_actions"] >= 3
    sums = (run_dir / "SHA256SUMS").read_text()
    for name in ("model_calls/1.prompt.txt", "model_calls/2.response.json", "world_models/h002.py"):
        assert f"  {name}\n" in sums
    for name in CONTRACT_FILES:
        assert (run_dir / name).exists()


def test_synthetic_runner_is_deterministic_given_the_responses(tmp_path: Path) -> None:
    a_dir, a = _run_synthetic(tmp_path, "a", [IDENTITY_PROGRAM, SYNTHETIC_PROGRAM_SOURCE])
    b_dir, b = _run_synthetic(tmp_path, "b", [IDENTITY_PROGRAM, SYNTHETIC_PROGRAM_SOURCE])
    for name in ("transitions.jsonl", "plans.jsonl", "level_accounting.json", "rhae.json"):
        assert (a_dir / name).read_bytes() == (b_dir / name).read_bytes(), name
    assert a.accounting.to_dict() == b.accounting.to_dict()
    hyps_a = [dict(h) for h in _jsonl(a_dir / "hypotheses.jsonl")]
    hyps_b = [dict(h) for h in _jsonl(b_dir / "hypotheses.jsonl")]
    assert hyps_a == hyps_b


def test_synthetic_mismatch_decertifies_and_stops_when_the_model_budget_is_consumed(
    tmp_path: Path,
) -> None:
    # A program that is right until the first click, then wrong: the synthetic program
    # with ACTION6 ignored. Certification passes only if no click was explored yet; the
    # exploration policy tries every action from the reset frame, so a click is in the
    # first four actions and the program is rejected. Then the responses are exhausted.
    no_click = SYNTHETIC_PROGRAM_SOURCE.replace("elif aid == 6:", "elif aid == 60:")
    run_dir, report = _run_synthetic(tmp_path, "mismatch", [no_click])
    acc = report.accounting
    assert report.model_calls == 1 and report.model_unavailable_reason is not None
    assert "exhausted" in report.model_unavailable_reason
    assert acc.stop_reason == la.STOP_MODEL_BUDGET_EXHAUSTED
    assert report.model_budget_consumed and acc.levels_completed == 0
    hyps = _jsonl(run_dir / "hypotheses.jsonl")
    assert hyps[0]["certified"] is False
    assert (run_dir / "world_models" / "h001.py").exists()
    assert _jsonl(run_dir / "plans.jsonl") == []
    results = json.loads((run_dir / "results.json").read_text())["results"]
    assert (
        results["hypotheses_certified"] == 0 and results["stop_reason"] == "model_budget_exhausted"
    )


def test_synthetic_model_free_run_explores_to_the_level_budget(tmp_path: Path) -> None:
    run_dir, report = _run_synthetic(tmp_path, "free", [])
    acc = report.accounting
    assert report.model_calls == 0 and not report.model_budget_consumed
    assert acc.stop_reason in (la.STOP_LEVEL_BUDGET_EXHAUSTED, la.STOP_ALL_LEVELS_COMPLETED)
    assert acc.actions_total == report.exploration_actions + report.reset_actions
    assert (run_dir / "world_models" / "EMPTY").exists()
    assert (run_dir / "model_calls" / "EMPTY").exists()
    assert (
        _jsonl(run_dir / "model_calls.jsonl") == [] and _jsonl(run_dir / "hypotheses.jsonl") == []
    )


def test_step_failure_is_a_run_failure_with_artifacts_preserved(tmp_path: Path) -> None:
    class Flaky(SyntheticEnvironment):
        def step(self, action: ai.ActionRecord) -> ai.FrameSummary | None:  # type: ignore[override]
            return None if self.steps >= 2 else super().step(action)

    params = _params(model_client=None, model_calls_per_game_max=0)
    run_dir = tmp_path / "flaky"
    with RunArtifactWriter(run_dir, rwm.EXTRA_ARTIFACTS) as writer:
        game = rwm.RefGameRun(
            game_id="syn0-00000000", game_index=0, seed=1, environment=Flaky(),
            baselines=[16, 16], params=params, client=None, writer=writer,
            deadline=Deadline(600), model_identifier=None, prompt_template=None,
        )  # fmt: skip
        report = game.run()
    assert report.accounting.stop_reason == la.STOP_STEP_FAILED and report.step_failed_at == 3
    assert report.accounting.actions_total == 2
    accounting = json.loads((run_dir / "level_accounting.json").read_text())
    assert accounting["stop_reason"] == "step_failed" and accounting["actions_total"] == 2
    assert "step_failed" in (run_dir / "stderr.log").read_text()


def test_calls_without_program_count_but_propose_nothing_then_unavailable(tmp_path: Path) -> None:
    """G3.5: a made call with no program (non-zero exit / empty text) is charged, proposes no
    hypothesis, and after CALLS_WITHOUT_PROGRAM_MAX in a row the channel is unavailable."""
    path = tmp_path / "empty_responses.json"
    items = [{"text": "", "usage": {"input_tokens": 10}, "exit_code": 1} for _ in range(5)]
    path.write_text(json.dumps({"schema_version": 1, "responses": items}))
    run_dir = tmp_path / "empty"
    with RunArtifactWriter(run_dir, rwm.EXTRA_ARTIFACTS) as writer:
        game = rwm.RefGameRun(
            game_id="syn0-00000000", game_index=0, seed=12345,
            environment=SyntheticEnvironment(), baselines=[16, 16], params=_params(),
            client=mc.RecordedResponseClient(path), writer=writer, deadline=Deadline(600),
            model_identifier="stub", prompt_template="T",
            guards=SandboxGuards(ROOT, (ENV_DIR, ROOT / "data")),
        )  # fmt: skip
        report = game.run()
        writer.write_resolved_config("synthetic: true\n")
        writer.write_git_state("none\n")
        writer.write_environment_info({})
        writer.write_results({"results": rwm.results_mapping(report, _params(), _config_stub())})
        writer.write_metrics(rwm.metrics_rows(report))
        writer.write_environment_results(rwm.environment_rows(report), rwm.ENVIRONMENT_COLUMNS)
        writer.write_manifest(_manifest_stub())
        writer.finalize()
    assert report.model_calls == rwm.CALLS_WITHOUT_PROGRAM_MAX == 3
    assert report.calls_without_program == 3 and report.hypotheses_proposed == 0
    assert report.tokens_by_kind["input"] == 30
    assert report.model_unavailable_reason == (
        "3 consecutive model calls returned no program (last exit_code=1)"
    )
    rows = [json.loads(l) for l in (run_dir / "model_calls.jsonl").read_text().splitlines()]
    assert [r["program_returned"] for r in rows] == [False, False, False]
    assert all(r["exit_code"] == 1 for r in rows)
    assert not any((run_dir / "world_models").glob("*.py"))
    assert (run_dir / "hypotheses.jsonl").read_text() == ""
    results = json.loads((run_dir / "results.json").read_text())["results"]
    assert results["calls_without_program"] == 3
    assert results["calls_without_program_max_consecutive"] == 3
    assert results["history_encoding"] == {
        "name": "rle_rows_delta_v1",
        "module_sha256": he.history_encoding_sha256(),
    }
    assert "returned no program" in (run_dir / "stdout.log").read_text()


def test_build_prompt_carries_history_budget_and_counterexamples() -> None:
    history = History(INITIAL)
    prompt = rwm.build_prompt(
        "TEMPLATE", history, [{"hypothesis_id": "h001", "kind": "backtest"}],
        [("h001", "def predict(h, a): pass")], 37, 2,
    )  # fmt: skip
    assert prompt.startswith("TEMPLATE\n")
    assert "def predict(history: list[dict], action: dict) -> dict" in prompt
    assert "current level: 2; actions remaining on this level: 37" in prompt
    assert "### h001" in prompt and '"kind":"backtest"' in prompt
    assert "## Recorded history (rle_rows_delta_v1; record 0 is the reset observation)" in prompt
    assert he.ENCODING_DESCRIPTION.rstrip() in prompt
    encoded = he.encode_history_compact(history_to_wire(history))
    assert encoded.rstrip() in prompt
    assert (
        'record 0: reset; state="NOT_FINISHED"; levels_completed=0; '
        "available_actions=[1,2,3,4,6]\nframe: full, 1 grid(s)\ng0 r0-r3: 0*4\n"
    ) == encoded
    assert he.decode_history_compact(encoded) == history_to_wire(history)
    assert "environment_files" not in prompt and "human_replays" not in prompt


def test_click_points_lattice() -> None:
    assert rwm.click_points_for_step(0) == ()
    pts = rwm.click_points_for_step(32)
    assert pts == ((16, 16), (48, 16), (16, 48), (48, 48))
    assert len(rwm.click_points_for_step(16)) == 16


# --------------------------------------------------------------------------- parameters


def test_params_from_the_committed_config_match_the_pre_registration() -> None:
    vr = _script("verify_run")
    prereg, _, _ = vr.load_preregistration("G3", ROOT)
    config = resolve_config(load_experiment_config(CONFIG))
    params = rwm.RefParams.from_config(config)
    t = lambda key: vr.threshold(prereg, key)
    assert params.action_budget_multiplier == t("action_budget_multiplier")
    assert params.model_calls_per_game_max == t("model_calls_per_game_max")
    assert params.tokens_per_game_max == t("tokens_per_game_max")
    assert params.simulation_steps_per_game_max == t("simulation_steps_per_game_max")
    assert params.limits.backtest_seconds_max == t("sandbox_backtest_seconds_max")
    assert params.limits.predict_seconds_max == t("sandbox_predict_seconds_max")
    assert params.limits.address_space_bytes_max == t("sandbox_address_space_bytes_max")
    assert params.cache_manifest_sha256 == str(t("cache_manifest_sha256"))
    assert params.model_effort == t("model_effort")
    assert config.language_model.identifier == t("model_identifier")
    assert config.model_calls_allowed == t("model_calls_per_game_max")
    assert config.wallclock_limit_seconds == t("wallclock_per_invocation_seconds")
    assert config.network_calls_allowed == t("network_calls_allowed")
    assert len(params.games) == t("public_games_total") and params.game is None
    experiment = vr.section(prereg, "experiment")
    assert config.experiment_id == experiment["experiment_id"]
    assert config.runner == experiment["runner"]
    assert config.seed == experiment["seed"]
    listed = [e.split(" ")[0] for e in experiment["extra_artifacts"]]
    assert listed == list(rwm.EXTRA_ARTIFACTS)
    assert config.budgets.persistent_state_size_cap_bytes == t(
        "cross_game_persistent_state_bytes_max"
    )


def test_params_reject_malformed_runner_params() -> None:
    config = resolve_config(load_experiment_config(CONFIG))

    def with_params(**changes: Any) -> Any:
        return config.model_copy(update={"runner_params": {**config.runner_params, **changes}})

    for changes, message in (
        ({"games": ["ar25", "ar25"]}, "distinct"),
        ({"game": "zzzz"}, "not one of games"),
        ({"planner": {"max_depth": 0, "max_nodes": 1, "click_grid_step": 0}}, "planner"),
        ({"sandbox_limits": {"backtest_seconds_max": 1}}, "exactly"),
        ({"extra_artifacts": ["plans.jsonl"]}, "extra_artifacts"),
        ({"cache_manifest_sha256": "abc"}, "64-hex"),
        ({"model_client": "recorded"}, "model_client"),
    ):
        with pytest.raises(rwm.RunnerConfigError, match=message):
            rwm.RefParams.from_config(with_params(**changes))


# --------------------------------------------------------------------------- the entry point


def _toolkit_config(tmp_path: Path, name: str, client: dict[str, Any], calls: int) -> Path:
    raw = yaml.safe_load(CONFIG.read_text())
    raw["wallclock_limit_seconds"] = 900
    raw["model_calls_allowed"] = calls
    raw["runner_params"]["model_calls_per_game_max"] = calls
    raw["runner_params"]["model_client"] = client
    raw["runner_params"]["planner"] = {"max_depth": 3, "max_nodes": 200, "click_grid_step": 0}
    raw["runner_params"]["wallclock_reserve_seconds"] = 0
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return path


@needs_toolkit_cache
def test_select_game_resolves_the_per_game_action_budget() -> None:
    config = resolve_config(load_experiment_config(CONFIG))
    runner = rwm.RefWorldModelRunner()
    selected = runner.select_game(config, "ar25")
    assert selected.runner_params["game"] == "ar25"
    assert selected.budgets.action_budget == 5 * sum(
        la.load_official_baselines(ENV_DIR, "ar25-0c556536")
    )
    assert selected.budgets.simulation_budget == config.budgets.simulation_budget
    with pytest.raises(RunPreflightError, match="not one of"):
        runner.select_game(config, "zzzz")


@needs_toolkit_cache
def test_preflight_refusals(tmp_path: Path) -> None:
    runner = rwm.RefWorldModelRunner()
    config = resolve_config(load_experiment_config(CONFIG))
    with pytest.raises(RunPreflightError, match="--game"):
        runner.preflight(config)
    # The committed config names the headless channel (G3.5): preflight passes when a
    # `claude` executable is on PATH and refuses otherwise, without touching any model.
    if shutil.which("claude") is not None:
        runner.preflight(runner.select_game(config, "ar25"))
    else:
        with pytest.raises(RunPreflightError, match="not found on PATH"):
            runner.preflight(runner.select_game(config, "ar25"))
    # No client while a model call could be needed.
    no_client = _toolkit_config(tmp_path, "no_client", {"kind": "none"}, 60)
    with pytest.raises(RunPreflightError, match="no model client"):
        runner.preflight(
            runner.select_game(resolve_config(load_experiment_config(no_client)), "ar25")
        )
    # A tampered cache manifest digest.
    tampered = config.model_copy(
        update={"runner_params": {**config.runner_params, "cache_manifest_sha256": "1" * 64}}
    )
    with pytest.raises(RunPreflightError, match="sha256"):
        runner.select_game(tampered, "ar25")
    # An action budget that is not multiplier x sum(baselines).
    selected = runner.select_game(config, "ar25")
    wrong = selected.model_copy(
        update={"budgets": selected.budgets.model_copy(update={"action_budget": 1})}
    )
    with pytest.raises(RunPreflightError, match="action_budget"):
        runner.preflight(wrong)


@needs_toolkit_cache
def test_entry_point_refuses_game_flag_for_other_runners(tmp_path: Path) -> None:
    rx = _script("run_experiment")
    from arc_plasticity.core.config import ConfigError

    with pytest.raises(ConfigError, match="does not accept --game"):
        rx.run(ROOT / "configs" / "experiments" / "E000_bootstrap.yaml", game="ar25",
               artifacts_root=tmp_path / "artifacts")  # fmt: skip


@needs_toolkit_cache
def test_entry_point_runs_one_cached_game_with_recorded_responses(tmp_path: Path) -> None:
    rx = _script("run_experiment")
    vr = _script("verify_run")
    responses = _responses(tmp_path / "responses.json", [IDENTITY_PROGRAM])
    cfg = _toolkit_config(
        tmp_path, "recorded", {"kind": "recorded", "responses_file": str(responses)}, 60
    )
    artifacts = tmp_path / "artifacts"
    run_dir, status = rx.run(cfg, artifacts_root=artifacts, run_id="ar25_recorded", game="ar25")
    assert status == "completed", (run_dir / "stderr.log").read_text()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["action_budget"] == 3740 and manifest["network_attempts"] == 0
    assert manifest["model_calls_allowed"] == 60 and manifest["model_calls"] == 1
    assert manifest["model_identifier"] == "claude-fable-5-1"
    resolved = yaml.safe_load((run_dir / "resolved_config.yaml").read_text())
    assert resolved["runner_params"]["game"] == "ar25"
    assert resolved["budgets"]["action_budget"] == 3740
    top = json.loads((run_dir / "results.json").read_text())
    assert top["config_file_sha256"] == hashlib.sha256(cfg.read_bytes()).hexdigest()
    results = top["results"]
    assert results["game_id"] == "ar25-0c556536" and results["stem"] == "ar25"
    assert results["operation_mode"] == "OFFLINE" and results["network_guard"] == "NetworkGuard"
    assert results["official_baseline_actions"] == [32, 50, 75, 37, 89, 159, 233, 73]
    assert results["model_calls"] == 1 and results["hypotheses_proposed"] == 1
    assert results["model_unavailable_reason"] and results["stop_reason"] in (
        la.STOP_MODEL_BUDGET_EXHAUSTED,
        la.STOP_LEVEL_BUDGET_EXHAUSTED,
    )
    assert results["exploration_actions"] >= 4 and results["resumptions"] == 0
    assert "wallclock" not in json.dumps(results)
    assert results["backtest_module_sha256"] == bt.backtest_module_sha256()

    rows = _jsonl(run_dir / "transitions.jsonl")
    assert len(rows) == results["actions_total"]
    replay = ai.replay_actions(
        ENV_DIR, "ar25-0c556536", 12345, [ai.ActionRecord.from_mapping(r) for r in rows]
    )
    assert replay.succeeded and replay.final_digest == results["final_frame_sha256"]
    assert [r["frame_sha256"] for r in rows][-1] == results["final_frame_sha256"]
    rebuilt = la.accounting_from_log(
        results["official_baseline_actions"], 5, rows, game_id="ar25-0c556536"
    )
    rebuilt.stop(results["stop_reason"])
    assert rebuilt.to_dict() == json.loads((run_dir / "level_accounting.json").read_text())

    hyps = _jsonl(run_dir / "hypotheses.jsonl")
    assert len(hyps) == 1 and hyps[0]["hypothesis_id"] == "h001"
    assert (run_dir / "world_models" / "h001.py").read_text() == mc.extract_program_source(
        f"```python\n{IDENTITY_PROGRAM}\n```"
    )
    calls = _jsonl(run_dir / "model_calls.jsonl")
    assert len(calls) == 1 and calls[0]["purpose"] == "induce"
    assert (run_dir / "model_calls" / "1.prompt.txt").exists()
    assert (run_dir / "model_calls" / "1.response.json").exists()
    metrics = (run_dir / "metrics.csv").read_text()
    assert "level_1_rhae_level_score" in metrics and "level_8_budget" in metrics
    assert "wallclock" not in metrics

    prereg, _, _ = vr.load_preregistration("G3", ROOT)
    completeness = vr.check_run_completeness(artifacts / "E300_ref", tuple(rwm.EXTRA_ARTIFACTS))
    assert completeness.passed, completeness.observed
    sums = vr.check_sha256sums(prereg, artifacts / "E300_ref")
    assert sums.passed, sums.observed
    offline = vr.check_offline_run(prereg, artifacts / "E300_ref", model_allowed=60)
    assert offline.passed, offline.observed

    # A refused preflight (responses file missing) leaves no run directory behind.
    bad = _toolkit_config(
        tmp_path, "bad", {"kind": "recorded", "responses_file": str(tmp_path / "nope.json")}, 60
    )
    with pytest.raises(RunPreflightError, match="does not exist"):
        rx.run(bad, artifacts_root=tmp_path / "artifacts_bad", game="ar25")
    assert not (tmp_path / "artifacts_bad").exists()

    # The run set manifest builder over this root: one graded run, set 1 incomplete.
    builder = _script("build_e300_run_set")
    (artifacts / "E300_ref" / "20260904T000000Z_seed12345_deadbeef").mkdir()
    doc = builder.build(
        artifacts / "E300_ref",
        stems_required=builder.stems_from_cache_manifest(),
        preflight=builder.preflight_games(),
    )
    assert doc["runs_total"] == 2 and doc["preflight_games"] == ["cd82", "s5i5", "wa30"]
    by_id = {r["run_id"]: r for r in doc["runs"]}
    good = by_id["ar25_recorded"]
    assert good["role"] == "graded" and good["set_index"] == 1 and good["stem"] == "ar25"
    assert (
        good["sha256sums_sha256"]
        == hashlib.sha256((run_dir / "SHA256SUMS").read_bytes()).hexdigest()
    )
    empty = by_id["20260904T000000Z_seed12345_deadbeef"]
    assert empty["role"] == "failed" and empty["stem"] is None and empty["sealed"] is False
    assert doc["sets"]["1"]["complete"] is False and "ar25" in doc["sets"]["1"]["graded_stems"]
    assert doc["sets"]["1"]["missing_stems"] == sorted(set(doc["stems_required"]) - {"ar25"})


@needs_toolkit_cache
def test_entry_point_model_free_run_reaches_the_level_budget(tmp_path: Path) -> None:
    rx = _script("run_experiment")
    cfg = _toolkit_config(tmp_path, "free", {"kind": "none"}, 0)
    run_dir, status = rx.run(
        cfg, artifacts_root=tmp_path / "artifacts", run_id="ar25_free", game="ar25"
    )
    assert status == "completed", (run_dir / "stderr.log").read_text()
    results = json.loads((run_dir / "results.json").read_text())["results"]
    assert results["stop_reason"] == la.STOP_LEVEL_BUDGET_EXHAUSTED
    assert results["model_calls"] == 0 and results["hypotheses_proposed"] == 0
    assert results["levels"][0]["actions_attributed"] == results["levels"][0]["budget"] == 160
    assert results["actions_total"] == 160 and results["over_budget_levels"] == []
    assert (run_dir / "world_models" / "EMPTY").exists()


def test_run_set_roles_never_label_a_completed_run_failed() -> None:
    builder = _script("build_e300_run_set")
    runs = [
        {"run_id": "b_second", "stem": "ar25", "completion_status": "completed", "sealed": True},
        {"run_id": "a_first", "stem": "ar25", "completion_status": "completed", "sealed": True},
        {"run_id": "c_fail", "stem": "ar25", "completion_status": "failed", "sealed": True},
        {"run_id": "d_pre", "stem": "cd82", "completion_status": "completed", "sealed": True},
        {"run_id": "e_unsealed", "stem": "cd82", "completion_status": "completed", "sealed": False},
    ]
    builder.assign_sets_and_roles(runs, ["cd82"])
    by_id = {r["run_id"]: r for r in runs}
    assert (by_id["a_first"]["set_index"], by_id["a_first"]["role"]) == (1, "graded")
    assert (by_id["b_second"]["set_index"], by_id["b_second"]["role"]) == (2, "graded")
    assert (by_id["c_fail"]["set_index"], by_id["c_fail"]["role"]) == (3, "failed")
    assert (by_id["d_pre"]["set_index"], by_id["d_pre"]["role"]) == (1, "preflight_graded")
    assert by_id["e_unsealed"]["role"] == "failed"
    assert all(
        r["role"] != "failed" for r in runs if r["completion_status"] == "completed" and r["sealed"]
    )
    sets = builder.summarize_sets(runs, ["ar25", "cd82"])
    assert sets["1"]["complete"] is True and sets["2"]["complete"] is False
    assert sets["2"]["missing_stems"] == ["cd82"] and sets["3"]["failed_run_ids"] == ["c_fail"]
