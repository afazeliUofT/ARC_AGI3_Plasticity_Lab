"""Unit tests for the G1 evaluator in scripts/verify_run.py.

Synthetic run directories in ``tmp_path`` drive every check. Every number a test compares
against is read from the real ``preregistration/G1.yaml`` through the verifier's own
``threshold()`` so the tests carry no copy of a gate threshold. The replay check is exercised
on the real cached ``ls20`` game with a short trajectory, so the digest the runner will record
and the digest the verifier recomputes are shown to be the same function.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from arc_plasticity.core.guards import NetworkGuard
from arc_plasticity.environments import arc_interface as ai

ROOT = Path(__file__).resolve().parents[2]
ENV_DIR = ROOT / "environment_files"
LS20 = "ls20"


def _load_module() -> ModuleType:
    if "verify_run" in sys.modules:
        return sys.modules["verify_run"]
    spec = importlib.util.spec_from_file_location("verify_run", ROOT / "scripts" / "verify_run.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


vr = _load_module()


@pytest.fixture(scope="module")
def prereg() -> dict[str, Any]:
    data: dict[str, Any]
    data, _, _ = vr.load_preregistration("G1", ROOT)
    return data


@pytest.fixture(scope="module")
def excluded() -> frozenset[str]:
    data, _, _ = vr.load_preregistration("G1", ROOT)
    _, names = vr.check_nondeterministic_fields(data, ROOT)
    return names


def _ls20_game_id() -> str:
    for game_dir in (ENV_DIR / LS20).iterdir():
        meta = json.loads((game_dir / "metadata.json").read_text())
        return str(meta["game_id"])
    raise AssertionError("ls20 is not cached")


@pytest.fixture(scope="module")
def ls20_recording() -> dict[str, Any]:
    """Play five actions on the real ls20 and record what the E100 runner would record."""
    game_id = _ls20_game_id()
    actions = [ai.ActionRecord(1), ai.ActionRecord(2), ai.ActionRecord(3), ai.ActionRecord(4),
               ai.ActionRecord(6, {"x": 3, "y": 4})]
    with NetworkGuard(0):
        arcade = ai.open_offline_arcade(ENV_DIR)
        env = ai.make_environment(arcade, game_id, 12345)
        reset = env.reset()
        assert reset is not None
        current = ai.summarize_response(reset)
        transitions: list[dict[str, Any]] = []
        for i, record in enumerate(actions, start=1):
            nxt = ai.step_environment(env, record)
            assert nxt is not None
            current = nxt
            transitions.append(
                {"game_index": 0, "game_id": game_id, "step_index": i, "action": record.action,
                 "data": dict(record.data), "frame_sha256": current.digest()}
            )
    game = {
        "game_id": game_id, "seed": 12345, "steps_taken": len(actions),
        "final_state": current.state, "levels_completed": current.levels_completed,
        "win_levels": current.win_levels, "terminal": current.terminal,
        "final_frame_sha256": current.digest(), "step_failed": False,
    }
    return {"game": game, "transitions": transitions}


# ------------------------------------------------------------------ synthetic runs


def _manifest(prereg: dict[str, Any], seed: int, run_id: str, **overrides: Any) -> dict[str, Any]:
    m: dict[str, Any] = {k: "x" for k in vr.REQUIRED_MANIFEST_KEYS}
    m.update(
        {
            "seed": seed,
            "run_id": run_id,
            "completion_status": "completed",
            "network_calls_allowed": vr.threshold(prereg, "network_calls_allowed"),
            "network_attempts": 0,
            "model_calls_allowed": vr.threshold(prereg, "model_calls_allowed"),
            "model_calls": 0,
        }
    )
    m.update(overrides)
    return m


def _fake_games(n: int, terminal: int = 1, failed: int = 0) -> list[dict[str, Any]]:
    games = []
    for i in range(n):
        is_terminal = i < terminal
        games.append(
            {
                "game_id": f"g{i:03d}-deadbeef", "seed": 1, "steps_taken": 10,
                "final_state": "GAME_OVER" if is_terminal else "NOT_FINISHED",
                "levels_completed": 0, "win_levels": 1, "terminal": is_terminal,
                "final_frame_sha256": "0" * 64, "step_failed": i < failed,
            }
        )
    return games


def _write_g1_run(
    root: Path,
    prereg: dict[str, Any],
    run_id: str,
    seed: int,
    games: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
    *,
    steps: int | None = None,
    fps: float | None = None,
    stated_fps: float | None = None,
    manifest_overrides: dict[str, Any] | None = None,
    results_overrides: dict[str, Any] | None = None,
    metric_value: float = 0.5,
) -> Path:
    run = root / run_id
    run.mkdir(parents=True)
    fps_min = float(vr.threshold(prereg, "throughput_fps_min"))
    steps_min = int(vr.threshold(prereg, "throughput_min_steps_measured"))
    steps = steps if steps is not None else 2 * steps_min
    fps = fps if fps is not None else 2 * fps_min
    seconds = steps / fps
    runner_results: dict[str, Any] = {
        "operation_mode": prereg["experiment"]["operation_mode"],
        "network_guard": "NetworkGuard",
        "games": games,
    }
    results: dict[str, Any] = {
        "run_id": run_id,
        "created_utc": "2026-09-04T00:00:00Z",
        "wallclock_seconds": 1.0,
        "seed": seed,
        "results": runner_results,
    }
    results.update(results_overrides or {})
    files: dict[str, str] = {
        "manifest.json": json.dumps(_manifest(prereg, seed, run_id, **(manifest_overrides or {}))),
        "resolved_config.yaml": f"seed: {seed}\n",
        "results.json": json.dumps(results),
        "metrics.csv": f"metric,value\nscore,{metric_value}\n",
        "environment_results.csv": "environment,steps\ne,1\n",
        "transitions.jsonl": "".join(json.dumps(t) + "\n" for t in transitions),
        "hypotheses.jsonl": "",
        "memory_operations.jsonl": "",
        "stdout.log": "ok\n",
        "stderr.log": "",
        "git_state.txt": "clean\n",
        "environment_info.json": "{}",
        "throughput.json": json.dumps(
            {"aggregate": {"steps": steps, "step_seconds": seconds,
                           "fps": stated_fps if stated_fps is not None else steps / seconds},
             "per_game": []}
        ),
    }
    for name, content in files.items():
        (run / name).write_text(content)
    lines = [f"{hashlib.sha256((run / n).read_bytes()).hexdigest()}  {n}" for n in files]
    (run / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    return run


# ------------------------------------------------------------------ thresholds and order


def test_every_g1_threshold_is_read_from_the_preregistration(prereg: dict[str, Any]) -> None:
    for key in (
        "arc_agi_locked_version", "cached_games_required", "cache_manifest_drift_files_max",
        "network_calls_allowed", "network_attempts_max", "model_calls_allowed",
        "games_attempted_min", "terminal_games_min", "step_failures_max",
        "replay_final_frame_identity_min", "replay_divergent_games_max", "throughput_fps_min",
        "throughput_min_steps_measured", "excluded_key_max_depth",
        "excluded_key_container_values_allowed",
    ):
        assert vr.threshold(prereg, key) is not None


def test_g1_checks_raise_without_thresholds(prereg: dict[str, Any], tmp_path: Path) -> None:
    stripped = {**prereg, "thresholds": {}}
    for fn in (
        lambda: vr.check_arc_agi_version_pinned(stripped, ROOT),
        lambda: vr.check_environment_cache_manifest(stripped, ROOT),
        lambda: vr.check_offline_run(stripped, tmp_path),
        lambda: vr.check_games_attempted_and_terminal(stripped, tmp_path),
        lambda: vr.check_exclusion_nesting(stripped, tmp_path, frozenset()),
        lambda: vr.check_replay_final_frame_identity(stripped, tmp_path, ROOT),
        lambda: vr.check_throughput(stripped, tmp_path),
    ):
        with pytest.raises(vr.PreregistrationError):
            fn()


def test_evaluator_order_matches_checks_in_order(
    prereg: dict[str, Any], tmp_path: Path, ls20_recording: dict[str, Any]
) -> None:
    proto = prereg["determinism_protocol"]
    g, t = ls20_recording["game"], ls20_recording["transitions"]
    _write_g1_run(tmp_path, prereg, "run_a", proto["fixed_seed"], [g], t)
    _write_g1_run(tmp_path, prereg, "run_b", proto["fixed_seed"], [g], t)
    _write_g1_run(tmp_path, prereg, "run_c", proto["contrast_seed"], [g], t, metric_value=0.7)
    report = vr.evaluate("G1", tmp_path, ROOT, skip_tooling=True)
    names = [c.name for c in report.checks if c.name != "nondeterministic_fields_within_bounds"]
    expected: list[str] = []
    for entry in prereg["verification"]["checks_in_order"]:
        head = entry.split(" (")[0]
        expected.extend(x.strip() for x in head.split(","))
    expected = [
        {"uv_sync": "uv_sync_exit_code", "pytest": "pytest_exit_code", "ruff": "ruff_exit_code",
         "mypy": "mypy_exit_code"}.get(n, n)
        for n in expected
    ]
    expected.insert(expected.index("pytest_exit_code") + 1, "pytest_min_tests_collected")
    assert names == expected
    assert set(report.skipped) == {
        "uv_sync_exit_code", "pytest_exit_code", "pytest_min_tests_collected",
        "ruff_exit_code", "mypy_exit_code",
    }
    by_name = {c.name: c for c in report.checks}
    assert by_name["replay_final_frame_identity"].passed, by_name["replay_final_frame_identity"].observed
    assert by_name["exclusion_nesting"].passed
    assert by_name["determinism_identity"].passed, by_name["determinism_identity"].observed
    assert by_name["throughput"].passed


# ------------------------------------------------------------------ version pin


def test_arc_agi_version_pinned_on_real_repo(prereg: dict[str, Any]) -> None:
    result = vr.check_arc_agi_version_pinned(prereg, ROOT)
    assert result.passed, result.observed
    assert result.observed["uv_lock"]["arc-agi"] == vr.threshold(prereg, "arc_agi_locked_version")
    assert "arcengine" in result.observed["uv_lock"]


def test_arc_agi_version_mismatch_fails(prereg: dict[str, Any], tmp_path: Path) -> None:
    (tmp_path / "uv.lock").write_text(
        'version = 1\n[[package]]\nname = "arc-agi"\nversion = "0.0.1"\n'
    )
    result = vr.check_arc_agi_version_pinned(prereg, tmp_path)
    assert not result.passed
    assert any("uv.lock arc-agi" in p for p in result.observed["problems"])


# ------------------------------------------------------------------ cache manifest


def _synthetic_cache_root(tmp_path: Path, prereg: dict[str, Any]) -> tuple[Path, Path]:
    """A repo-like root with N fake cached games, an evidence doc listing them, and a manifest."""
    root = tmp_path / "repo"
    stems = ai.public_game_stems(ROOT)
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "EVIDENCE_ARC.md").write_text(
        "## 1.1\n\nPublic game ID stems (two mirrors agree):\n\n```\n"
        + "  ".join(stems) + "\n```\n"
    )
    env_rel = prereg["experiment"]["environments_dir"]
    manifest_rel = prereg["cache_warming"]["manifest_path"]
    games = []
    for stem in stems:
        gdir = root / env_rel / stem / "0123abcd"
        gdir.mkdir(parents=True)
        (gdir / "metadata.json").write_text(
            json.dumps({"game_id": f"{stem}-0123abcd", "baseline_actions": [3, 4],
                        "date_downloaded": "2026-09-04T05:28:00Z"})
        )
        (gdir / f"{stem}.py").write_text(f"# {stem}\n")
        files = {
            p.relative_to(root / env_rel).as_posix(): ai.sha256_of(p)
            for p in ai.iter_environment_files(root / env_rel)
            if p.is_relative_to(gdir)
        }
        games.append(
            {"stem": stem, "game_id": f"{stem}-0123abcd",
             "local_dir": gdir.relative_to(root).as_posix(),
             "date_downloaded": "2026-09-04T05:28:00Z", "baseline_actions_count": 2,
             "files": files}
        )
    manifest_path = root / manifest_rel
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "generated_utc": "2026-09-04T00:00:00Z",
                    "environments_dir": env_rel, "games": games,
                    "totals": {"games": len(games), "files": 2 * len(games)}})
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", manifest_rel], cwd=root, check=True)
    return root, root / env_rel


def test_cache_manifest_passes_when_disk_matches(prereg: dict[str, Any], tmp_path: Path) -> None:
    root, _ = _synthetic_cache_root(tmp_path, prereg)
    result = vr.check_environment_cache_manifest(prereg, root)
    assert result.passed, result.observed
    assert result.observed["drift_files"] == 0
    assert result.observed["listed_stems"] == vr.threshold(prereg, "cached_games_required")
    assert result.observed["committed"] is True


def test_cache_manifest_detects_modified_file(prereg: dict[str, Any], tmp_path: Path) -> None:
    root, env_dir = _synthetic_cache_root(tmp_path, prereg)
    (env_dir / LS20 / "0123abcd" / f"{LS20}.py").write_text("# changed\n")
    result = vr.check_environment_cache_manifest(prereg, root)
    assert not result.passed
    assert result.observed["drift"]["mismatched"] == [f"{LS20}/0123abcd/{LS20}.py"]


def test_cache_manifest_detects_unlisted_file(prereg: dict[str, Any], tmp_path: Path) -> None:
    root, env_dir = _synthetic_cache_root(tmp_path, prereg)
    (env_dir / LS20 / "0123abcd" / "extra.json").write_text("{}")
    result = vr.check_environment_cache_manifest(prereg, root)
    assert not result.passed
    assert result.observed["drift"]["unlisted"] == [f"{LS20}/0123abcd/extra.json"]


def test_cache_manifest_ignores_bytecode(prereg: dict[str, Any], tmp_path: Path) -> None:
    root, env_dir = _synthetic_cache_root(tmp_path, prereg)
    cache = env_dir / LS20 / "0123abcd" / "__pycache__"
    cache.mkdir()
    (cache / f"{LS20}.cpython-312.pyc").write_bytes(b"\x00")
    result = vr.check_environment_cache_manifest(prereg, root)
    assert result.passed, result.observed


def test_cache_manifest_missing_fails(prereg: dict[str, Any], tmp_path: Path) -> None:
    result = vr.check_environment_cache_manifest(prereg, tmp_path)
    assert not result.passed
    assert any("missing" in p for p in result.observed["problems"])


def test_cache_manifest_untracked_fails(prereg: dict[str, Any], tmp_path: Path) -> None:
    root, _ = _synthetic_cache_root(tmp_path, prereg)
    subprocess.run(["git", "rm", "-q", "--cached", prereg["cache_warming"]["manifest_path"]],
                   cwd=root, check=True)
    result = vr.check_environment_cache_manifest(prereg, root)
    assert not result.passed
    assert result.observed["committed"] is False


def test_public_stems_parse_from_real_evidence_base(prereg: dict[str, Any]) -> None:
    stems = ai.public_game_stems(ROOT)
    assert len(stems) == vr.threshold(prereg, "cached_games_required")
    assert len(set(stems)) == len(stems)
    assert LS20 in stems


# ------------------------------------------------------------------ offline and games


def test_offline_run_passes_and_fails(prereg: dict[str, Any], tmp_path: Path) -> None:
    _write_g1_run(tmp_path, prereg, "run_a", 1, _fake_games(1), [])
    assert vr.check_offline_run(prereg, tmp_path).passed
    _write_g1_run(tmp_path, prereg, "run_b", 1, _fake_games(1), [],
                  manifest_overrides={"network_attempts": 1})
    result = vr.check_offline_run(prereg, tmp_path)
    assert not result.passed
    assert any("run_b: network_attempts" in p for p in result.observed["problems"])


def test_offline_run_requires_offline_mode_and_guard(prereg: dict[str, Any], tmp_path: Path) -> None:
    _write_g1_run(
        tmp_path, prereg, "run_a", 1, _fake_games(1), [],
        results_overrides={"results": {"operation_mode": "ONLINE", "network_guard": None,
                                       "games": _fake_games(1)}},
    )
    result = vr.check_offline_run(prereg, tmp_path)
    assert not result.passed
    assert any("operation_mode" in p for p in result.observed["problems"])
    assert any("network_guard" in p for p in result.observed["problems"])


def test_games_attempted_and_terminal(prereg: dict[str, Any], tmp_path: Path) -> None:
    n = int(vr.threshold(prereg, "games_attempted_min"))
    t = int(vr.threshold(prereg, "terminal_games_min"))
    _write_g1_run(tmp_path, prereg, "run_a", 1, _fake_games(n, terminal=t), [])
    result = vr.check_games_attempted_and_terminal(prereg, tmp_path)
    assert result.passed, result.observed
    assert result.observed["runs"]["run_a"]["attempted"] == n


def test_games_fail_on_too_few_or_no_terminal_or_step_failure(
    prereg: dict[str, Any], tmp_path: Path
) -> None:
    n = int(vr.threshold(prereg, "games_attempted_min"))
    t = int(vr.threshold(prereg, "terminal_games_min"))
    f = int(vr.threshold(prereg, "step_failures_max"))
    _write_g1_run(tmp_path / "few", prereg, "run_a", 1, _fake_games(n - 1, terminal=t), [])
    assert not vr.check_games_attempted_and_terminal(prereg, tmp_path / "few").passed
    _write_g1_run(tmp_path / "noterm", prereg, "run_a", 1, _fake_games(n, terminal=t - 1), [])
    assert not vr.check_games_attempted_and_terminal(prereg, tmp_path / "noterm").passed
    _write_g1_run(tmp_path / "fail", prereg, "run_a", 1, _fake_games(n, terminal=t, failed=f + 1), [])
    assert not vr.check_games_attempted_and_terminal(prereg, tmp_path / "fail").passed


def test_terminal_flag_must_agree_with_final_state(prereg: dict[str, Any], tmp_path: Path) -> None:
    n = int(vr.threshold(prereg, "games_attempted_min"))
    games = _fake_games(n, terminal=1)
    games[0]["final_state"] = "NOT_FINISHED"  # still flagged terminal
    _write_g1_run(tmp_path, prereg, "run_a", 1, games, [])
    result = vr.check_games_attempted_and_terminal(prereg, tmp_path)
    assert not result.passed
    assert any("disagrees" in p for p in result.observed["problems"])


# ------------------------------------------------------------------ exclusion nesting


def test_exclusion_nesting_passes_for_flat_scalar_exclusions(
    prereg: dict[str, Any], tmp_path: Path, excluded: frozenset[str]
) -> None:
    _write_g1_run(tmp_path, prereg, "run_a", 1, _fake_games(1), [])
    result = vr.check_exclusion_nesting(prereg, tmp_path, excluded)
    assert result.passed, result.observed
    assert {h["key"] for h in result.observed["hits"]["run_a"]} >= {"run_id", "created_utc"}


def test_exclusion_nesting_fails_on_nested_excluded_key(
    prereg: dict[str, Any], tmp_path: Path, excluded: frozenset[str]
) -> None:
    _write_g1_run(
        tmp_path, prereg, "run_a", 1, _fake_games(1), [],
        results_overrides={"results": {"operation_mode": "OFFLINE", "network_guard": "NetworkGuard",
                                       "games": _fake_games(1), "wallclock_seconds": 3.0}},
    )
    result = vr.check_exclusion_nesting(prereg, tmp_path, excluded)
    assert not result.passed
    assert any("depth" in p for p in result.observed["problems"])


def test_exclusion_nesting_fails_on_container_valued_excluded_key(
    prereg: dict[str, Any], tmp_path: Path, excluded: frozenset[str]
) -> None:
    _write_g1_run(tmp_path, prereg, "run_a", 1, _fake_games(1), [],
                  results_overrides={"hardware": {"steps": 12}})
    result = vr.check_exclusion_nesting(prereg, tmp_path, excluded)
    assert not result.passed
    assert any("container" in p for p in result.observed["problems"])


# ------------------------------------------------------------------ replay


def test_replay_identity_passes_on_real_ls20(
    prereg: dict[str, Any], tmp_path: Path, ls20_recording: dict[str, Any]
) -> None:
    g, t = ls20_recording["game"], ls20_recording["transitions"]
    _write_g1_run(tmp_path, prereg, "run_a", 12345, [g], t)
    result = vr.check_replay_final_frame_identity(prereg, tmp_path, ROOT)
    assert result.passed, result.observed
    assert result.observed["identity"] == 1.0
    assert result.observed["network_attempts"] == 0
    assert result.observed["runs"]["run_a"]["replayed_steps"] == g["steps_taken"]


def test_replay_divergence_fails(
    prereg: dict[str, Any], tmp_path: Path, ls20_recording: dict[str, Any]
) -> None:
    g = dict(ls20_recording["game"])
    g["final_frame_sha256"] = "f" * 64
    _write_g1_run(tmp_path, prereg, "run_a", 12345, [g], ls20_recording["transitions"])
    result = vr.check_replay_final_frame_identity(prereg, tmp_path, ROOT)
    assert not result.passed
    assert result.observed["divergent"] == [f"run_a/{g['game_id']}"]
    assert result.observed["runs"]["run_a"]["divergent"][0]["replayed"] == (
        ls20_recording["game"]["final_frame_sha256"]
    )


def test_replay_detects_truncated_transition_log(
    prereg: dict[str, Any], tmp_path: Path, ls20_recording: dict[str, Any]
) -> None:
    # The dropped action is the ACTION6 click, which ls20 (a keyboard game) ignores, so the
    # final frame is unchanged and the digest alone would not notice. The verifier must still
    # fail on the transition count disagreeing with steps_taken.
    g = ls20_recording["game"]
    _write_g1_run(tmp_path, prereg, "run_a", 12345, [g], ls20_recording["transitions"][:-1])
    result = vr.check_replay_final_frame_identity(prereg, tmp_path, ROOT)
    assert not result.passed
    assert any("steps_taken" in p for p in result.observed["problems"])


def test_replay_unknown_game_is_divergent(prereg: dict[str, Any], tmp_path: Path) -> None:
    g = _fake_games(1)[0]
    g["steps_taken"] = 0
    _write_g1_run(tmp_path, prereg, "run_a", 1, [g], [])
    result = vr.check_replay_final_frame_identity(prereg, tmp_path, ROOT)
    assert not result.passed
    assert "returned None" in result.observed["runs"]["run_a"]["divergent"][0]["reason"]


def test_replay_ignores_incomplete_runs(
    prereg: dict[str, Any], tmp_path: Path, ls20_recording: dict[str, Any]
) -> None:
    g, t = ls20_recording["game"], ls20_recording["transitions"]
    _write_g1_run(tmp_path, prereg, "run_a", 12345, [g], t,
                  manifest_overrides={"completion_status": "failed"})
    result = vr.check_replay_final_frame_identity(prereg, tmp_path, ROOT)
    assert not result.passed
    assert result.observed["games_attempted"] == 0


# ------------------------------------------------------------------ throughput


def test_throughput_passes_above_threshold(prereg: dict[str, Any], tmp_path: Path) -> None:
    _write_g1_run(tmp_path, prereg, "run_a", 1, _fake_games(1), [])
    result = vr.check_throughput(prereg, tmp_path)
    assert result.passed, result.observed


def test_throughput_fails_below_fps_threshold(prereg: dict[str, Any], tmp_path: Path) -> None:
    fps_min = float(vr.threshold(prereg, "throughput_fps_min"))
    _write_g1_run(tmp_path, prereg, "run_a", 1, _fake_games(1), [], fps=fps_min / 2)
    result = vr.check_throughput(prereg, tmp_path)
    assert not result.passed
    assert any("fps below" in p for p in result.observed["problems"])


def test_throughput_fails_on_too_few_steps(prereg: dict[str, Any], tmp_path: Path) -> None:
    steps_min = int(vr.threshold(prereg, "throughput_min_steps_measured"))
    _write_g1_run(tmp_path, prereg, "run_a", 1, _fake_games(1), [], steps=steps_min - 1)
    result = vr.check_throughput(prereg, tmp_path)
    assert not result.passed
    assert any("steps measured" in p for p in result.observed["problems"])


def test_throughput_fails_when_stated_fps_disagrees(prereg: dict[str, Any], tmp_path: Path) -> None:
    fps_min = float(vr.threshold(prereg, "throughput_fps_min"))
    _write_g1_run(tmp_path, prereg, "run_a", 1, _fake_games(1), [],
                  fps=fps_min / 2, stated_fps=fps_min * 4)
    result = vr.check_throughput(prereg, tmp_path)
    assert not result.passed
    assert any("stated fps" in p for p in result.observed["problems"])


def test_run_completeness_requires_throughput_json(prereg: dict[str, Any], tmp_path: Path) -> None:
    run = _write_g1_run(tmp_path, prereg, "run_a", 1, _fake_games(1), [])
    extra = tuple(prereg["verification"]["additional_run_artifacts"])
    assert vr.check_run_completeness(tmp_path, extra).passed
    (run / "throughput.json").unlink()
    result = vr.check_run_completeness(tmp_path, extra)
    assert not result.passed
    assert "run_a: missing throughput.json" in result.observed["problems"]


# ------------------------------------------------------------------ digest definition


def test_canonical_frame_digest_matches_preregistered_encoding(prereg: dict[str, Any]) -> None:
    spec = prereg["primary_metric"]["canonical_frame_digest"]
    assert 'separators (",", ":")' in spec
    frames = [[[0, 1], [2, 3]]]
    expected = hashlib.sha256(
        json.dumps({"state": "WIN", "levels_completed": 2, "win_levels": 2, "frames": frames},
                   separators=(",", ":")).encode()
    ).hexdigest()
    assert ai.canonical_frame_digest("WIN", 2, 2, frames) == expected
    # numpy grids and plain lists digest identically
    import numpy as np

    assert ai.canonical_frame_digest("WIN", 2, 2, [np.array(frames[0], dtype=np.int8)]) == expected


def test_replay_is_deterministic_across_fresh_arcades(ls20_recording: dict[str, Any]) -> None:
    g = ls20_recording["game"]
    actions = [ai.ActionRecord.from_mapping(t) for t in ls20_recording["transitions"]]
    with NetworkGuard(0):
        a = ai.replay_actions(ENV_DIR, g["game_id"], g["seed"], actions)
        b = ai.replay_actions(ENV_DIR, g["game_id"], g["seed"], actions)
    assert a.succeeded and b.succeeded
    assert a.final_digest == b.final_digest == g["final_frame_sha256"]


def test_make_environment_raises_instead_of_returning_none() -> None:
    with NetworkGuard(0):
        arcade = ai.open_offline_arcade(ENV_DIR)
        with pytest.raises(ai.EnvironmentLoadError):
            ai.make_environment(arcade, "zzzz-00000000", 1)
