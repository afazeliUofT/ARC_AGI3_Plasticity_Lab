"""Unit tests for scripts/g3_graded_set_accounting.py (G3.6b step 17, G3b cost_accounting)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "g3_graded_set_accounting.py"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("g3_graded_set_accounting", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _params(escalate_above: float = 60000.0, hard_bound: float = 90000.0) -> dict[str, Any]:
    games = ["ar25", "cd82", "s5i5", "wa30"]
    return {
        "gate": "G3b",
        "preregistration_path": "synthetic",
        "preregistration_sha256": "0" * 64,
        "experiment_id": "E999_ref",
        "graded_config_sha256": "c" * 64,
        "games": games,
        "games_required": len(games),
        "runs_per_game": 1,
        "set_model_seconds_escalate_above": escalate_above,
        "set_model_seconds_hard_bound": hard_bound,
        "model_wallclock_per_run_seconds": 3600.0,
        "cost_accounting_clause": "synthetic",
    }


def _make_run(
    root: Path,
    run_id: str,
    stem: str,
    model_seconds: float,
    experiment_id: str = "E999_ref",
    stop_reason: str = "model_budget_exhausted",
) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    results = {
        "experiment_id": experiment_id,
        "run_id": run_id,
        "seed": 12345,
        "completion_status": "completed",
        "config_file_sha256": "c" * 64,
        "wallclock_seconds": 250.5,
        "results": {
            "stem": stem,
            "game_id": f"{stem}-00000000",
            "prompt_hash": "p" * 64,
            "model_identifier": "claude-fable-5-1",
            "planner": {},
            "spend_control": {},
            "simulation_budget": {},
            "stop_reason": stop_reason,
            "model_budget_binding": None,
            "levels_completed": 1,
            "win_levels": 6,
            "levels": [{"level": 1, "completed": True, "completion_action_index": 27}],
            "rhae_environment_score": 4.76,
            "rhae_level_scores": [115.0],
            "actions_total": 27,
            "action_budget_total": 855,
            "exploration_actions": 7,
            "plan_actions": 20,
            "reset_actions": 0,
            "model_calls": 2,
            "calls_without_program": 0,
            "model_wallclock_seconds_total": model_seconds,
            "tokens_by_kind": {
                "cache_creation": 1_000_000,
                "cache_read": 4_000_000,
                "input": 100_000,
                "output": 200_000,
            },
            "tokens_total": 5_300_000,
            "plans_searched": 0,
            "plans_executed": 0,
            "hypotheses_proposed": 0,
            "hypotheses_certified": 0,
            "predictions_compared": 0,
            "prediction_mismatches": 0,
        },
    }
    (run_dir / "results.json").write_text(json.dumps(results), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"git_commit": "abcdef0", "git_dirty": False, "wallclock_limit_seconds": 9900}),
        encoding="utf-8",
    )
    (run_dir / "model_calls.jsonl").write_text(
        json.dumps({"call_index": 1, "wallclock_seconds": 5.0, "total_cost_usd": 1.5}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "SHA256SUMS").write_text("x\n", encoding="utf-8")
    return run_dir


def _make_budget(path: Path) -> dict[str, Any]:
    budget = {
        "schema_version": 1,
        "programme_end_date": "2027-03-31",
        "g3_preflight": {"games_measured": 3, "nested": {"keep": True}},
        "effort_policy": {"planning": "max"},
    }
    path.write_text(json.dumps(budget, indent=2) + "\n", encoding="utf-8")
    return budget


def _write_job_result(jobs_dir: Path, job_id: str, run_dir: Path, charged: int) -> None:
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True)
    rel = str(run_dir.relative_to(REPO_ROOT)) if run_dir.is_relative_to(REPO_ROOT) else str(run_dir)
    (job_dir / "result.json").write_text(
        json.dumps(
            {
                "id": job_id,
                "accepted": True,
                "returncode": 0,
                "timed_out": False,
                "wallclock_s": 3000,
                "model_seconds_charged": charged,
                "model_seconds_source": rel + "/results.json",
                "finished_utc": "2026-09-12T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


def test_load_parameters_reads_the_real_preregistration() -> None:
    module = _load_module()
    params = module.load_parameters(REPO_ROOT)
    assert params["gate"] == "G3b"
    assert params["experiment_id"] == "E304_ref"
    assert params["games_required"] == 25
    assert len(params["games"]) == 25
    assert params["games"] == sorted(params["games"])
    assert params["set_model_seconds_escalate_above"] < params["set_model_seconds_hard_bound"]
    assert len(params["preregistration_sha256"]) == 64
    assert "set_model_seconds_escalate_above" in params["cost_accounting_clause"]


def test_empty_root_gives_zero_totals_and_no_escalation(tmp_path: Path) -> None:
    module = _load_module()
    artifacts_root = tmp_path / "artifacts" / "E999_ref"  # does not exist
    section = module.account([], _params(), artifacts_root, "2026-09-12T00:00:00Z")
    assert section["cumulative"]["runs"] == 0
    assert section["cumulative"]["model_wallclock_seconds_total"] == 0
    assert section["projection_linear"] is None
    assert section["escalate"] is False
    assert section["hard_bound_exceeded"] is False
    assert section["set_complete"] is False
    assert section["games_remaining"] == ["ar25", "cd82", "s5i5", "wa30"]
    assert module.discover_runs(artifacts_root) == []


def test_one_run_record_totals_projection_and_budget_write(tmp_path: Path) -> None:
    module = _load_module()
    artifacts_root = tmp_path / "artifacts" / "E999_ref"
    jobs_dir = tmp_path / "jobs"
    run_dir = _make_run(artifacts_root, "20260912T000000Z_seed12345_aaaaaaaa", "cd82", 1234.56)
    _write_job_result(jobs_dir, "g37-cd82-1", run_dir, charged=1234)

    runs = [module.run_record(p, jobs_dir) for p in module.discover_runs(artifacts_root)]
    assert len(runs) == 1
    rec = runs[0]
    assert rec["game"] == "cd82"
    assert rec["stop_reason"] == "model_budget_exhausted"
    assert rec["model_wallclock_seconds_total"] == pytest.approx(1234.6)
    assert rec["model_calls"] == 2
    assert rec["supervisor_job_id"] == "g37-cd82-1"
    assert rec["supervisor_charged_seconds"] == 1234
    assert rec["tokens_by_kind"] == {
        "input": 100_000,
        "output": 200_000,
        "cache_read": 4_000_000,
        "cache_creation": 1_000_000,
    }
    assert rec["tokens_total"] == 5_300_000
    # 0.1M*10 + 0.2M*50 + 4M*0.25 + 1M*12.5 = 1 + 10 + 1 + 12.5 USD
    assert rec["usd_equivalent_prereg_prices"] == pytest.approx(24.5)
    assert rec["usd_cli_total_cost_sum"] == pytest.approx(1.5)
    assert len(rec["results_json_sha256"]) == 64
    assert len(rec["sha256sums_sha256"]) == 64

    params = _params()
    section = module.account(runs, params, artifacts_root, "2026-09-12T00:00:00Z")
    totals = section["cumulative"]
    assert totals["runs"] == 1
    assert totals["games_distinct"] == 1
    assert totals["model_wallclock_seconds_total"] == pytest.approx(1234.6)
    assert totals["supervisor_charged_seconds_total"] == 1234
    assert totals["supervisor_charged_runs"] == 1
    assert totals["usd_equivalent_prereg_prices"] == pytest.approx(24.5)
    assert totals["levels_completed"] == 1
    projection = section["projection_linear"]
    assert projection["basis_runs"] == 1
    assert projection["target_runs"] == 4
    assert projection["model_wallclock_seconds_total"] == pytest.approx(4 * 1234.6)
    assert projection["usd_equivalent_prereg_prices"] == pytest.approx(98.0)
    assert section["escalate"] is False
    assert section["games_remaining"] == ["ar25", "s5i5", "wa30"]
    assert section["games_run_more_than_once"] == []
    assert section["games_outside_graded_set"] == []
    assert section["set_complete"] is False
    assert section["preregistration_sha256"] == "0" * 64
    assert section["prices_usd_per_million"] == {
        "input": 10.0,
        "output": 50.0,
        "cache_read": 0.25,
        "cache_creation": 12.5,
    }

    budget_path = tmp_path / "BUDGET.json"
    before = _make_budget(budget_path)
    module.write_budget(budget_path, section)
    after = json.loads(budget_path.read_text(encoding="utf-8"))
    for key, value in before.items():
        assert after[key] == value
    assert after["g3_graded_set"]["cumulative"]["runs"] == 1
    assert after["g3_graded_set"]["recorded_utc"] == "2026-09-12T00:00:00Z"
    assert budget_path.read_text(encoding="utf-8").endswith("}\n")


def test_escalate_flag_crosses_at_the_threshold(tmp_path: Path) -> None:
    module = _load_module()
    artifacts_root = tmp_path / "artifacts" / "E999_ref"
    jobs_dir = tmp_path / "jobs"
    _make_run(artifacts_root, "20260912T000000Z_seed12345_aaaaaaaa", "ar25", 2000.0)
    _make_run(artifacts_root, "20260912T010000Z_seed12345_bbbbbbbb", "cd82", 3000.0)
    runs = [module.run_record(p, jobs_dir) for p in module.discover_runs(artifacts_root)]
    assert [r["game"] for r in runs] == ["ar25", "cd82"]

    exactly = module.account(runs, _params(escalate_above=5000.0), artifacts_root, "t")
    assert exactly["cumulative"]["model_wallclock_seconds_total"] == pytest.approx(5000.0)
    assert exactly["escalate"] is False, "the rule is 'exceeds', so equality does not escalate"

    crossed = module.account(runs, _params(escalate_above=4999.9), artifacts_root, "t")
    assert crossed["escalate"] is True
    assert crossed["hard_bound_exceeded"] is False

    bound = module.account(
        runs, _params(escalate_above=1000.0, hard_bound=4000.0), artifacts_root, "t"
    )
    assert bound["escalate"] is True
    assert bound["hard_bound_exceeded"] is True


def test_warnings_for_duplicates_foreign_games_and_experiment_ids(tmp_path: Path) -> None:
    module = _load_module()
    artifacts_root = tmp_path / "artifacts" / "E999_ref"
    jobs_dir = tmp_path / "jobs"
    _make_run(artifacts_root, "20260912T000000Z_seed12345_aaaaaaaa", "cd82", 10.0)
    _make_run(artifacts_root, "20260912T010000Z_seed12345_bbbbbbbb", "cd82", 10.0)
    _make_run(
        artifacts_root,
        "20260912T020000Z_seed12345_cccccccc",
        "zz99",
        10.0,
        experiment_id="E303_ref",
    )
    runs = [module.run_record(p, jobs_dir) for p in module.discover_runs(artifacts_root)]
    section = module.account(runs, _params(), artifacts_root, "t")
    assert section["games_run_more_than_once"] == ["cd82"]
    assert section["games_outside_graded_set"] == ["zz99"]
    assert section["runs_with_other_experiment_id"] == ["20260912T020000Z_seed12345_cccccccc"]
    assert section["cumulative"]["supervisor_charged_runs"] == 0
    assert [r["supervisor_charged_seconds"] for r in runs] == [None, None, None]
    lines = module.summary_lines(section)
    assert any("WARNING games_run_more_than_once" in line for line in lines)


def test_main_writes_budget_and_report_and_exit_code(tmp_path: Path) -> None:
    module = _load_module()
    artifacts_root = tmp_path / "artifacts" / "E304_ref"
    jobs_dir = tmp_path / "jobs"
    budget_path = tmp_path / "BUDGET.json"
    _make_budget(budget_path)
    out_path = tmp_path / "report.json"

    rc = module.main(
        [
            "--artifacts-root",
            str(artifacts_root),
            "--budget",
            str(budget_path),
            "--jobs-dir",
            str(jobs_dir),
            "--out",
            str(out_path),
        ]
    )
    assert rc == 0
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    assert budget["g3_graded_set"]["cumulative"]["runs"] == 0
    assert budget["g3_graded_set"]["experiment_id"] == "E304_ref"
    assert budget["g3_graded_set"]["set_model_seconds_escalate_above"] == pytest.approx(60000.0)
    assert budget["g3_preflight"] == {"games_measured": 3, "nested": {"keep": True}}
    assert json.loads(out_path.read_text(encoding="utf-8"))["cumulative"]["runs"] == 0

    # A run above the real escalate threshold sets the flag and the exit code, budget still written.
    _make_run(artifacts_root, "20260912T000000Z_seed12345_aaaaaaaa", "ar25", 60000.5)
    rc = module.main(
        [
            "--artifacts-root",
            str(artifacts_root),
            "--budget",
            str(budget_path),
            "--jobs-dir",
            str(jobs_dir),
        ]
    )
    assert rc == module.EXIT_ESCALATE
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    assert budget["g3_graded_set"]["escalate"] is True
    assert budget["g3_graded_set"]["cumulative"]["runs"] == 1

    # --dry-run prints but writes nothing.
    _make_run(artifacts_root, "20260912T010000Z_seed12345_bbbbbbbb", "bp35", 1.0)
    rc = module.main(
        [
            "--artifacts-root",
            str(artifacts_root),
            "--budget",
            str(budget_path),
            "--jobs-dir",
            str(jobs_dir),
            "--dry-run",
        ]
    )
    assert rc == module.EXIT_ESCALATE
    assert (
        json.loads(budget_path.read_text(encoding="utf-8"))["g3_graded_set"]["cumulative"]["runs"]
        == 1
    )
