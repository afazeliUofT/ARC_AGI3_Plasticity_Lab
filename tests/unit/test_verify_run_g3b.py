"""Unit tests for the G3 graded-set evaluators and the G3b successor overlay in
scripts/verify_run.py (G3.6b step 15).

Every number a test compares against is read from the real ``preregistration/G3.yaml`` and
``preregistration/G3b.yaml`` through the verifier's own ``threshold()``. The checks run on a
synthetic graded set built at full scale (one run per cached game, 25 runs) whose transitions
are REAL: three actions stepped on each cached game in this process, so the replay identity
check has something true to verify. Everything else in a run (one model call with its prompt
and response files, one certified hypothesis, one found plan executed by two of the three
actions, the accounting rebuilt from the transitions through the project's own
``level_accounting``) is consistent by construction. Each check then gets failing cases
produced by mutating a private copy of the world.
"""

from __future__ import annotations

import copy
import csv
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

from arc_plasticity.core.guards import NetworkGuard
from arc_plasticity.environments import arc_interface as ai
from arc_plasticity.evaluation import level_accounting as la

ROOT = Path(__file__).resolve().parents[2]
ENV_DIR = ROOT / "environment_files"
CACHE_MANIFEST = ROOT / "experiments" / "environment_cache_manifest.json"

pytestmark = pytest.mark.skipif(
    not CACHE_MANIFEST.exists() or not ENV_DIR.exists(), reason="the environment cache is absent"
)


def _load_module(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


vr = _load_module("verify_run")
builder = _load_module("build_e300_run_set")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ------------------------------------------------------------------ pre-registrations


@pytest.fixture(scope="module")
def g3() -> dict[str, Any]:
    data: dict[str, Any]
    data, _, _ = vr.load_preregistration("G3", ROOT)
    return data


@pytest.fixture(scope="module")
def g3b() -> dict[str, Any]:
    loaded = vr.load_g3_successor(ROOT)
    assert loaded is not None, "preregistration/G3b.yaml is absent"
    return loaded[0]


@pytest.fixture(scope="module")
def view(g3: dict[str, Any], g3b: dict[str, Any]) -> dict[str, Any]:
    merged, _ = vr.apply_g3_overlay(g3, g3b)
    return merged


@pytest.fixture(scope="module")
def e310_root(g3: dict[str, Any]) -> Path:
    return ROOT / str(g3["verification"]["secondary_artifacts_root"])


# ------------------------------------------------------------------ synthetic graded set


def _cache_games() -> list[tuple[str, str]]:
    doc = json.loads(CACHE_MANIFEST.read_text())
    return sorted((str(g["stem"]), str(g["game_id"])) for g in doc["games"])


def _e310_backtest_digest(e310_root: Path) -> str:
    for run in sorted(e310_root.iterdir()):
        if (run / "results.json").is_file():
            return str(
                json.loads((run / "results.json").read_text())["results"]["backtest_module_sha256"]
            )
    raise AssertionError("no E310 run")


def _step_real(game_id: str, seed: int, actions: list[ai.ActionRecord]) -> list[dict[str, Any]]:
    """Step a cached game for real and return the transition records the runner would write."""
    with NetworkGuard(0):
        arcade = ai.open_offline_arcade(ENV_DIR)
        env = ai.make_environment(arcade, game_id, seed)
        reset = env.reset()
        assert reset is not None
        current = ai.summarize_response(reset)
        out: list[dict[str, Any]] = []
        for i, record in enumerate(actions, start=1):
            pre = current.digest()
            nxt = ai.step_environment(env, record)
            assert nxt is not None, (game_id, i)
            current = nxt
            out.append(
                {
                    "game_index": 0,
                    "game_id": game_id,
                    "step_index": i,
                    "action": record.action,
                    "data": dict(record.data),
                    "pre_frame_sha256": pre,
                    "frame_sha256": current.digest(),
                    "observation_sha256": current.digest(),
                    "state": current.state,
                    "levels_completed": current.levels_completed,
                    "win_levels": current.win_levels,
                    "available_actions": list(current.available_actions),
                    "source": "exploration",
                    "hypothesis_id": None,
                    "plan_index": None,
                    "predicted_observation_sha256": None,
                    "prediction_matched": None,
                    "prediction_note": None,
                }
            )
    return out


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))


def _seal(run: Path) -> None:
    sums = run / "SHA256SUMS"
    lines = []
    for p in sorted(run.rglob("*")):
        if p.is_file() and p != sums:
            lines.append(f"{_sha(p)}  {p.relative_to(run).as_posix()}")
    sums.write_text("\n".join(lines) + "\n")


def _write_reports(
    run: Path,
    view: dict[str, Any],
    g3b: dict[str, Any],
    *,
    game_id: str,
    stem: str,
    baselines: list[int],
    transitions: list[dict[str, Any]],
    stop_reason: str,
    plans: list[dict[str, Any]],
    executed_plan_indices: set[int],
    hyps: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    backtest_digest: str,
    wallclock_seconds: float,
) -> None:
    """results.json, level_accounting.json, rhae.json, metrics.csv, environment_results.csv
    and manifest.json, all derived from the transitions through the project's accounting."""
    multiplier = int(vr.threshold(view, "action_budget_multiplier"))
    acc = la.accounting_from_log(baselines, multiplier, transitions, game_id=game_id)
    acc.stop(stop_reason)
    accounting = acc.to_dict()
    (run / "level_accounting.json").write_text(json.dumps(accounting, indent=2, sort_keys=True))
    level_scores = acc.rhae_level_scores()
    (run / "rhae.json").write_text(
        json.dumps(
            {
                "game_id": game_id,
                "stem": stem,
                "canonical_scoring_baseline": "official metadata.json baseline_actions",
                "official_baseline_actions": list(baselines),
                "levels": [
                    {**r.to_dict(), "rhae_level_score": s}
                    for r, s in zip(acc.level_records(), level_scores, strict=True)
                ],
                "rhae_environment_score": acc.rhae_environment_score(),
                "levels_completed": acc.levels_completed,
                "win_levels": acc.win_levels,
                "stop_reason": stop_reason,
            },
            indent=2,
            sort_keys=True,
        )
    )
    tokens: dict[str, int] = {}
    for call in calls:
        for kind, n in call["tokens_by_kind"].items():
            tokens[kind] = tokens.get(kind, 0) + int(n)
    model_wall = sum(float(c["wallclock_seconds"]) for c in calls)
    certified_ids = {
        h["hypothesis_id"] for h in hyps if h["event"] == "proposed" and h["certified"]
    }
    results = {
        "operation_mode": "OFFLINE",
        "network_guard": "NetworkGuard",
        "game_id": game_id,
        "stem": stem,
        "seed": int(view["experiment"]["seed"]),
        "win_levels": acc.win_levels,
        "levels_completed": acc.levels_completed,
        "final_state": transitions[-1]["state"],
        "final_frame_sha256": transitions[-1]["frame_sha256"],
        "stop_reason": stop_reason,
        "actions_total": acc.actions_total,
        "exploration_actions": sum(1 for t in transitions if t["source"] == "exploration"),
        "plan_actions": sum(1 for t in transitions if t["source"] == "plan"),
        "levels": accounting["levels"],
        "official_baseline_actions": list(baselines),
        "action_budget_multiplier": multiplier,
        "action_budget_total": acc.action_budget_total,
        "over_budget_levels": accounting["over_budget_levels"],
        "rhae_environment_score": acc.rhae_environment_score(),
        "rhae_level_scores": level_scores,
        "model_calls": len(calls),
        "model_calls_per_game_max": int(vr.threshold(view, "model_calls_per_game_max")),
        "tokens_by_kind": tokens,
        "tokens_total": sum(tokens.values()),
        "tokens_per_game_max": int(vr.threshold(view, "tokens_per_game_max")),
        "model_wallclock_seconds_total": model_wall,
        "model_identifier": str(vr.threshold(view, "model_identifier")),
        "model_effort": str(vr.threshold(view, "model_effort")),
        "model_budget_binding": None,
        "model_budget_consumed": False,
        "hypotheses_proposed": sum(1 for h in hyps if h["event"] == "proposed"),
        "hypotheses_certified": len(certified_ids),
        "plans_searched": len(plans),
        "plans_executed": len(executed_plan_indices),
        "prediction_mismatches": 0,
        "resumptions": 0,
        "backtest_module_sha256": backtest_digest,
        "prompt_hash": str(vr.threshold(g3b, "prompt_hash")),
        "planner": {
            key: vr.threshold(g3b, name) for key, name in vr.G3_SUCCESSOR_PLANNER_THRESHOLDS
        },
        "spend_control": {
            "calls_per_run_max": int(vr.threshold(g3b, "calls_per_run_max")),
            "model_wallclock_per_run_seconds": float(
                vr.threshold(g3b, "model_wallclock_per_run_seconds")
            ),
            "concurrency": 1,
        },
        "simulation_budget": {
            "max_steps": int(vr.threshold(g3b, "simulation_steps_per_game_max")),
            "used": 1000,
        },
        "simulation_steps_per_game_max": int(vr.threshold(g3b, "simulation_steps_per_game_max")),
    }
    top = {
        "experiment_id": str(vr.threshold(g3b, "experiment_id")),
        "run_id": run.name,
        "seed": results["seed"],
        "created_utc": "2026-09-12T00:00:00Z",
        "config_file_sha256": str(vr.threshold(g3b, "graded_config_sha256")),
        "config_hash": "x",
        "completion_status": "completed",
        "wallclock_seconds": wallclock_seconds,
        "results": results,
        "extra": {},
    }
    (run / "results.json").write_text(json.dumps(top, indent=2, sort_keys=True))
    with (run / "metrics.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value"])
        w.writerow(["rhae_environment_score", acc.rhae_environment_score()])
        w.writerow(["levels_completed", acc.levels_completed])
    with (run / "environment_results.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["environment", "level", "actions_attributed", "completed"])
        for r in acc.level_records():
            w.writerow([game_id, r.level, r.actions_attributed, int(r.completed)])
    manifest = {k: "x" for k in vr.REQUIRED_MANIFEST_KEYS}
    manifest.update(
        {
            "experiment_id": top["experiment_id"],
            "run_id": run.name,
            "timestamp_utc": "2026-09-12T00:00:00Z",
            "seed": results["seed"],
            "completion_status": "completed",
            "model_identifier": results["model_identifier"],
            "prompt_hash": results["prompt_hash"],
            "action_budget": acc.action_budget_total,
            "simulation_budget": results["simulation_budget"]["max_steps"],
            "token_budget": results["tokens_per_game_max"],
            "persistent_state_size_cap": 0,
            "wallclock_limit_seconds": vr.threshold(view, "wallclock_per_invocation_seconds"),
            "wallclock_seconds": wallclock_seconds,
            "network_calls_allowed": int(vr.threshold(view, "network_calls_allowed")),
            "network_attempts": 0,
            "model_calls_allowed": results["model_calls_per_game_max"],
            "model_calls": len(calls),
            "git_dirty": False,
        }
    )
    (run / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))


def _make_run(
    root: Path,
    view: dict[str, Any],
    g3b: dict[str, Any],
    *,
    run_id: str,
    stem: str,
    game_id: str,
    backtest_digest: str,
) -> Path:
    run = root / run_id
    (run / "model_calls").mkdir(parents=True)
    (run / "world_models").mkdir()
    baselines = la.load_official_baselines(ENV_DIR, game_id)
    seed = int(view["experiment"]["seed"])
    actions = [ai.ActionRecord(1), ai.ActionRecord(2), ai.ActionRecord(3)]
    transitions = _step_real(game_id, seed, actions)
    # One model call after the first action, one certified hypothesis, one found plan of two
    # actions executed as steps 2 and 3 with a recorded prediction before each.
    prompt = f"history of {game_id} after 1 action\n"
    response = json.dumps({"result": "```python\n# GOAL: x\ndef predict(h, a): ...\n```"})
    (run / "model_calls" / "1.prompt.txt").write_text(prompt)
    (run / "model_calls" / "1.response.json").write_text(response)
    (run / "world_models" / "h001.py").write_text("# GOAL: x\ndef predict(h, a): ...\n")
    calls = [
        {
            "call_index": 1,
            "purpose": "induce",
            "client_kind": "headless_cli",
            "model_identifier_sent": str(vr.threshold(view, "model_identifier")),
            "model_identifier_reported": None,
            "effort": str(vr.threshold(view, "model_effort")),
            "cwd": "/tmp/arc_model_call_synthetic",
            "tools_disabled": True,
            "prompt_path": "model_calls/1.prompt.txt",
            "prompt_sha256": _sha_text(prompt),
            "response_path": "model_calls/1.response.json",
            "response_sha256": _sha_text(response),
            "tokens_by_kind": {"cache_creation": 1000, "cache_read": 0, "input": 2, "output": 500},
            "wallclock_seconds": 12.5,
            "exit_code": 0,
            "history_length_at_call": 1,
            "program_returned": True,
        }
    ]
    backtests = [
        {
            "hypothesis_id": "h001",
            "model_call_index": 1,
            "certified": True,
            "mismatches": 0,
            "history_length": 1,
            "history_length_checked": 1,
            "failure_kind": None,
            "first_mismatch_index": None,
            "backtest_module_sha256": backtest_digest,
            "interface_sha256": "y",
            "source_sha256": _sha(run / "world_models" / "h001.py"),
        }
    ]
    hyps = [
        {
            "event": "proposed",
            "hypothesis_id": "h001",
            "certified": True,
            "mismatches": 0,
            "history_length": 1,
            "history_length_checked": 1,
            "failure_kind": None,
            "model_call_index": 1,
            "parent_hypothesis_id": None,
            "purpose": "induce",
            "source_path": "world_models/h001.py",
            "backtest_module_sha256": backtest_digest,
        }
    ]
    plans = [
        {
            "plan_index": 0,
            "hypothesis_id": "h001",
            "game_id": game_id,
            "outcome": "found",
            "certification_history_length": 1,
            "planned_from_history_length": 1,
            "step_index_at_plan": 1,
            "actions": [{"action": 2, "data": {}}, {"action": 3, "data": {}}],
            "nodes_expanded": 3,
            "steps_simulated": 9,
            "max_depth_reached": 2,
            "target_levels_completed": 1,
            "predicted_levels_completed_max": 1,
        }
    ]
    for t in transitions[1:]:
        t["source"] = "plan"
        t["hypothesis_id"] = "h001"
        t["plan_index"] = 0
        t["predicted_observation_sha256"] = t["frame_sha256"]
        t["prediction_matched"] = True
    _write_jsonl(run / "transitions.jsonl", transitions)
    _write_jsonl(run / "model_calls.jsonl", calls)
    _write_jsonl(run / "backtests.jsonl", backtests)
    _write_jsonl(run / "hypotheses.jsonl", hyps)
    _write_jsonl(run / "plans.jsonl", plans)
    (run / "memory_operations.jsonl").write_text("")
    (run / "stdout.log").write_text("synthetic\n")
    (run / "stderr.log").write_text("")
    (run / "git_state.txt").write_text("commit x\ndirty false\n")
    (run / "environment_info.json").write_text(json.dumps({"game_id": game_id}))
    resolved = {
        "experiment_id": str(vr.threshold(g3b, "experiment_id")),
        "wallclock_limit_seconds": vr.threshold(view, "wallclock_per_invocation_seconds"),
        "runner_params": {
            "game": stem,
            "wallclock_reserve_seconds": 120,
            "model_client": {"kind": "headless_cli", "call_wallclock_seconds": 900},
        },
    }
    (run / "resolved_config.yaml").write_text(yaml.safe_dump(resolved))
    limit = float(vr.threshold(view, "wallclock_per_invocation_seconds"))
    _write_reports(
        run,
        view,
        g3b,
        game_id=game_id,
        stem=stem,
        baselines=baselines,
        transitions=transitions,
        stop_reason=la.STOP_WALLCLOCK,
        plans=plans,
        executed_plan_indices={0},
        hyps=hyps,
        calls=calls,
        backtest_digest=backtest_digest,
        wallclock_seconds=limit - 50.0,
    )
    _seal(run)
    return run


@pytest.fixture(scope="module")
def world(
    tmp_path_factory: pytest.TempPathFactory,
    view: dict[str, Any],
    g3b: dict[str, Any],
    e310_root: Path,
) -> Path:
    """A complete synthetic graded set: one sealed run per cached game."""
    root = tmp_path_factory.mktemp("g3b_world") / str(vr.threshold(g3b, "experiment_id"))
    root.mkdir()
    digest = _e310_backtest_digest(e310_root)
    for i, (stem, game_id) in enumerate(_cache_games()):
        _make_run(
            root,
            view,
            g3b,
            run_id=f"20260912T{i:02d}0000Z_seed12345_{stem}",
            stem=stem,
            game_id=game_id,
            backtest_digest=digest,
        )
    return root


def _experiment(g3b: dict[str, Any], root: Path, manifest: Path) -> Any:
    exp = g3b["graded_experiment"]
    return vr.GradedExperiment(
        experiment_id=str(exp["experiment_id"]),
        artifacts_root=root,
        run_set_manifest=manifest,
        config_path=ROOT / str(exp["config"]),
        preflight_stems=(),
        roles=(vr.ROLE_GRADED, vr.ROLE_FAILED),
    )


def _write_run_set(root: Path, manifest: Path, experiment_id: str) -> None:
    doc = builder.build(
        root,
        stems_required=builder.stems_from_cache_manifest(),
        preflight=[],
        experiment_id=experiment_id,
    )
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")


@pytest.fixture()
def copied(world: Path, tmp_path: Path, g3b: dict[str, Any]) -> tuple[Path, Any]:
    """A private copy of the world with its run set manifest, for mutation."""
    root = tmp_path / world.name
    shutil.copytree(world, root)
    manifest = tmp_path / "experiments" / f"{world.name}_run_set.json"
    _write_run_set(root, manifest, str(vr.threshold(g3b, "experiment_id")))
    return root, _experiment(g3b, root, manifest)


def _edit_json(path: Path, edit: Any) -> None:
    doc = json.loads(path.read_text())
    edit(doc)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True))


def _edit_jsonl(path: Path, edit: Any) -> None:
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    edit(records)
    _write_jsonl(path, records)


def _all_checks(
    view: dict[str, Any], g3b: dict[str, Any], experiment: Any, e310_root: Path
) -> dict[str, Any]:
    graded = vr.g3_graded_set(view, experiment, ROOT)
    calls_max = int(vr.threshold(view, "model_calls_per_game_max"))
    checks = [
        vr.check_run_set_manifest(view, g3b, experiment, graded, ROOT),
        vr.check_run_completeness(
            experiment.artifacts_root, vr._g3_extra_artifacts(view), runs=graded.runs
        ),
        vr.check_sha256sums(view, experiment.artifacts_root, runs=graded.runs),
        vr.check_offline_run(
            view, experiment.artifacts_root, model_allowed=calls_max, runs=graded.runs
        ),
        vr.check_official_baselines_used(view, experiment, graded, ROOT),
        vr.check_action_budget_enforced(view, experiment, graded),
        vr.check_replay_final_frame_identity_e300(view, experiment, graded, ROOT),
        vr.check_rhae_recomputed(view, experiment, graded),
        vr.check_model_call_accounting(view, experiment, graded, ROOT),
        vr.check_verification_active(view, experiment, graded, e310_root),
        vr.check_preflight_recorded(view, experiment, graded, ROOT),
        vr.check_graded_config_identity(g3b, experiment, graded, ROOT),
        vr.check_graded_config_derivation(g3b, experiment, ROOT),
        vr.check_spend_caps_respected(view, g3b, experiment, graded),
        vr.check_planner_caps_recorded(g3b, graded),
        vr.check_no_resumption(g3b, graded),
        vr.check_diagnostic_runs_untouched(g3b, experiment, ROOT),
        vr.check_stop_reason_semantics(view, g3b, experiment, graded),
    ]
    return {c.name: c for c in checks}


# ------------------------------------------------------------------ overlay


def test_overlay_replaces_exactly_the_listed_keys(g3: dict[str, Any], g3b: dict[str, Any]) -> None:
    view, overrides = vr.apply_g3_overlay(g3, g3b)
    keys = vr.g3_overriding_keys(g3b)
    assert set(overrides) == set(keys) and keys
    for key in keys:
        assert view["thresholds"][key] == vr.threshold(g3b, key) == overrides[key]["successor"]
        assert overrides[key]["g3"] == vr.threshold(g3, key)
    untouched = {k: v for k, v in g3["thresholds"].items() if k not in keys}
    assert {k: v for k, v in view["thresholds"].items() if k not in keys} == untouched
    # the pass criteria are inherited unchanged and restated identically
    for key in (
        "rhae_total_min",
        "backtest_rejection_fraction_min",
        "backtest_correct_model_acceptance_min",
    ):
        assert vr.threshold(view, key) == vr.threshold(g3b, key) == vr.threshold(g3, key)
    assert g3 is not view and "thresholds_overriding_g3" not in g3


def test_overlay_rejects_a_key_g3_lacks_or_the_successor_does_not_fix(
    g3: dict[str, Any], g3b: dict[str, Any]
) -> None:
    bad = copy.deepcopy(g3b)
    bad["thresholds_overriding_g3"].append("not_a_g3_threshold (x -> y)")
    with pytest.raises(vr.PreregistrationError, match="which G3 lacks"):
        vr.apply_g3_overlay(g3, bad)
    unfixed = copy.deepcopy(g3b)
    del unfixed["thresholds"][vr.g3_overriding_keys(g3b)[0]]
    with pytest.raises(vr.PreregistrationError, match="lacks thresholds"):
        vr.apply_g3_overlay(g3, unfixed)
    with pytest.raises(vr.PreregistrationError, match="thresholds_overriding_g3"):
        vr.apply_g3_overlay(g3, {**g3b, "thresholds_overriding_g3": []})


def test_default_artifacts_root_is_the_successor_graded_root(
    g3: dict[str, Any], g3b: dict[str, Any]
) -> None:
    assert vr.default_artifacts_root("G3", g3, ROOT) == ROOT / str(
        g3b["graded_experiment"]["artifacts_root"]
    )
    assert vr.default_artifacts_root("G1", vr.load_preregistration("G1", ROOT)[0], ROOT).name


def test_successor_overlay_check_binds_the_g3_digest(
    g3: dict[str, Any], g3b: dict[str, Any]
) -> None:
    _, g3_path, g3_sha = vr.load_preregistration("G3", ROOT)
    loaded = vr.load_g3_successor(ROOT)
    assert loaded is not None
    _, path, sha = loaded
    _, overrides = vr.apply_g3_overlay(g3, g3b)
    ok = vr.check_successor_overlay(g3_path, g3_sha, g3b, path, sha, overrides)
    assert (
        ok.passed
        and ok.observed["g3"]["sha256"] == g3_sha
        and ok.observed["successor"]["sha256"] == sha
    )
    bad = vr.check_successor_overlay(g3_path, "0" * 64, g3b, path, sha, overrides)
    assert not bad.passed


# ------------------------------------------------------------------ the world passes


def test_world_passes_every_check_except_the_primary_metric(
    view: dict[str, Any], g3b: dict[str, Any], copied: tuple[Path, Any], e310_root: Path
) -> None:
    _root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    assert graded.complete and len(graded.runs) == int(vr.threshold(view, "graded_games_required"))
    checks = _all_checks(view, g3b, experiment, e310_root)
    for name, check in checks.items():
        if name == "rhae_recomputed":
            continue
        assert check.passed, (name, check.observed.get("problems"))
    rhae_check = checks["rhae_recomputed"]
    assert not rhae_check.passed
    assert rhae_check.observed["set_complete"] and rhae_check.observed["runs_scored"] == len(
        graded.runs
    )
    assert rhae_check.observed["rhae_total_mean"] == 0.0  # three real actions complete nothing
    assert len(rhae_check.observed["problems"]) == 1 and "<" in rhae_check.observed["problems"][0]
    replay = checks["replay_final_frame_identity"]
    assert replay.observed["identity"] == 1.0 and replay.observed["network_attempts"] == 0
    assert (
        checks["verification_active"].observed["runs"][graded.runs[0].name]["plans_executed"] == 1
    )
    assert checks["stop_reason_semantics"].observed["stop_reason_counts"] == {
        la.STOP_WALLCLOCK: len(graded.runs)
    }
    assert checks["graded_config_derivation"].observed["line_changes"] == int(
        vr.threshold(g3b, "graded_config_line_changes_from_e303")
    )


def _complete_every_level(
    run: Path, view: dict[str, Any], g3b: dict[str, Any], e310_root: Path
) -> None:
    """Rewrite a run so every level completes in exactly its baseline (score 100 per level)."""
    results = json.loads((run / "results.json").read_text())["results"]
    baselines = list(results["official_baseline_actions"])
    log: list[dict[str, Any]] = []
    for done, h in enumerate(baselines, start=1):
        for _ in range(h):
            log.append({"action": 1, "levels_completed": done - 1, "state": "NOT_FINISHED"})
        log[-1]["levels_completed"] = done
        log[-1]["state"] = "WIN" if done == len(baselines) else "NOT_FINISHED"
    transitions = [
        {
            **json.loads((run / "transitions.jsonl").read_text().splitlines()[0]),
            "step_index": i,
            **entry,
            "frame_sha256": f"{i:064x}",
            "source": "exploration",
            "hypothesis_id": None,
            "plan_index": None,
            "predicted_observation_sha256": None,
        }
        for i, entry in enumerate(log, start=1)
    ]
    _write_jsonl(run / "transitions.jsonl", transitions)
    calls = [json.loads(line) for line in (run / "model_calls.jsonl").read_text().splitlines()]
    hyps = [json.loads(line) for line in (run / "hypotheses.jsonl").read_text().splitlines()]
    _write_reports(
        run,
        view,
        g3b,
        game_id=results["game_id"],
        stem=results["stem"],
        baselines=baselines,
        transitions=transitions,
        stop_reason=la.STOP_WIN,
        plans=[json.loads(line) for line in (run / "plans.jsonl").read_text().splitlines()],
        executed_plan_indices=set(),
        hyps=hyps,
        calls=calls,
        backtest_digest=_e310_backtest_digest(e310_root),
        wallclock_seconds=100.0,
    )


def test_rhae_mean_passes_when_every_level_completes_at_baseline(
    view: dict[str, Any], g3b: dict[str, Any], copied: tuple[Path, Any], e310_root: Path
) -> None:
    root, experiment = copied
    for run in sorted(root.iterdir()):
        _complete_every_level(run, view, g3b, e310_root)
    graded = vr.g3_graded_set(view, experiment, ROOT)
    ok = vr.check_rhae_recomputed(view, experiment, graded)
    assert ok.passed, ok.observed["problems"]
    assert ok.observed["rhae_total_mean"] == pytest.approx(100.0)
    assert set(ok.observed["per_game"]) == set(graded.runs_by_stem)
    # the accounting rebuilt from the transitions still agrees, and a win is a graded stop
    assert vr.check_action_budget_enforced(view, experiment, graded).passed
    assert vr.check_stop_reason_semantics(view, g3b, experiment, graded).passed
    # a score edited in results.json is caught by the recomputation
    first = graded.runs[0]
    _edit_json(
        first / "results.json", lambda d: d["results"].__setitem__("rhae_environment_score", 115.0)
    )
    bad = vr.check_rhae_recomputed(view, experiment, graded)
    assert not bad.passed and any(
        "results.json rhae_environment_score" in p for p in bad.observed["problems"]
    )
    # an incomplete set never yields a graded mean
    shutil.rmtree(graded.runs[-1])
    partial = vr.check_rhae_recomputed(view, experiment, vr.g3_graded_set(view, experiment, ROOT))
    assert not partial.passed and not partial.observed["set_complete"]


# ------------------------------------------------------------------ one failing case per check


def test_wrong_config_digest_fails_identity(
    view: dict[str, Any], g3b: dict[str, Any], copied: tuple[Path, Any]
) -> None:
    _root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    target = graded.runs[3]
    _edit_json(target / "results.json", lambda d: d.__setitem__("config_file_sha256", "0" * 64))
    bad = vr.check_graded_config_identity(g3b, experiment, graded, ROOT)
    assert not bad.passed
    assert [p for p in bad.observed["problems"] if "config_file_sha256" in p] == [
        f"{target.name}: config_file_sha256 '{'0' * 64}' != {vr.threshold(g3b, 'graded_config_sha256')}"
    ]
    # the committed config itself must carry the locked digest
    other = vr.replace(experiment, config_path=ROOT / "configs" / "experiments" / "E303_ref.yaml")
    assert not vr.check_graded_config_identity(g3b, other, graded, ROOT).passed


def test_wrong_prompt_hash_fails_identity(
    view: dict[str, Any], g3b: dict[str, Any], copied: tuple[Path, Any]
) -> None:
    _root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    target = graded.runs[0]
    _edit_json(target / "manifest.json", lambda d: d.__setitem__("prompt_hash", "f" * 64))
    bad = vr.check_graded_config_identity(g3b, experiment, graded, ROOT)
    assert not bad.passed and any(
        p.startswith(f"{target.name}: prompt_hash") for p in bad.observed["problems"]
    )


def test_excluded_diagnostic_run_present_fails(
    view: dict[str, Any], g3b: dict[str, Any], copied: tuple[Path, Any]
) -> None:
    root, experiment = copied
    excluded = vr._excluded_diagnostic_runs(g3b)
    assert len(excluded) == int(vr.threshold(g3b, "diagnostic_runs_excluded"))
    _, _, run_id = excluded[0]
    shutil.copytree(min(root.iterdir()), root / run_id)
    untouched = vr.check_diagnostic_runs_untouched(g3b, experiment, ROOT)
    assert not untouched.passed and any(run_id in p for p in untouched.observed["problems"])
    graded = vr.g3_graded_set(view, experiment, ROOT)
    run_set = vr.check_run_set_manifest(view, g3b, experiment, graded, ROOT)
    assert not run_set.passed and run_set.observed["excluded_diagnostic_runs_present"] == [run_id]


def test_diagnostic_runs_untouched_passes_on_the_real_tree(g3b: dict[str, Any]) -> None:
    experiment = _experiment(
        g3b, ROOT / str(g3b["graded_experiment"]["artifacts_root"]), ROOT / "nonexistent.json"
    )
    ok = vr.check_diagnostic_runs_untouched(g3b, experiment, ROOT)
    assert ok.passed, ok.observed["problems"]
    assert len(ok.observed["runs"]) == int(vr.threshold(g3b, "diagnostic_runs_excluded"))


def test_run_set_manifest_is_recomputed_and_compared(
    view: dict[str, Any], g3b: dict[str, Any], copied: tuple[Path, Any]
) -> None:
    root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    ok = vr.check_run_set_manifest(view, g3b, experiment, graded, ROOT)
    assert ok.passed, ok.observed["problems"]
    assert ok.observed["listed_runs"] == ok.observed["run_directories"] == len(graded.runs)
    # relabelling a completed run failed is caught
    doc = json.loads(experiment.run_set_manifest.read_text())
    doc["runs"][0]["role"] = vr.ROLE_FAILED
    experiment.run_set_manifest.write_text(json.dumps(doc))
    bad = vr.check_run_set_manifest(view, g3b, experiment, graded, ROOT)
    assert not bad.passed and bad.observed["completed_labelled_failed"] == 1
    # an unlisted directory is caught
    _write_run_set(root, experiment.run_set_manifest, experiment.experiment_id)
    (root / "20260913T000000Z_seed12345_stray").mkdir()
    graded2 = vr.g3_graded_set(view, experiment, ROOT)
    unlisted = vr.check_run_set_manifest(view, g3b, experiment, graded2, ROOT)
    assert not unlisted.passed and unlisted.observed["unlisted"] == [
        "20260913T000000Z_seed12345_stray"
    ]
    assert graded2.complete  # a failed (empty) directory does not break set 1
    # a missing manifest is a failure, never a skip
    experiment.run_set_manifest.unlink()
    missing = vr.check_run_set_manifest(view, g3b, experiment, graded2, ROOT)
    assert not missing.passed and not missing.skipped


def test_replay_detects_a_tampered_action(view: dict[str, Any], copied: tuple[Path, Any]) -> None:
    _root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    target = graded.runs[1]

    def swap(records: list[dict[str, Any]]) -> None:
        records[0]["action"] = 4 if records[0]["action"] != 4 else 5

    _edit_jsonl(target / "transitions.jsonl", swap)
    bad = vr.check_replay_final_frame_identity_e300(view, experiment, graded, ROOT)
    # either the final digest diverges or the tampered action changes nothing on this game;
    # the check also requires the replayed digest to equal the recorded one for every run
    row = bad.observed["runs"][target.name]
    if bad.passed:
        pytest.skip(f"{target.name}: the substituted action produced the same final frame")
    assert target.name in bad.observed["divergent"] and row["identical"] is False


def test_action_budget_detects_tampered_accounting(
    view: dict[str, Any], copied: tuple[Path, Any]
) -> None:
    _root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    target = graded.runs[2]
    _edit_json(
        target / "level_accounting.json",
        lambda d: d["levels"][0].__setitem__(
            "actions_attributed", d["levels"][0]["actions_attributed"] + 1
        ),
    )
    bad = vr.check_action_budget_enforced(view, experiment, graded)
    assert not bad.passed and any("rebuilt from transitions" in p for p in bad.observed["problems"])
    over = copy.deepcopy(view)
    over["thresholds"]["action_budget_multiplier"] = 1
    assert not vr.check_action_budget_enforced(over, experiment, graded).passed


def test_model_call_accounting_detects_a_rewritten_prompt_and_a_cwd_inside_the_repo(
    view: dict[str, Any], copied: tuple[Path, Any]
) -> None:
    _root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    target = graded.runs[4]
    (target / "model_calls" / "1.prompt.txt").write_text("rewritten\n")
    bad = vr.check_model_call_accounting(view, experiment, graded, ROOT)
    assert not bad.passed and any("prompt sha256 mismatch" in p for p in bad.observed["problems"])
    _edit_jsonl(
        target / "model_calls.jsonl", lambda rs: rs[0].__setitem__("cwd", str(ROOT / "artifacts"))
    )
    inside = vr.check_model_call_accounting(view, experiment, graded, ROOT)
    assert any("inside the repository" in p for p in inside.observed["problems"])


def test_verification_active_detects_an_uncertified_plan_source(
    view: dict[str, Any], copied: tuple[Path, Any], e310_root: Path
) -> None:
    _root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    target = graded.runs[5]
    _edit_jsonl(target / "backtests.jsonl", lambda rs: rs[0].__setitem__("mismatches", 1))
    bad = vr.check_verification_active(view, experiment, graded, e310_root)
    assert not bad.passed
    assert any("does not follow from its record" in p for p in bad.observed["problems"])
    assert any("partial or has mismatches" in p for p in bad.observed["problems"])
    # a plan action citing a plan that was never found
    other = graded.runs[6]
    _edit_jsonl(other / "plans.jsonl", lambda rs: rs[0].__setitem__("outcome", "not_found"))
    bad2 = vr.check_verification_active(view, experiment, graded, e310_root)
    assert any(
        f"{other.name}: plan action at step 2 cites plan 0" in p for p in bad2.observed["problems"]
    )


def test_stop_reason_semantics_detects_inconsistent_stops(
    view: dict[str, Any], g3b: dict[str, Any], copied: tuple[Path, Any]
) -> None:
    _root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    a, b = graded.runs[7], graded.runs[8]
    _edit_json(a / "manifest.json", lambda d: d.__setitem__("wallclock_seconds", 10.0))
    _edit_json(
        b / "results.json",
        lambda d: d["results"].__setitem__("stop_reason", la.STOP_MODEL_BUDGET_EXHAUSTED),
    )
    bad = vr.check_stop_reason_semantics(view, g3b, experiment, graded)
    problems = bad.observed["problems"]
    assert any(p.startswith(f"{a.name}: wallclock stop") for p in problems)
    assert any("still certified" in p and p.startswith(b.name) for p in problems)
    assert any("without model_budget_consumed" in p and p.startswith(b.name) for p in problems)


def test_spend_planner_and_resumption_caps(
    view: dict[str, Any], g3b: dict[str, Any], copied: tuple[Path, Any]
) -> None:
    _root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    a, b, c = graded.runs[9], graded.runs[10], graded.runs[11]
    cap = float(vr.threshold(g3b, "model_wallclock_per_run_seconds"))
    _edit_json(
        a / "results.json",
        lambda d: d["results"].__setitem__("model_wallclock_seconds_total", cap + 901.0),
    )
    spend = vr.check_spend_caps_respected(view, g3b, experiment, graded)
    assert not spend.passed and any(
        p.startswith(f"{a.name}: model wall-clock") for p in spend.observed["problems"]
    )
    _edit_json(
        b / "results.json", lambda d: d["results"]["planner"].__setitem__("max_nodes", 20000)
    )
    planner = vr.check_planner_caps_recorded(g3b, graded)
    assert not planner.passed and [p.split(":")[0] for p in planner.observed["problems"]] == [
        b.name
    ]
    _edit_json(c / "results.json", lambda d: d["results"].__setitem__("resumptions", 1))
    resumed = vr.check_no_resumption(g3b, graded)
    assert not resumed.passed and [p.split(":")[0] for p in resumed.observed["problems"]] == [
        c.name
    ]


def test_official_baselines_detect_a_substituted_baseline(
    view: dict[str, Any], copied: tuple[Path, Any]
) -> None:
    _root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    target = graded.runs[12]
    _edit_json(
        target / "level_accounting.json", lambda d: d["official_baseline_actions"].__setitem__(0, 1)
    )
    bad = vr.check_official_baselines_used(view, experiment, graded, ROOT)
    assert not bad.passed and any(
        "!= metadata" in p and p.startswith(target.name) for p in bad.observed["problems"]
    )


def test_preflight_recorded_reads_the_real_budget_and_dates_the_graded_runs(
    view: dict[str, Any], copied: tuple[Path, Any]
) -> None:
    _root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    ok = vr.check_preflight_recorded(view, experiment, graded, ROOT)
    assert ok.passed, ok.observed["problems"]
    assert ok.observed["games_measured"] == int(vr.threshold(view, "preflight_games_measured"))
    assert ok.observed["projected_fraction_of_weekly_allowance"] is None
    assert ok.observed["no_denominator_escalations"]  # the ledger entry the rule requires
    target = graded.runs[0]
    _edit_json(
        target / "manifest.json", lambda d: d.__setitem__("timestamp_utc", "2026-09-01T00:00:00Z")
    )
    early = vr.check_preflight_recorded(
        view, experiment, vr.g3_graded_set(view, experiment, ROOT), ROOT
    )
    assert not early.passed and early.observed["graded_runs_not_after_preflight"] == [target.name]


def test_graded_config_derivation_on_the_committed_configs(g3b: dict[str, Any]) -> None:
    experiment = _experiment(g3b, ROOT / "artifacts" / "none", ROOT / "none.json")
    ok = vr.check_graded_config_derivation(g3b, experiment, ROOT)
    assert ok.passed, ok.observed["problems"]
    assert ok.observed["line_changes"] == int(
        vr.threshold(g3b, "graded_config_line_changes_from_e303")
    )
    assert set(ok.observed["differing_keys"]) == {path for path, _ in vr.G3_SUCCESSOR_CONFIG_LINES}
    wrong = copy.deepcopy(g3b)
    wrong["thresholds"]["planner_max_nodes"] = 1
    assert not vr.check_graded_config_derivation(wrong, experiment, ROOT).passed


# ------------------------------------------------------------------ thresholds are never defaulted


def test_every_graded_set_check_raises_without_its_thresholds(
    view: dict[str, Any], g3b: dict[str, Any], copied: tuple[Path, Any], e310_root: Path
) -> None:
    _root, experiment = copied
    graded = vr.g3_graded_set(view, experiment, ROOT)
    stripped = {**view, "thresholds": {}}
    stripped_b = {**g3b, "thresholds": {}}
    for call in (
        lambda: vr.g3_graded_set(stripped, experiment, ROOT),
        lambda: vr.check_run_set_manifest(stripped, g3b, experiment, graded, ROOT),
        lambda: vr.check_run_set_manifest(view, stripped_b, experiment, graded, ROOT),
        lambda: vr.check_official_baselines_used(stripped, experiment, graded, ROOT),
        lambda: vr.check_action_budget_enforced(stripped, experiment, graded),
        lambda: vr.check_replay_final_frame_identity_e300(stripped, experiment, graded, ROOT),
        lambda: vr.check_rhae_recomputed(stripped, experiment, graded),
        lambda: vr.check_model_call_accounting(stripped, experiment, graded, ROOT),
        lambda: vr.check_verification_active(stripped, experiment, graded, e310_root),
        lambda: vr.check_preflight_recorded(stripped, experiment, graded, ROOT),
        lambda: vr.check_graded_config_identity(stripped_b, experiment, graded, ROOT),
        lambda: vr.check_graded_config_derivation(stripped_b, experiment, ROOT),
        lambda: vr.check_spend_caps_respected(view, stripped_b, experiment, graded),
        lambda: vr.check_spend_caps_respected(stripped, g3b, experiment, graded),
        lambda: vr.check_planner_caps_recorded(stripped_b, graded),
        lambda: vr.check_no_resumption(stripped_b, graded),
        lambda: vr.check_diagnostic_runs_untouched(stripped_b, experiment, ROOT),
        lambda: vr.check_stop_reason_semantics(view, stripped_b, experiment, graded),
        lambda: vr.check_stop_reason_semantics(stripped, g3b, experiment, graded),
    ):
        with pytest.raises(vr.PreregistrationError):
            call()


def test_every_new_threshold_is_read_from_the_successor(g3b: dict[str, Any]) -> None:
    for key in (
        "graded_config_sha256",
        "graded_config_derived_from_sha256",
        "graded_config_line_changes_from_e303",
        "prompt_hash",
        "experiment_id",
        "model_wallclock_per_run_seconds",
        "calls_per_run_max",
        "planner_max_depth",
        "planner_max_nodes",
        "planner_click_grid_step",
        "planner_click_points",
        "simulation_steps_per_game_max",
        "wallclock_per_invocation_seconds",
        "job_wallclock_limit_seconds",
        "job_margin_over_runner_limit_seconds_min",
        "resumptions_used_max",
        "failed_reruns_per_game_max",
        "diagnostic_runs_excluded",
    ):
        assert vr.threshold(g3b, key) is not None


# ------------------------------------------------------------------ evaluate_g3 end to end


def test_evaluate_g3_with_the_successor_orders_the_checks_and_fails_on_an_empty_root(
    g3: dict[str, Any], g3b: dict[str, Any], tmp_path: Path
) -> None:
    checks = vr.evaluate_g3(g3, tmp_path / "E304_ref", ROOT, skip_tooling=True)
    names = [c.name for c in checks]
    assert names[:4] == [
        "successor_preregistration_overlay",
        "cache_manifest_locked",
        "run_set_manifest",
        "run_artifact_completeness",
    ]
    for name in (
        "run_artifact_completeness_e310",
        "sha256sums_verify",
        "sha256sums_verify_e310",
        "offline_run",
        "offline_run_e310",
        "official_baselines_used",
        "action_budget_enforced",
        "replay_final_frame_identity",
        "rhae_recomputed",
        "model_call_accounting",
        "verification_active",
        "backtest_rejection",
        "preflight_recorded",
        "graded_config_identity",
        "graded_config_derivation",
        "spend_caps_respected",
        "planner_caps_recorded",
        "no_resumption",
        "diagnostic_runs_untouched",
        "stop_reason_semantics",
        "exclusion_nesting_e310",
        "nondeterministic_fields_within_bounds",
        "determinism_identity_e310",
        "git_status_clean",
    ):
        assert name in names, name
    assert (
        names.index("verification_active")
        < names.index("backtest_rejection")
        < names.index("preflight_recorded")
    )
    assert (
        names.index("preflight_recorded")
        < names.index("graded_config_identity")
        < names.index("exclusion_nesting_e310")
    )
    by_name = {c.name: c for c in checks}
    overlay = by_name["successor_preregistration_overlay"]
    assert overlay.passed and set(overlay.observed["overrides"]) == set(vr.g3_overriding_keys(g3b))
    assert overlay.observed["successor"]["sha256"] == vr.load_g3_successor(ROOT)[2]  # type: ignore[index]
    for name in (
        "run_set_manifest",
        "run_artifact_completeness",
        "sha256sums_verify",
        "offline_run",
        "official_baselines_used",
        "action_budget_enforced",
        "replay_final_frame_identity",
        "rhae_recomputed",
        "model_call_accounting",
        "verification_active",
        "graded_config_identity",
        "spend_caps_respected",
        "planner_caps_recorded",
        "no_resumption",
        "stop_reason_semantics",
    ):
        assert not by_name[name].passed and not by_name[name].skipped, name
    # what does not depend on graded runs passes on the real tree
    for name in (
        "graded_config_derivation",
        "diagnostic_runs_untouched",
        "preflight_recorded",
        "cache_manifest_locked",
    ):
        assert by_name[name].passed, (name, by_name[name].observed)
    assert not vr.Report("G3", "x", "y", checks).passed
