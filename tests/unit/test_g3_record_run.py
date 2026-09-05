"""Unit tests for scripts/g3_record_run.py (G3.6b step 19, the graded-set record step)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "g3_record_run.py"
CONFIG_SHA = "a" * 64
PROMPT_HASH = "b" * 64
RUN_ID = "20260912T000000Z_seed12345_aaaaaaaa"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("g3_record_run", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _params(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "gate": "G3b",
        "preregistration_path": "synthetic",
        "preregistration_sha256": "0" * 64,
        "experiment_id": "E999_ref",
        "config": "configs/experiments/E999_ref.yaml",
        "config_sha256_on_disk": CONFIG_SHA,
        "graded_config_sha256": CONFIG_SHA,
        "prompt_hash": PROMPT_HASH,
        "games": ["ar25", "bp35", "cd82"],
        "seed": 12345,
        "wallclock_per_invocation_seconds": 9900,
        "job_wallclock_limit_seconds": 10800,
        "model_wallclock_per_run_seconds": 3600.0,
        "calls_per_run_max": 60,
        "resumptions_used_max": 0,
        "call_wallclock_seconds": 900.0,
    }
    params.update(overrides)
    return params


def _write_sums(run_dir: Path) -> None:
    lines = []
    for path in sorted(p for p in run_dir.rglob("*") if p.is_file() and p.name != "SHA256SUMS"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(run_dir).as_posix()}")
    (run_dir / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_run(
    root: Path,
    stem: str = "ar25",
    *,
    status: str = "completed",
    stderr: str = "",
    results_overrides: dict[str, Any] | None = None,
    inner_overrides: dict[str, Any] | None = None,
    manifest_overrides: dict[str, Any] | None = None,
) -> Path:
    run_dir = root / "artifacts" / "E999_ref" / RUN_ID
    run_dir.mkdir(parents=True)
    inner: dict[str, Any] = {
        "stem": stem,
        "game_id": f"{stem}-00000000",
        "stop_reason": "level_budget_exhausted",
        "model_budget_binding": None,
        "levels_completed": 1,
        "win_levels": 6,
        "rhae_environment_score": 12.5,
        "model_calls": 9,
        "model_wallclock_seconds_total": 2000.5,
        "resumptions": 0,
        "prompt_hash": PROMPT_HASH,
    }
    inner.update(inner_overrides or {})
    results: dict[str, Any] = {
        "experiment_id": "E999_ref",
        "run_id": RUN_ID,
        "seed": 12345,
        "completion_status": status,
        "config_file_sha256": CONFIG_SHA,
        "wallclock_seconds": 3000.2,
        "results": inner,
    }
    results.update(results_overrides or {})
    manifest: dict[str, Any] = {
        "run_id": RUN_ID,
        "prompt_hash": PROMPT_HASH,
        "wallclock_limit_seconds": 9900,
        "model_calls": inner["model_calls"],
    }
    manifest.update(manifest_overrides or {})
    (run_dir / "results.json").write_text(json.dumps(results), encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "stderr.log").write_text(stderr, encoding="utf-8")
    (run_dir / "stdout.log").write_text("ok\n", encoding="utf-8")
    (run_dir / "world_models").mkdir()
    (run_dir / "world_models" / "h001.py").write_text("# GOAL: x\n", encoding="utf-8")
    _write_sums(run_dir)
    return run_dir


def _make_job(
    root: Path,
    job_id: str = "g37-ar25-1",
    *,
    game: str = "ar25",
    with_result: bool = True,
    finished_utc: str = "2026-09-12T03:00:00Z",
    result_overrides: dict[str, Any] | None = None,
) -> Path:
    job_dir = root / "state" / "jobs" / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "request.json").write_text(
        json.dumps(
            {
                "id": job_id,
                "runner": "run_experiment",
                "config": "configs/experiments/E999_ref.yaml",
                "game": game,
                "wallclock_limit_s": 10800,
                "received_utc": "2026-09-12T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    if with_result:
        result: dict[str, Any] = {
            "id": job_id,
            "accepted": True,
            "returncode": 0,
            "timed_out": False,
            "wallclock_s": 3100,
            "model_seconds_charged": 2000,
            "model_seconds_source": f"artifacts/E999_ref/{RUN_ID}/results.json",
            "finished_utc": finished_utc,
            "stdout_tail": json.dumps(
                {"run_dir": f"artifacts/E999_ref/{RUN_ID}", "completion_status": "completed"}
            )
            + "\n",
            "stderr_tail": "",
        }
        result.update(result_overrides or {})
        (job_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return job_dir


def _failed_names(checks: list[Any]) -> list[str]:
    return [c.name for c in checks if not c.ok]


def test_load_parameters_reads_the_real_preregistration_and_config() -> None:
    module = _load_module()
    params = module.load_parameters(REPO_ROOT)
    assert params["gate"] == "G3b" and params["experiment_id"] == "E304_ref"
    assert params["config_sha256_on_disk"] == params["graded_config_sha256"]
    assert len(params["prompt_hash"]) == 64 and len(params["games"]) == 25
    assert params["call_wallclock_seconds"] > 0
    assert params["model_wallclock_per_run_seconds"] > 0 and params["calls_per_run_max"] > 0
    assert params["wallclock_per_invocation_seconds"] < params["job_wallclock_limit_seconds"]
    assert params["resumptions_used_max"] >= 0 and params["seed"] == 12345


def test_passing_run_verifies_every_check(tmp_path: Path) -> None:
    module = _load_module()
    _make_run(tmp_path)
    job_dir = _make_job(tmp_path)
    checks, report = module.verify_job(job_dir, _params(), tmp_path)
    assert _failed_names(checks) == []
    assert report["ok"] and report["failed"] == 0 and report["passed"] == len(checks)
    names = {c.name for c in checks}
    assert {
        "job_returncode_zero",
        "job_not_timed_out",
        "job_wallclock_within_limit",
        "job_request_names_graded_config",
        "run_dir_located",
        "run_dir_is_run_id",
        "sha256sums_verified",
        "results_config_digest",
        "results_experiment_id",
        "prompt_hash",
        "manifest_wallclock_limit",
        "completion_status_completed",
        "stderr_empty",
        "model_seconds_within_cap",
        "model_calls_within_cap",
        "resumptions_within_max",
        "seed_preregistered",
        "game_in_graded_set",
        "game_matches_job_request",
    } <= names
    run = report["run"]
    assert run["run_id"] == RUN_ID and run["game"] == "ar25"
    assert run["levels_completed"] == 1 and run["win_levels"] == 6
    assert run["model_wallclock_seconds_total"] == 2000.5 and run["model_calls"] == 9
    assert run["sha256sums_entries"] == 5
    run_dir = tmp_path / "artifacts" / "E999_ref" / RUN_ID
    assert (
        run["results_json_sha256"]
        == hashlib.sha256((run_dir / "results.json").read_bytes()).hexdigest()
    )
    lines = module.report_lines(checks, report)
    assert lines[-1].startswith("RUN VERIFIED")
    assert any(line.startswith("PASS sha256sums_verified: 5 entries") for line in lines)


def test_sha256sums_mismatch_fails(tmp_path: Path) -> None:
    module = _load_module()
    run_dir = _make_run(tmp_path)
    (run_dir / "world_models" / "h001.py").write_text("# GOAL: y\n", encoding="utf-8")
    job_dir = _make_job(tmp_path)
    checks, report = module.verify_job(job_dir, _params(), tmp_path)
    assert _failed_names(checks) == ["sha256sums_verified"]
    assert not report["ok"]
    detail = next(c.detail for c in checks if c.name == "sha256sums_verified")
    assert "1 mismatched ['world_models/h001.py']" in detail

    # A listed file that is gone is reported as missing, not as a crash.
    (run_dir / "stdout.log").unlink()
    checks, _ = module.verify_job(job_dir, _params(), tmp_path)
    detail = next(c.detail for c in checks if c.name == "sha256sums_verified")
    assert "1 missing ['stdout.log']" in detail

    # The verifier uses hashlib and the two-space format, never the shell.
    entries, mismatched, missing = module.verify_sha256sums(run_dir)
    assert entries == 5 and mismatched == ["world_models/h001.py"] and missing == ["stdout.log"]


def test_config_digest_mismatch_fails(tmp_path: Path) -> None:
    module = _load_module()
    _make_run(tmp_path)
    job_dir = _make_job(tmp_path)
    params = _params(graded_config_sha256="f" * 64)
    checks, report = module.verify_job(job_dir, params, tmp_path)
    assert _failed_names(checks) == ["results_config_digest"]
    assert not report["ok"]


def test_non_completed_run_fails_and_is_still_summarised(tmp_path: Path) -> None:
    module = _load_module()
    _make_run(tmp_path, status="step_failed")
    job_dir = _make_job(tmp_path, result_overrides={"returncode": 1})
    checks, report = module.verify_job(job_dir, _params(), tmp_path)
    assert _failed_names(checks) == ["job_returncode_zero", "completion_status_completed"]
    assert report["run"]["completion_status"] == "step_failed"
    assert module.report_lines(checks, report)[-1].startswith("RUN FAILED VERIFICATION")


def test_non_empty_stderr_fails_and_shows_first_lines(tmp_path: Path) -> None:
    module = _load_module()
    _make_run(tmp_path, stderr="Traceback (most recent call last):\n  boom\n")
    job_dir = _make_job(tmp_path)
    checks, report = module.verify_job(job_dir, _params(), tmp_path)
    assert _failed_names(checks) == ["stderr_empty"]
    detail = next(c.detail for c in checks if c.name == "stderr_empty")
    assert "Traceback" in detail and "boom" in detail
    assert not report["ok"]


def test_caps_prompt_hash_limit_and_game_checks(tmp_path: Path) -> None:
    module = _load_module()
    _make_run(
        tmp_path,
        stem="zz99",
        inner_overrides={
            "model_calls": 61,
            "model_wallclock_seconds_total": 4500.1,
            "resumptions": 1,
            "prompt_hash": "c" * 64,
        },
        manifest_overrides={"wallclock_limit_seconds": 10500},
        results_overrides={"seed": 7, "experiment_id": "E998_ref"},
    )
    job_dir = _make_job(
        tmp_path, game="ar25", result_overrides={"timed_out": True, "wallclock_s": 10801}
    )
    checks, report = module.verify_job(job_dir, _params(), tmp_path)
    assert set(_failed_names(checks)) == {
        "job_not_timed_out",
        "job_wallclock_within_limit",
        "results_experiment_id",
        "prompt_hash",
        "manifest_wallclock_limit",
        "model_seconds_within_cap",
        "model_calls_within_cap",
        "resumptions_within_max",
        "seed_preregistered",
        "game_in_graded_set",
        "game_matches_job_request",
    }
    assert report["failed"] == 11

    # Exactly the cap plus one timed-out call is still within the allowance.
    root2 = tmp_path / "second"
    _make_run(root2, inner_overrides={"model_wallclock_seconds_total": 4500.0})
    checks, _ = module.verify_job(_make_job(root2), _params(), root2)
    assert _failed_names(checks) == []


def test_job_without_result_is_a_usage_error(tmp_path: Path) -> None:
    module = _load_module()
    _make_run(tmp_path)
    job_dir = _make_job(tmp_path, with_result=False)
    with pytest.raises(module.RecordRunError, match="no result.json"):
        module.verify_job(job_dir, _params(), tmp_path)
    assert module.newest_finished_job(tmp_path / "state" / "jobs") is None


def test_unlocated_run_fails_without_crashing(tmp_path: Path) -> None:
    module = _load_module()
    job_dir = _make_job(
        tmp_path, result_overrides={"model_seconds_source": "none", "stdout_tail": "killed\n"}
    )
    checks, report = module.verify_job(job_dir, _params(), tmp_path)
    assert _failed_names(checks) == ["run_dir_located"]
    assert report["run"] is None and not report["ok"]

    # stdout_tail alone is enough to locate the run when model_seconds_source is absent.
    _make_run(tmp_path)
    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    result["stdout_tail"] = json.dumps({"run_dir": f"artifacts/E999_ref/{RUN_ID}"}) + "\n"
    assert module.locate_run_dir(result, tmp_path) == tmp_path / "artifacts" / "E999_ref" / RUN_ID


def test_newest_finished_job_is_the_default(tmp_path: Path) -> None:
    module = _load_module()
    _make_job(tmp_path, "g37-ar25-1", finished_utc="2026-09-12T03:00:00Z")
    _make_job(tmp_path, "g37-bp35-1", game="bp35", finished_utc="2026-09-12T07:00:00Z")
    _make_job(tmp_path, "g37-cd82-1", game="cd82", with_result=False)
    newest = module.newest_finished_job(tmp_path / "state" / "jobs")
    assert newest is not None and newest.name == "g37-bp35-1"


def test_main_exit_codes_and_json_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    _make_run(tmp_path)
    _make_job(tmp_path)
    monkeypatch.setattr(module, "load_parameters", lambda _root: _params())
    report_path = tmp_path / "report.json"

    rc = module.main(["--repo-root", str(tmp_path), "--json", str(report_path)])
    assert rc == module.EXIT_OK
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert written["ok"] and written["job_id"] == "g37-ar25-1"
    assert written["run"]["run_id"] == RUN_ID

    rc = module.main(["--repo-root", str(tmp_path), "--job-id", "g37-none-1"])
    assert rc == module.EXIT_ERROR

    (tmp_path / "artifacts" / "E999_ref" / RUN_ID / "stderr.log").write_text("x\n")
    rc = module.main(["--repo-root", str(tmp_path), "--job-id", "g37-ar25-1"])
    assert rc == module.EXIT_FAILED
