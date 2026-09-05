"""Unit tests for the G3 evaluator's E310 checks in scripts/verify_run.py.

Every number a test compares against is read from the real ``preregistration/G3.yaml``
through the verifier's own ``threshold()``. The checks are exercised on synthetic E310 run
directories built at full scale (25 games x 10 wrong-model trials + 1 control, the games and
their digests taken from the committed G1 history run) so the pass case is a real pass; each
threshold then gets one failing case produced by mutating a private copy of the runs, with
results.json rebuilt to agree with the mutated records so the failure comes from the
threshold, not from the agreement check. The agreement check gets its own failing case.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from arc_plasticity.hypotheses import backtest as bt
from arc_plasticity.hypotheses import mutations as mu

ROOT = Path(__file__).resolve().parents[2]
G1_RUN = ROOT / "artifacts" / "E100_arc_interface" / "20260904T074939Z_seed12345_8383cad8"

pytestmark = pytest.mark.skipif(
    not (G1_RUN / "results.json").exists(), reason="the graded G1 history run is absent"
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

Hyp = dict[str, Any]
Trial = dict[str, Any]
Edit = Callable[[list[Hyp], list[Trial], dict[str, Any]], None]


@pytest.fixture(scope="module")
def prereg() -> dict[str, Any]:
    data: dict[str, Any]
    data, _, _ = vr.load_preregistration("G3", ROOT)
    return data


@pytest.fixture(scope="module")
def excluded(prereg: dict[str, Any]) -> frozenset[str]:
    g0, _, _ = vr.load_preregistration("G0", ROOT)
    _, names = vr.check_nondeterministic_fields(
        vr._g3_e310_view(prereg), ROOT, bounds=g0["determinism_protocol"]
    )
    return names


# ------------------------------------------------------------------ synthetic E310 runs


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _g1_games() -> list[dict[str, Any]]:
    doc = json.loads((G1_RUN / "results.json").read_text())
    return list(doc["results"]["games"])


def _history_source() -> dict[str, Any]:
    manifest = json.loads((G1_RUN / "manifest.json").read_text())
    return {
        "transitions_path": str((G1_RUN / "transitions.jsonl").relative_to(ROOT)),
        "transitions_sha256": _sha(G1_RUN / "transitions.jsonl"),
        "sha256sums_sha256": _sha(G1_RUN / "SHA256SUMS"),
        "results_sha256": _sha(G1_RUN / "results.json"),
        "environment_seed": manifest["seed"],
        "history_run_id": manifest["run_id"],
    }


def _games() -> list[dict[str, Any]]:
    return [
        {
            "game_index": i,
            "game_id": g["game_id"],
            "history_length": g["steps_taken"],
            "final_frame_sha256_expected": g["final_frame_sha256"],
            "final_frame_sha256_replayed": g["final_frame_sha256"],
            "frame_digest_mismatches": 0,
            "replay_identity": True,
        }
        for i, g in enumerate(_g1_games())
    ]


def _trials(games: list[dict[str, Any]], class_offset: int) -> tuple[list[Hyp], list[Trial]]:
    classes = list(mu.MUTATION_CLASSES)
    live = {
        "backtest_module_sha256": bt.backtest_module_sha256(),
        "interface_sha256": bt.interface_sha256(),
    }
    hyps: list[Hyp] = []
    trials: list[Trial] = []
    for game in games:
        length = int(game["history_length"])
        for trial_index in range(11):
            control = trial_index == 10
            cls = (
                None
                if control
                else classes[(game["game_index"] * 10 + trial_index + class_offset) % 8]
            )
            base = {
                "game_index": game["game_index"],
                "game_id": game["game_id"],
                "trial_index": trial_index,
                "kind": "control" if control else "wrong_model",
                "mutation_class": cls,
            }
            trials.append(
                {
                    **base,
                    "mutation_params": {},
                    "redraws": 0,
                    "vacuous": False,
                    "discrimination_index": None if control else 0,
                    "discrimination_field": None if control else "frame",
                    "backtested": True,
                    "certified": control,
                    "rejected": not control,
                    "history_length": length,
                    "history_length_checked": length,
                    "mismatches": 0 if control else 1,
                    "first_mismatch_index": None if control else 0,
                    "failure_kind": None,
                    "notes": [],
                }
            )
            hyps.append(
                {
                    **base,
                    **live,
                    "backtester": "full_history_exact",
                    "certification_fields": ["frame", "state", "levels_completed"],
                    "certified": control,
                    "mismatches": 0 if control else 1,
                    "history_length": length,
                    "history_length_checked": length,
                    "first_mismatch_index": None if control else 0,
                    "failure_kind": None,
                    "reason": None,
                    "failed_at_index": None,
                }
            )
    return hyps, trials


def _summarize(hyps: list[Hyp], trials: list[Trial]) -> dict[str, Any]:
    """The runner's summary arithmetic, on records (the verifier recomputes the same)."""
    table = {(t["game_id"], t["trial_index"]): t for t in trials}

    def vacuous(h: Hyp) -> bool:
        return bool(table[(h["game_id"], h["trial_index"])]["vacuous"])

    wrong = [h for h in hyps if h["kind"] == "wrong_model"]
    controls = [h for h in hyps if h["kind"] == "control"]
    non_vacuous = [h for h in wrong if not vacuous(h)]
    rejected = [h for h in non_vacuous if not h["certified"]]
    per_class: dict[str, dict[str, Any]] = {}
    for cls in mu.MUTATION_CLASSES:
        ct = [h for h in wrong if h["mutation_class"] == cls]
        cnv = [h for h in ct if not vacuous(h)]
        cr = [h for h in cnv if not h["certified"]]
        per_class[cls] = {
            "trials": len(ct),
            "vacuous_trials": len(ct) - len(cnv),
            "non_vacuous_trials": len(cnv),
            "rejected_trials": len(cr),
            "rejection_fraction": (len(cr) / len(cnv)) if cnv else None,
            "redraws_total": 0,
            "vacuous_rejected_anyway": 0,
        }
    accepted = [h for h in controls if h["certified"]]
    unequal = [h for h in hyps if h["history_length_checked"] != h["history_length"]]
    return {
        "wrong_model_trials": len(wrong),
        "vacuous_trials": len(wrong) - len(non_vacuous),
        "non_vacuous_trials": len(non_vacuous),
        "rejected_trials": len(rejected),
        "rejection_fraction": (len(rejected) / len(non_vacuous)) if non_vacuous else None,
        "rejection_denominator": "non_vacuous_trials",
        "mutation_classes": list(mu.MUTATION_CLASSES),
        "mutation_classes_used": sorted(
            {h["mutation_class"] for h in wrong if h["mutation_class"]}
        ),
        "per_class": per_class,
        "control_trials": len(controls),
        "control_accepted": len(accepted),
        "correct_model_acceptance_fraction": (len(accepted) / len(controls)) if controls else None,
        "trials_backtested": len(hyps),
        "history_length_checked_equal_length_all": not unequal,
        "history_length_checked_unequal_trials": [
            {"game_id": h["game_id"], "trial_index": h["trial_index"], "kind": h["kind"]}
            for h in unequal
        ],
        "failure_kinds": sorted({h["failure_kind"] for h in hyps if h["failure_kind"]}),
    }


def _results(
    prereg: dict[str, Any],
    seed: int,
    games: list[dict[str, Any]],
    hyps: list[Hyp],
    trials: list[Trial],
) -> dict[str, Any]:
    limits = {key: vr.threshold(prereg, name) for key, name in vr.G3_E310_LIMIT_THRESHOLDS}
    return {
        "environment_generator_version": "arc-agi-offline-cache-1.0.0",
        "operation_mode": "OFFLINE",
        "network_guard": "NetworkGuard",
        "history_source": _history_source(),
        **_summarize(hyps, trials),
        "seed": seed,
        "trial_seeds_per_game": 10,
        "control_trials_per_game": 1,
        "redraw_max": 20,
        "class_assignment": "balanced_blocks",
        "backtester": "full_history_exact",
        "backtest_limits": {
            "backtest_seconds_max": float(limits["backtest_seconds_max"]),
            "predict_seconds_max": float(limits["predict_seconds_max"]),
            "address_space_bytes_max": int(limits["address_space_bytes_max"]),
        },
        "certification_fields": ["frame", "state", "levels_completed"],
        "games": games,
        "replay_identity_games": sum(1 for g in games if g["replay_identity"]),
        "replay_divergent_games": sum(1 for g in games if not g["replay_identity"]),
        "backtest_module_sha256": bt.backtest_module_sha256(),
        "interface_sha256": bt.interface_sha256(),
    }


def _manifest(run_id: str, seed: int) -> dict[str, Any]:
    return {
        "experiment_id": "E310_ref_backtest_rejection",
        "run_id": run_id,
        "timestamp_utc": "2026-09-04T17:00:00Z",
        "git_commit": "0" * 40,
        "git_dirty": False,
        "python_version": "3.12.13",
        "dependency_lock_hash": "0" * 64,
        "config_hash": "1" * 64,
        "environment_generator_version": "arc-agi-offline-cache-1.0.0",
        "seed": seed,
        "model_identifier": None,
        "prompt_hash": None,
        "action_budget": 0,
        "simulation_budget": 5000000,
        "token_budget": 0,
        "persistent_state_size_cap": 0,
        "hardware": "synthetic",
        "wallclock_limit_seconds": 3600,
        "wallclock_seconds": 1.0,
        "completion_status": "completed",
        "network_calls_allowed": 0,
        "network_attempts": 0,
        "model_calls_allowed": 0,
        "model_calls": 0,
    }


def _reseal(run: Path) -> None:
    lines = []
    for p in sorted(x for x in run.rglob("*") if x.is_file() and x.name != "SHA256SUMS"):
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(run)}")
    (run / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def _write_records(
    run: Path, hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]
) -> None:
    (run / "transitions.jsonl").write_text(
        "".join(json.dumps(t, sort_keys=True) + "\n" for t in trials)
    )
    (run / "hypotheses.jsonl").write_text(
        "".join(json.dumps(h, sort_keys=True) + "\n" for h in hyps)
    )
    doc = json.loads((run / "results.json").read_text()) if (run / "results.json").exists() else {}
    doc.update(
        {
            "experiment_id": "E310_ref_backtest_rejection",
            "run_id": run.name,
            "seed": results["seed"],
            "created_utc": doc.get("created_utc", f"2026-09-04T17:00:0{results['seed'] % 10}Z"),
            "config_hash": "1" * 64,
            "completion_status": "completed",
            "wallclock_seconds": 1.0,
            "results": results,
            "extra": {},
        }
    )
    (run / "results.json").write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n")
    rows = [
        ("games", len(results["games"])),
        ("wrong_model_trials", results["wrong_model_trials"]),
        ("vacuous_trials", results["vacuous_trials"]),
        ("rejected_trials", results["rejected_trials"]),
        ("rejection_fraction", results["rejection_fraction"]),
        ("control_trials", results["control_trials"]),
        ("control_accepted", results["control_accepted"]),
    ]
    with (run / "metrics.csv").open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        writer.writerows(rows)


def _write_run(
    root: Path, run_id: str, seed: int, prereg: dict[str, Any], class_offset: int = 0
) -> Path:
    run = root / run_id
    run.mkdir(parents=True)
    games = _games()
    hyps, trials = _trials(games, class_offset)
    results = _results(prereg, seed, games, hyps, trials)
    (run / "manifest.json").write_text(json.dumps(_manifest(run_id, seed), indent=1))
    for name, content in {
        "resolved_config.yaml": f"seed: {seed}\n",
        "environment_results.csv": "environment,history_length\n",
        "memory_operations.jsonl": "",
        "stdout.log": "ok\n",
        "stderr.log": "",
        "git_state.txt": "clean\n",
        "environment_info.json": "{}",
    }.items():
        (run / name).write_text(content)
    _write_records(run, hyps, trials, results)
    _reseal(run)
    return run


def _rebuild(run: Path, edit: Edit) -> None:
    """Apply ``edit`` to the records and results, then recompute the summary so results.json
    agrees with the records (the failure must come from a threshold)."""
    hyps = [json.loads(line) for line in (run / "hypotheses.jsonl").read_text().splitlines()]
    trials = [json.loads(line) for line in (run / "transitions.jsonl").read_text().splitlines()]
    results = json.loads((run / "results.json").read_text())["results"]
    edit(hyps, trials, results)
    results.update(_summarize(hyps, trials))
    results["replay_identity_games"] = sum(1 for g in results["games"] if g["replay_identity"])
    results["replay_divergent_games"] = len(results["games"]) - results["replay_identity_games"]
    _write_records(run, hyps, trials, results)
    _reseal(run)


def _edit_json(path: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    doc = json.loads(path.read_text())
    mutate(doc)
    path.write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n")


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory, prereg: dict[str, Any]) -> Path:
    root = tmp_path_factory.mktemp("g3world") / "E310_ref_backtest_rejection"
    proto = prereg["backtest_rejection_experiment"]["determinism_protocol"]
    for i in range(int(proto["identical_invocations"])):
        _write_run(root, f"fixed_{i}", int(proto["fixed_seed"]), prereg)
    _write_run(root, "contrast_0", int(proto["contrast_seed"]), prereg, class_offset=1)
    return root


@pytest.fixture
def runs(world: Path, tmp_path: Path) -> Path:
    dst = tmp_path / "E310_ref_backtest_rejection"
    shutil.copytree(world, dst)
    return dst


# ------------------------------------------------------------------ thresholds, dispatch


def test_every_g3_e310_threshold_is_read_from_the_preregistration(prereg: dict[str, Any]) -> None:
    for key in (
        "backtest_wrong_model_trials_min",
        "backtest_control_trials_min",
        "backtest_mutation_classes_min",
        "backtest_trials_per_class_min",
        "backtest_vacuous_trials_max",
        "backtest_rejection_fraction_min",
        "backtest_correct_model_acceptance_min",
        "backtest_history_min_length",
        "backtest_mismatches_for_certification_max",
        "backtest_must_cover_full_history",
        "sandbox_backtest_seconds_max",
        "sandbox_predict_seconds_max",
        "sandbox_address_space_bytes_max",
        "g1_history_run_sha256sums_sha256",
        "replay_final_frame_identity_min",
        "replay_divergent_games_max",
        "public_games_total",
        "cache_manifest_sha256",
        "cache_manifest_drift_files_max",
        "cached_games_required",
        "arc_agi_locked_version",
        "network_calls_allowed",
        "network_attempts_max",
        "determinism_identity_min",
        "contrast_seed_must_differ",
        "excluded_key_max_depth",
        "excluded_key_container_values_allowed",
    ):
        assert vr.threshold(prereg, key) is not None


def test_g3_checks_raise_without_thresholds(prereg: dict[str, Any], tmp_path: Path) -> None:
    stripped = {**prereg, "thresholds": {}}
    with pytest.raises(vr.PreregistrationError):
        vr.check_backtest_rejection(stripped, tmp_path, ROOT)
    with pytest.raises(vr.PreregistrationError):
        vr.check_cache_manifest_locked(stripped, ROOT)
    with pytest.raises(vr.PreregistrationError):
        vr.check_determinism(vr._g3_e310_view(stripped), tmp_path, frozenset())


def test_g3_is_dispatched_and_the_e310_protocol_is_hoisted(prereg: dict[str, Any]) -> None:
    assert vr.GATE_EVALUATORS["G3"] is vr.evaluate_g3
    view = vr._g3_e310_view(prereg)
    assert (
        view["determinism_protocol"]
        is prereg["backtest_rejection_experiment"]["determinism_protocol"]
    )
    assert "determinism_protocol" not in prereg
    broken = copy.deepcopy(prereg)
    del broken["backtest_rejection_experiment"]["determinism_protocol"]
    with pytest.raises(vr.PreregistrationError, match="determinism_protocol"):
        vr._g3_e310_view(broken)


def test_pending_e300_checks_are_failures_not_skips(tmp_path: Path) -> None:
    for name, needs in vr.G3_E300_PENDING_CHECKS:
        check = vr._pending_e300_check(name, needs, tmp_path / "E300_ref")
        assert check.name == name and not check.passed and not check.skipped
        assert check.observed["status"] == "not_yet_evaluable"


# ------------------------------------------------------------------ cache manifest


def test_cache_manifest_locked_passes_on_the_real_tree_and_fails_on_a_wrong_digest(
    prereg: dict[str, Any],
) -> None:
    ok = vr.check_cache_manifest_locked(prereg, ROOT)
    assert ok.passed, ok.observed["problems"]
    assert ok.observed["sha256"] == vr.threshold(prereg, "cache_manifest_sha256")
    wrong = copy.deepcopy(prereg)
    wrong["thresholds"]["cache_manifest_sha256"] = "0" * 64
    bad = vr.check_cache_manifest_locked(wrong, ROOT)
    assert not bad.passed and any("!= locked" in p for p in bad.observed["problems"])


# ------------------------------------------------------------------ E310 pass case


def test_backtest_rejection_passes_on_the_synthetic_world(
    prereg: dict[str, Any], world: Path
) -> None:
    result = vr.check_backtest_rejection(prereg, world, ROOT)
    assert result.passed, result.observed["problems"]
    for name in ("fixed_0", "fixed_1", "contrast_0"):
        row = result.observed["runs"][name]
        assert row["games"] == vr.threshold(prereg, "public_games_total")
        assert row["replay_identity"] == 1.0 and row["divergent"] == []
        assert row["wrong_model_trials"] == 250 and row["control_trials"] == 25
        assert row["rejection_fraction"] == 1.0 and row["correct_model_acceptance_fraction"] == 1.0
        assert len(row["per_class"]) == 8 and all(
            c["trials"] >= 31 for c in row["per_class"].values()
        )
    assert (
        result.threshold["g1_history_run_sha256sums_sha256"]
        == _history_source()["sha256sums_sha256"]
    )
    assert any("E100_arc_interface" in e for e in result.evidence)


def test_offline_run_e310_uses_the_experiment_model_allowance(
    prereg: dict[str, Any], runs: Path
) -> None:
    allowed = int(prereg["backtest_rejection_experiment"]["model_calls_allowed"])
    ok = vr.check_offline_run(prereg, runs, model_allowed=allowed)
    assert ok.passed, ok.observed["problems"]
    with pytest.raises(vr.PreregistrationError):  # G3 thresholds carry no model_calls_allowed
        vr.check_offline_run(prereg, runs)
    _edit_json(runs / "fixed_0" / "manifest.json", lambda d: d.__setitem__("model_calls", 1))
    bad = vr.check_offline_run(prereg, runs, model_allowed=allowed)
    assert not bad.passed and any("model_calls 1" in p for p in bad.observed["problems"])


def test_completeness_and_sha256sums_pass_on_the_world(prereg: dict[str, Any], world: Path) -> None:
    assert vr.check_run_completeness(world).passed
    assert vr.check_sha256sums(prereg, world).passed


# ------------------------------------------------------------------ one failing case per threshold


def _drop_game_wrong_trials(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
    game = results["games"][0]["game_id"]
    hyps[:] = [h for h in hyps if not (h["game_id"] == game and h["kind"] == "wrong_model")]
    trials[:] = [t for t in trials if not (t["game_id"] == game and t["kind"] == "wrong_model")]


def _drop_one_control(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
    hyps[:] = [h for h in hyps if h["kind"] != "control" or h["game_index"] != 0]
    trials[:] = [t for t in trials if t["kind"] != "control" or t["game_index"] != 0]


def _merge_two_classes(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
    for rec in (*hyps, *trials):
        if rec["mutation_class"] == "stale_frame":
            rec["mutation_class"] = "identity_model"


def _thin_one_class(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
    # The synthetic world assigns classes round-robin, so the first 12 games hold exactly
    # 15 single_cell_flip trials of 31 or 32; moving them leaves the class under the locked
    # per-class minimum of 20 (both record lists must move together to stay joinable).
    moved = 0
    for rec in (*hyps, *trials):
        if rec["mutation_class"] == "single_cell_flip" and rec["game_index"] < 12:
            rec["mutation_class"] = "colour_permutation"
            moved += 1
    assert moved == 30, moved  # 15 trials x (hypotheses record + transitions record)


def _mark_vacuous(n: int) -> Edit:
    def edit(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
        wrong = [t for t in trials if t["kind"] == "wrong_model"]
        for t in wrong[:n]:
            t["vacuous"] = True
            t["notes"] = ["non-discriminating after re-draws; excluded from the denominator"]

    return edit


def _accept_wrong(n: int) -> Edit:
    def edit(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
        for h in [h for h in hyps if h["kind"] == "wrong_model"][:n]:
            h.update({"certified": True, "mismatches": 0, "first_mismatch_index": None})
        table = {(h["game_id"], h["trial_index"]): h for h in hyps}
        for t in trials:
            h = table[(t["game_id"], t["trial_index"])]
            t["certified"], t["rejected"], t["mismatches"] = (
                h["certified"],
                not h["certified"],
                h["mismatches"],
            )

    return edit


def _reject_one_control(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
    h = next(h for h in hyps if h["kind"] == "control")
    h.update({"certified": False, "mismatches": 1, "first_mismatch_index": 0})


def _shorten_one_history(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
    results["games"][0]["history_length"] = 1


def _wrong_history_digest(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
    results["history_source"]["sha256sums_sha256"] = "0" * 64


def _diverge_one_game(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
    game = results["games"][0]
    game["final_frame_sha256_replayed"] = "f" * 64
    game["replay_identity"] = False
    game["frame_digest_mismatches"] = 3


def _loosen_limit(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
    results["backtest_limits"]["backtest_seconds_max"] += 1


def _other_module(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
    results["backtest_module_sha256"] = "0" * 64
    for h in hyps:
        h["backtest_module_sha256"] = "0" * 64


def _inconsistent_certification(
    hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]
) -> None:
    h = next(h for h in hyps if h["kind"] == "wrong_model")
    h["certified"] = True  # mismatches stays 1


def _partial_certification(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
    h = next(h for h in hyps if h["kind"] == "control")
    h["history_length_checked"] = h["history_length"] - 1  # certified stays True


def _unbacktested_trial(hyps: list[Hyp], trials: list[Trial], results: dict[str, Any]) -> None:
    del hyps[0]


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (_drop_game_wrong_trials, "wrong-model trials 240 <"),
        (_drop_one_control, "control trials 24 <"),
        (_merge_two_classes, "7 mutation classes <"),
        (_thin_one_class, "class single_cell_flip has"),
        (_mark_vacuous(13), "vacuous trials 13 >"),
        (_accept_wrong(13), "rejection fraction 0.948 <"),
        (_reject_one_control, "correct-model acceptance 0.96 <"),
        (_shorten_one_history, "history_length 1 <"),
        (_wrong_history_digest, "recorded history sha256sums_sha256 != locked"),
        (_diverge_one_game, "replay identity 0.96 <"),
        (_loosen_limit, "backtest_limits.backtest_seconds_max"),
        (_other_module, "!= live module"),
        (_inconsistent_certification, "certified flag does not follow"),
        (_partial_certification, "certifications on a partial history"),
        (_unbacktested_trial, "every trial must be backtested"),
    ],
    ids=lambda x: getattr(x, "__name__", None) or str(x),
)
def test_backtest_rejection_fails_one_threshold_at_a_time(
    prereg: dict[str, Any], runs: Path, edit: Edit, expected: str
) -> None:
    _rebuild(runs / "fixed_0", edit)
    result = vr.check_backtest_rejection(prereg, runs, ROOT)
    assert not result.passed
    assert any(expected in p for p in result.observed["problems"]), result.observed["problems"]


def test_backtest_rejection_fails_when_results_disagree_with_the_records(
    prereg: dict[str, Any], runs: Path
) -> None:
    run = runs / "fixed_0"
    _edit_json(run / "results.json", lambda d: d["results"].__setitem__("rejected_trials", 251))
    _reseal(run)
    result = vr.check_backtest_rejection(prereg, runs, ROOT)
    assert not result.passed
    assert any(
        "results rejected_trials 251 != recomputed 250" in p for p in result.observed["problems"]
    )


def test_backtest_rejection_fails_on_a_tampered_history_run(
    prereg: dict[str, Any], runs: Path, tmp_path: Path
) -> None:
    """The G1 run is located from the record but bound to the locked digest: a copy whose
    transitions were edited (and re-sealed) is not the pre-registered history."""
    copy_dir = tmp_path / "g1copy"
    shutil.copytree(G1_RUN, copy_dir)
    original = (copy_dir / "transitions.jsonl").read_text()
    tampered = original.replace('"action":1,', '"action":2,', 1)  # the G1 log is compact JSON
    assert tampered != original, "the tamper must change the history"
    (copy_dir / "transitions.jsonl").write_text(tampered)
    _reseal(copy_dir)
    assert _sha(copy_dir / "SHA256SUMS") != _sha(G1_RUN / "SHA256SUMS")
    run = runs / "fixed_0"

    def point_at_copy(d: dict[str, Any]) -> None:
        src = d["results"]["history_source"]
        src["transitions_path"] = str(copy_dir / "transitions.jsonl")
        src["transitions_sha256"] = _sha(copy_dir / "transitions.jsonl")
        src["sha256sums_sha256"] = _sha(copy_dir / "SHA256SUMS")

    _edit_json(run / "results.json", point_at_copy)
    _reseal(run)
    result = vr.check_backtest_rejection(prereg, runs, ROOT)
    assert not result.passed
    assert any("SHA256SUMS sha256" in p and "!= locked" in p for p in result.observed["problems"])


def test_backtest_rejection_fails_with_no_completed_run(
    prereg: dict[str, Any], tmp_path: Path
) -> None:
    result = vr.check_backtest_rejection(prereg, tmp_path / "empty", ROOT)
    assert not result.passed and any("no completed run" in p for p in result.observed["problems"])


# ------------------------------------------------------------------ nesting and determinism


def test_exclusion_nesting_rejects_a_nested_run_id(
    prereg: dict[str, Any], runs: Path, excluded: frozenset[str]
) -> None:
    """The defect the first three graded runs had (ledger G3.3 failure, 2026-09-04)."""
    ok = vr.check_exclusion_nesting(prereg, runs, excluded)
    assert ok.passed, ok.observed["problems"]
    run = runs / "fixed_0"
    _edit_json(
        run / "results.json",
        lambda d: d["results"]["history_source"].__setitem__("run_id", "g1"),
    )
    _reseal(run)
    bad = vr.check_exclusion_nesting(prereg, runs, excluded)
    assert not bad.passed
    assert any("'run_id' at depth 3 > 1" in p for p in bad.observed["problems"])


def test_determinism_e310_passes_and_detects_both_failures(
    prereg: dict[str, Any], runs: Path, excluded: frozenset[str]
) -> None:
    view = vr._g3_e310_view(prereg)
    ok = vr.check_determinism(view, runs, excluded)
    assert ok.passed, ok.observed["problems"]
    assert ok.observed["identity"] == 1.0 and ok.observed["contrast_differs"] is True
    assert "run_id" in ok.observed["excluded_fields"]

    same_seed = copy.deepcopy(ok)
    _edit_json(
        runs / "fixed_1" / "results.json",
        lambda d: d["results"].__setitem__("rejected_trials", 249),
    )
    _reseal(runs / "fixed_1")
    bad = vr.check_determinism(view, runs, excluded)
    assert not bad.passed and bad.observed["identity"] == 0.0
    assert same_seed.observed["identity"] == 1.0

    shutil.rmtree(runs / "fixed_1")
    shutil.copytree(runs / "fixed_0", runs / "fixed_1")
    shutil.rmtree(runs / "contrast_0")
    shutil.copytree(runs / "fixed_0", runs / "contrast_0")
    _edit_json(runs / "contrast_0" / "manifest.json", lambda d: d.__setitem__("seed", 12346))
    _reseal(runs / "contrast_0")
    no_contrast = vr.check_determinism(view, runs, excluded)
    assert not no_contrast.passed and no_contrast.observed["contrast_differs"] is False


# ------------------------------------------------------------------ evaluate_g3 end to end


def test_evaluate_g3_orders_the_checks_and_fails_the_pending_e300_ones(
    prereg: dict[str, Any], world: Path, tmp_path: Path
) -> None:
    view = copy.deepcopy(prereg)
    view["verification"]["secondary_artifacts_root"] = str(world)
    checks = vr.evaluate_g3(view, tmp_path / "E300_ref", ROOT, skip_tooling=True)
    names = [c.name for c in checks]
    # G3.6b step 15: the successor overlay leads when preregistration/G3b.yaml exists, and
    # the graded-set checks run for real (over an empty root here) instead of the pending
    # placeholders; the E310 checks keep their order.
    overlay = ["successor_preregistration_overlay"] if vr.load_g3_successor(ROOT) else []
    assert names[: len(overlay) + 5] == overlay + [
        "cache_manifest_locked",
        "run_set_manifest",
        "run_artifact_completeness",
        "run_artifact_completeness_e310",
        "sha256sums_verify",
    ]
    assert names.index("sha256sums_verify_e310") < names.index("offline_run_e310")
    assert names.index("backtest_rejection") < names.index("preflight_recorded")
    assert names.index("exclusion_nesting_e310") < names.index("determinism_identity_e310")
    by_name = {c.name: c for c in checks}
    for name, _ in vr.G3_E300_PENDING_CHECKS:
        if name == "preflight_recorded":
            continue  # reads state/BUDGET.json and the preserved E300 runs, not the empty root
        assert not by_name[name].passed and not by_name[name].skipped
    for name in (
        "cache_manifest_locked",
        "run_artifact_completeness_e310",
        "sha256sums_verify_e310",
        "offline_run_e310",
        "backtest_rejection",
        "exclusion_nesting_e310",
        "nondeterministic_fields_within_bounds",
        "determinism_identity_e310",
    ):
        assert by_name[name].passed, (name, by_name[name].observed)
    assert (
        by_name["nondeterministic_fields_within_bounds"]
        .threshold["bounds_source"]["preregistration"]
        .endswith("G0.yaml")
    )
    report = vr.Report("G3", "x", "y", checks)
    assert not report.passed  # the pending E300 checks keep an incomplete G3 from passing
