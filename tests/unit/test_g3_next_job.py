"""Unit tests for scripts/g3_next_job.py (G3.6b step 18, the graded-set queue step)."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "g3_next_job.py"
TZ = dt.timezone(dt.timedelta(hours=-4), name="EDT-fixed")
AFTER_START = dt.datetime(2026, 9, 12, 9, 0, tzinfo=TZ)
BEFORE_START = dt.datetime(2026, 9, 11, 16, 59, tzinfo=TZ)
CONFIG_TEXT = "schema_version: 1\nexperiment_id: E999_ref\nwallclock_limit_seconds: 9900\n"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("g3_next_job", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclasses with postponed annotations resolve their module through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _repo(tmp_path: Path, config_text: str = CONFIG_TEXT) -> Path:
    """A tmp repo layout: configs/experiments/E999_ref.yaml, empty state/, no artifacts."""
    (tmp_path / "configs" / "experiments").mkdir(parents=True)
    (tmp_path / "configs" / "experiments" / "E999_ref.yaml").write_text(
        config_text, encoding="utf-8"
    )
    (tmp_path / "state").mkdir()
    return tmp_path


def _params(root: Path, **overrides: Any) -> dict[str, Any]:
    config = root / "configs" / "experiments" / "E999_ref.yaml"
    params: dict[str, Any] = {
        "gate": "G3b",
        "preregistration_path": "synthetic",
        "preregistration_sha256": "0" * 64,
        "experiment_id": "E999_ref",
        "config": "configs/experiments/E999_ref.yaml",
        "graded_config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "games": ["ar25", "bp35", "cd82"],
        "job_wallclock_limit_seconds": 10800,
        "wallclock_per_invocation_seconds": 9900,
        "job_margin_over_runner_limit_seconds_min": 900,
        "failed_reruns_per_game_max": 1,
        "earliest_start_local": "2026-09-11T17:00",
    }
    params.update(overrides)
    return params


def _make_run(root: Path, run_id: str, stem: str, status: str | None = "completed") -> Path:
    """A run directory; status None writes only resolved_config.yaml (a killed run)."""
    run_dir = root / "artifacts" / "E999_ref" / run_id
    run_dir.mkdir(parents=True)
    if status is None:
        (run_dir / "resolved_config.yaml").write_text(
            f"runner_params:\n  game: {stem}\n", encoding="utf-8"
        )
        return run_dir
    (run_dir / "results.json").write_text(
        json.dumps(
            {
                "experiment_id": "E999_ref",
                "run_id": run_id,
                "completion_status": status,
                "results": {"stem": stem, "game_id": f"{stem}-00000000"},
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def _make_job(root: Path, job_id: str, received_utc: str, with_result: bool) -> Path:
    job_dir = root / "state" / "jobs" / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "request.json").write_text(
        json.dumps({"id": job_id, "received_utc": received_utc}), encoding="utf-8"
    )
    if with_result:
        (job_dir / "result.json").write_text(
            json.dumps({"id": job_id, "returncode": 0}), encoding="utf-8"
        )
    return job_dir


def test_load_parameters_reads_the_real_preregistration() -> None:
    module = _load_module()
    params = module.load_parameters(REPO_ROOT)
    assert params["gate"] == "G3b"
    assert params["experiment_id"] == "E304_ref"
    assert params["config"] == "configs/experiments/E304_ref.yaml"
    assert len(params["games"]) == 25 and params["games"] == sorted(params["games"])
    assert params["games"][0] == "ar25" and params["games"][-1] == "wa30"
    assert (
        params["wallclock_per_invocation_seconds"]
        + params["job_margin_over_runner_limit_seconds_min"]
        <= params["job_wallclock_limit_seconds"]
    )
    assert params["failed_reruns_per_game_max"] >= 0
    assert dt.datetime.fromisoformat(params["earliest_start_local"]).year == 2026
    assert len(params["preregistration_sha256"]) == 64
    # The real graded config on disk still carries the pre-registered digest.
    real_config = REPO_ROOT / params["config"]
    assert hashlib.sha256(real_config.read_bytes()).hexdigest() == params["graded_config_sha256"]


def test_empty_root_queues_first_game_attempt_one(tmp_path: Path) -> None:
    module = _load_module()
    root = _repo(tmp_path)
    decision = module.decide(_params(root), root=root, now=AFTER_START)
    assert decision.ok, decision.reason
    assert decision.request == {
        "id": "g37-ar25-1",
        "runner": "run_experiment",
        "config": "configs/experiments/E999_ref.yaml",
        "game": "ar25",
        "wallclock_limit_s": 10800,
    }
    assert decision.runs_seen == 0 and decision.completed_games == []
    assert decision.earliest_start_local == "2026-09-11T17:00:00-04:00"


def test_completed_first_game_moves_to_second(tmp_path: Path) -> None:
    module = _load_module()
    root = _repo(tmp_path)
    _make_run(root, "20260912T000000Z_seed12345_aaaaaaaa", "ar25")
    decision = module.decide(_params(root), root=root, now=AFTER_START)
    assert decision.ok, decision.reason
    assert decision.request is not None
    assert decision.request["id"] == "g37-bp35-1" and decision.request["game"] == "bp35"
    assert decision.completed_games == ["ar25"]


def test_incomplete_first_game_gets_attempt_two(tmp_path: Path) -> None:
    module = _load_module()
    root = _repo(tmp_path)
    _make_run(root, "20260912T000000Z_seed12345_aaaaaaaa", "ar25", status="step_failed")
    decision = module.decide(_params(root), root=root, now=AFTER_START)
    assert decision.ok, decision.reason
    assert decision.request is not None
    assert decision.request["id"] == "g37-ar25-2" and decision.request["game"] == "ar25"

    # A killed run (no results.json, only resolved_config.yaml) counts as an attempt too.
    root2 = _repo(tmp_path / "second")
    _make_run(root2, "20260912T000000Z_seed12345_aaaaaaaa", "ar25", status=None)
    runs = module.discover_runs(root2 / "artifacts" / "E999_ref")
    assert [(r.game, r.completion_status, r.source) for r in runs] == [
        ("ar25", None, "resolved_config.yaml")
    ]
    decision = module.decide(_params(root2), root=root2, now=AFTER_START)
    assert decision.ok and decision.request is not None
    assert decision.request["id"] == "g37-ar25-2"


def test_two_incomplete_runs_refuse_a_third(tmp_path: Path) -> None:
    module = _load_module()
    root = _repo(tmp_path)
    _make_run(root, "20260912T000000Z_seed12345_aaaaaaaa", "ar25", status="step_failed")
    _make_run(root, "20260912T010000Z_seed12345_bbbbbbbb", "ar25", status=None)
    decision = module.decide(_params(root), root=root, now=AFTER_START)
    assert not decision.ok
    assert "failed_reruns_per_game_max" in decision.reason and "ar25" in decision.reason
    assert decision.request is None
    # The order never skips ahead: bp35 is not offered while ar25 is unresolved.
    assert "bp35" not in decision.reason


def test_set_complete_refuses(tmp_path: Path) -> None:
    module = _load_module()
    root = _repo(tmp_path)
    for index, stem in enumerate(["ar25", "bp35", "cd82"]):
        _make_run(root, f"20260912T0{index}0000Z_seed12345_{stem}0000", stem)
    decision = module.decide(_params(root), root=root, now=AFTER_START)
    assert not decision.ok and "set is complete" in decision.reason
    assert decision.completed_games == ["ar25", "bp35", "cd82"]


def test_before_earliest_start_refuses_and_prints_both_times(tmp_path: Path) -> None:
    module = _load_module()
    root = _repo(tmp_path)
    decision = module.decide(_params(root), root=root, now=BEFORE_START)
    assert not decision.ok
    assert "before earliest_start_local" in decision.reason
    assert "2026-09-11T16:59:00-04:00" in decision.reason
    assert "2026-09-11T17:00:00-04:00" in decision.reason
    assert decision.config_sha256 is None, "the time check comes before every file read"
    # The comparison is zone-aware: 17:00 local exactly is not before the start.
    at_start = dt.datetime(2026, 9, 11, 17, 0, tzinfo=TZ)
    assert module.decide(_params(root), root=root, now=at_start).ok
    naive = AFTER_START.replace(tzinfo=None)
    with pytest.raises(ValueError):
        module.decide(_params(root), root=root, now=naive)


def test_config_digest_mismatch_refuses(tmp_path: Path) -> None:
    module = _load_module()
    root = _repo(tmp_path)
    params = _params(root, graded_config_sha256="f" * 64)
    decision = module.decide(params, root=root, now=AFTER_START)
    assert not decision.ok and "graded_config_sha256" in decision.reason
    assert decision.config_sha256 == hashlib.sha256(CONFIG_TEXT.encode()).hexdigest()

    missing = _params(root, config="configs/experiments/E998_ref.yaml")
    decision = module.decide(missing, root=root, now=AFTER_START)
    assert not decision.ok and "does not exist" in decision.reason


def test_runner_limit_and_margin_are_checked_against_the_job_limit(tmp_path: Path) -> None:
    module = _load_module()
    root = _repo(tmp_path, config_text=CONFIG_TEXT.replace("9900", "10500"))
    params = _params(root, wallclock_per_invocation_seconds=10500)
    decision = module.decide(params, root=root, now=AFTER_START)
    assert not decision.ok and "margin 900" in decision.reason

    root2 = _repo(tmp_path / "second", config_text=CONFIG_TEXT.replace("9900", "9000"))
    decision = module.decide(_params(root2), root=root2, now=AFTER_START)
    assert not decision.ok and "wallclock_per_invocation_seconds 9900" in decision.reason


def test_pending_request_or_in_flight_job_refuses(tmp_path: Path) -> None:
    module = _load_module()
    root = _repo(tmp_path)
    (root / "state" / "job_request.json").write_text("{}\n", encoding="utf-8")
    decision = module.decide(_params(root), root=root, now=AFTER_START)
    assert not decision.ok and "already exists" in decision.reason
    (root / "state" / "job_request.json").unlink()

    _make_job(root, "g36d-wa30-1", "2026-09-05T19:19:50Z", with_result=True)
    assert module.in_flight(root / "state" / "jobs") is None
    assert module.decide(_params(root), root=root, now=AFTER_START).ok

    _make_job(root, "g37-ar25-1", "2026-09-12T13:00:00Z", with_result=False)
    assert module.in_flight(root / "state" / "jobs") == "g37-ar25-1"
    decision = module.decide(_params(root), root=root, now=AFTER_START)
    assert not decision.ok and "g37-ar25-1" in decision.reason and "in flight" in decision.reason

    # Once the result lands, the id g37-ar25-1 is taken but no run exists under the root:
    # the queue refuses rather than reuse an id.
    (root / "state" / "jobs" / "g37-ar25-1" / "result.json").write_text("{}", encoding="utf-8")
    decision = module.decide(_params(root), root=root, now=AFTER_START)
    assert not decision.ok and "already exists under jobs" in decision.reason


def test_main_dry_run_writes_nothing_and_real_run_writes_the_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    root = _repo(tmp_path)
    params = _params(root)
    monkeypatch.setattr(module, "load_parameters", lambda _root: params)
    request_path = root / "state" / "job_request.json"

    class _Clock(dt.datetime):
        @classmethod
        def now(cls, tz: dt.tzinfo | None = None) -> _Clock:  # type: ignore[override]
            return cls(2026, 9, 12, 9, 0, tzinfo=TZ)

    monkeypatch.setattr(module.dt, "datetime", _Clock)

    rc = module.main(["--repo-root", str(root), "--dry-run"])
    assert rc == module.EXIT_OK
    assert not request_path.exists()

    rc = module.main(["--repo-root", str(root)])
    assert rc == module.EXIT_OK
    written = json.loads(request_path.read_text(encoding="utf-8"))
    assert written["id"] == "g37-ar25-1" and written["wallclock_limit_s"] == 10800
    assert request_path.read_text(encoding="utf-8").endswith("}\n")

    # A second call sees the pending request and refuses with exit 2.
    rc = module.main(["--repo-root", str(root)])
    assert rc == module.EXIT_REFUSED
