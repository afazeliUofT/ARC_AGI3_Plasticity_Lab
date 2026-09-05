"""Unit tests for scripts/g36b_e303_summary.py (G3.6b step 12 bookkeeping script)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "g36b_e303_summary.py"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("g36b_e303_summary", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


@pytest.fixture
def synthetic_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "artifacts" / "E999_ref" / "20260101T000000Z_seed1_deadbeef"
    run_dir.mkdir(parents=True)
    results = {
        "experiment_id": "E999_ref",
        "run_id": "20260101T000000Z_seed1_deadbeef",
        "seed": 1,
        "completion_status": "completed",
        "config_file_sha256": "c" * 64,
        "wallclock_seconds": 100.25,
        "results": {
            "stem": "cd82",
            "game_id": "cd82-fb555c5d",
            "prompt_hash": "p" * 64,
            "model_identifier": "claude-fable-5-1",
            "planner": {
                "click_grid_step": 6,
                "click_points": 121,
                "max_depth": 16,
                "max_nodes": 20000,
            },
            "spend_control": {"model_wallclock_per_run_seconds": 2400.0},
            "simulation_budget": {"max_steps": 5000000, "used": 10},
            "stop_reason": "model_budget_exhausted",
            "model_budget_binding": "spend_control.model_wallclock_per_run_seconds",
            "levels_completed": 1,
            "win_levels": 6,
            "levels": [
                {
                    "level": 1,
                    "completed": True,
                    "completion_action_index": 27,
                    "official_baseline_actions": 55,
                },
                {
                    "level": 2,
                    "completed": False,
                    "completion_action_index": None,
                    "official_baseline_actions": 8,
                },
            ],
            "rhae_environment_score": 4.76,
            "rhae_level_scores": [115.0, 0.0],
            "actions_total": 27,
            "action_budget_total": 855,
            "exploration_actions": 7,
            "plan_actions": 20,
            "reset_actions": 0,
            "model_calls": 2,
            "calls_without_program": 0,
            "model_wallclock_seconds_total": 12.34,
            "tokens_by_kind": {
                "cache_creation": 1_000_000,
                "cache_read": 0,
                "input": 0,
                "output": 1_000_000,
            },
            "tokens_total": 2_000_000,
            "plans_searched": 3,
            "plans_executed": 2,
            "hypotheses_proposed": 2,
            "hypotheses_certified": 2,
            "predictions_compared": 10,
            "prediction_mismatches": 4,
        },
    }
    (run_dir / "results.json").write_text(json.dumps(results), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {"git_commit": "abcdef0123456789", "git_dirty": True, "wallclock_limit_seconds": 10500}
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        run_dir / "plans.jsonl",
        [
            {
                "plan_index": 0,
                "outcome": "not_found",
                "nodes_expanded": 5,
                "predicted_levels_completed_max": 0,
            },
            {
                "plan_index": 1,
                "outcome": "found",
                "hypothesis_id": "h001",
                "max_depth_reached": 3,
                "nodes_expanded": 40,
                "predicted_levels_completed_max": 1,
                "actions": [{"action": 1}, {"action": 1}, {"action": 5}],
            },
            {
                "plan_index": 2,
                "outcome": "found",
                "hypothesis_id": "h002",
                "max_depth_reached": 1,
                "nodes_expanded": 1,
                "predicted_levels_completed_max": 1,
                "actions": [{"action": 5}],
            },
        ],
    )
    _write_jsonl(
        run_dir / "hypotheses.jsonl",
        [
            {"event": "proposed", "hypothesis_id": "h001", "certified": True},
            {"event": "decertified", "hypothesis_id": "h001", "plan_index": 1},
            {"event": "proposed", "hypothesis_id": "h002", "certified": True},
            {"event": "decertified", "hypothesis_id": "h002", "plan_index": None},
        ],
    )
    _write_jsonl(
        run_dir / "model_calls.jsonl",
        [
            {"call_index": 1, "wallclock_seconds": 5.04, "total_cost_usd": 1.5},
            {"call_index": 2, "wallclock_seconds": 7.3, "total_cost_usd": 2.25},
        ],
    )
    (run_dir / "SHA256SUMS").write_text("x\n", encoding="utf-8")
    return run_dir


def test_summarise_run_derives_numbers_and_digests(synthetic_run: Path, tmp_path: Path) -> None:
    module = _load_module()
    summary = module.summarise_run(synthetic_run, tmp_path / "no_jobs")

    assert summary["game"] == "cd82"
    assert summary["plans_found"] == 2
    assert summary["plan_outcomes"] == {"not_found": 1, "found": 2}
    assert summary["plans_found_detail"][0] == {
        "plan_index": 1,
        "hypothesis_id": "h001",
        "depth": 3,
        "nodes": 40,
        "actions": 3,
    }
    assert summary["nodes_expanded_max"] == 40
    assert summary["predicted_levels_completed_max"] == 1
    assert summary["hypotheses_decertified"] == 2
    assert summary["hypotheses_decertified_on_planned_action"] == 1
    assert summary["completion_action_indices"] == [27]
    assert summary["level_1_official_baseline_actions"] == 55
    assert summary["prediction_mismatch_rate"] == pytest.approx(0.4)
    assert summary["per_call_wallclock_seconds"] == [5.0, 7.3]
    assert summary["usd_cli_total_cost_sum"] == pytest.approx(3.75)
    # one million cache_creation tokens at 12.5 plus one million output tokens at 50
    assert summary["usd_equivalent_prereg_prices"] == pytest.approx(62.5)
    assert summary["manifest_git_commit"] == "abcdef0"
    assert summary["wallclock_limit_seconds"] == 10500
    assert summary["supervisor_job"] is None

    expected_digest = hashlib.sha256((synthetic_run / "results.json").read_bytes()).hexdigest()
    assert summary["sha256"]["results.json"] == expected_digest
    assert set(summary["sha256"]) == {
        "results.json",
        "manifest.json",
        "plans.jsonl",
        "hypotheses.jsonl",
        "model_calls.jsonl",
        "SHA256SUMS",
    }


def test_job_result_is_attached_when_it_names_the_run(synthetic_run: Path, tmp_path: Path) -> None:
    module = _load_module()
    jobs_dir = tmp_path / "jobs"
    (jobs_dir / "job-1").mkdir(parents=True)
    (jobs_dir / "job-1" / "result.json").write_text(
        json.dumps(
            {
                "id": "job-1",
                "accepted": True,
                "returncode": 0,
                "timed_out": False,
                "wallclock_s": 123,
                "model_seconds_charged": 12,
                "model_seconds_source": str(synthetic_run) + "/results.json",
            }
        ),
        encoding="utf-8",
    )
    summary = module.summarise_run(synthetic_run, jobs_dir)
    assert summary["supervisor_job"] is not None
    assert summary["supervisor_job"]["id"] == "job-1"
    assert summary["supervisor_job"]["wallclock_s"] == 123


def test_aggregate_sums_across_runs(synthetic_run: Path, tmp_path: Path) -> None:
    module = _load_module()
    one = module.summarise_run(synthetic_run, tmp_path / "no_jobs")
    totals = module.aggregate([one, one])
    assert totals["runs"] == 2
    assert totals["plans_searched"] == 6
    assert totals["plans_found"] == 4
    assert totals["plan_actions"] == 40
    assert totals["levels_completed"] == 2
    assert totals["predictions_compared"] == 20
    assert totals["prediction_mismatches"] == 8
    assert totals["hypotheses_decertified_on_planned_action"] == 2
    assert totals["usd_equivalent_prereg_prices"] == pytest.approx(125.0)


def test_main_writes_report(
    synthetic_run: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_module()
    out = tmp_path / "report.json"
    rc = module.main([str(synthetic_run), "--out", str(out), "--jobs-dir", str(tmp_path / "none")])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["totals_all"]["runs"] == 1
    assert "E999_ref" in report["totals_by_experiment"]
    assert report["totals_before_e303"]["runs"] == 1
    captured = capsys.readouterr().out
    assert "### E999_ref" in captured
    assert "report written" in captured
