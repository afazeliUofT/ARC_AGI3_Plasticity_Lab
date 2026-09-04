"""Unit tests for scripts/verify_run.py.

They exercise the pure check functions against synthetic run directories so that no real
artifact is needed, and they exercise the real preregistration/G0.yaml and
configs/nondeterministic_fields.yaml so that a drift between the two is caught here first.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_run", ROOT / "scripts" / "verify_run.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(mod)
    return mod


vr = _load_module()


@pytest.fixture(scope="module")
def prereg() -> dict[str, Any]:
    data: dict[str, Any]
    data, _, _ = vr.load_preregistration("G0", ROOT)
    return data


def _manifest(seed: int, run_id: str, status: str = "completed") -> dict[str, Any]:
    m: dict[str, Any] = {k: "x" for k in vr.REQUIRED_MANIFEST_KEYS}
    m.update({"seed": seed, "run_id": run_id, "completion_status": status})
    return m


def _write_run(
    root: Path,
    run_id: str,
    seed: int,
    value: float,
    *,
    status: str = "completed",
    omit_from_sums: str | None = None,
    corrupt_after_hash: str | None = None,
) -> Path:
    run = root / run_id
    run.mkdir(parents=True)
    files: dict[str, str] = {
        "manifest.json": json.dumps(_manifest(seed, run_id, status)),
        "resolved_config.yaml": f"seed: {seed}\n",
        "results.json": json.dumps(
            {
                "run_id": run_id,
                "created_utc": f"2026-09-04T00:00:0{seed % 10}Z",
                "score": value,
                "nested": {"wallclock_seconds": seed * 1.5, "levels": [{"hostname": run_id, "v": value}]},
            }
        ),
        "metrics.csv": f"run_id,metric,value,elapsed_seconds\n{run_id},score,{value},{seed}\n",
        "environment_results.csv": "env,score\ne,1\n",
        "transitions.jsonl": "",
        "hypotheses.jsonl": "",
        "memory_operations.jsonl": "",
        "stdout.log": "ok\n",
        "stderr.log": "",
        "git_state.txt": "clean\n",
        "environment_info.json": "{}",
    }
    for name, content in files.items():
        (run / name).write_text(content)
    lines = []
    for name in files:
        if name == omit_from_sums:
            continue
        digest = hashlib.sha256((run / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    (run / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    if corrupt_after_hash:
        (run / corrupt_after_hash).write_text("tampered\n")
    return run


# ------------------------------------------------------------------ pre-registration


def test_thresholds_are_read_from_the_preregistration(prereg: dict[str, Any]) -> None:
    for key in (
        "uv_sync_exit_code",
        "pytest_exit_code",
        "pytest_min_tests_collected",
        "ruff_exit_code",
        "mypy_exit_code",
        "determinism_identity_min",
        "contrast_seed_must_differ",
        "sha256sums_verified_fraction_min",
        "sha256sums_must_list_every_artifact_file",
        "git_status_porcelain_lines_max",
        "licence_required_text",
        "verify_on_machine_items_total",
        "verify_on_machine_items_resolved_min",
    ):
        assert vr.threshold(prereg, key) is not None


def test_missing_threshold_raises_instead_of_defaulting(prereg: dict[str, Any]) -> None:
    stripped = {**prereg, "thresholds": {}}
    with pytest.raises(vr.PreregistrationError):
        vr.check_licence(stripped, ROOT)


def test_preregistration_gate_mismatch_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "preregistration").mkdir()
    (tmp_path / "preregistration" / "G9.yaml").write_text("gate: G0\nthresholds: {}\n")
    with pytest.raises(vr.PreregistrationError):
        vr.load_preregistration("G9", tmp_path)


def test_verifier_source_has_no_gate_threshold_literals() -> None:
    # The only numbers permitted in the verifier are structural (buffer sizes, exit codes of
    # the shell helper, regex quantifiers). Gate thresholds must come from the pre-registration.
    src = (ROOT / "scripts" / "verify_run.py").read_text()
    for forbidden in ("12345", "12346", "1.15", "115.0"):
        assert forbidden not in src, f"gate literal {forbidden} hard-coded in verifier"


# ------------------------------------------------------------------ exclusion bounds


def test_real_nondeterministic_fields_are_within_bounds(prereg: dict[str, Any]) -> None:
    result, names = vr.check_nondeterministic_fields(prereg, ROOT)
    assert result.passed, result.observed
    assert {"run_id", "created_utc", "wallclock_seconds", "hostname"} <= names


def _write_fields_config(root: Path, excluded: dict[str, list[str]]) -> None:
    (root / "configs").mkdir(parents=True, exist_ok=True)
    (root / "configs" / "nondeterministic_fields.yaml").write_text(
        yaml.safe_dump(
            {
                "compared_files": ["results.json", "metrics.csv"],
                "excluded_fields": excluded,
                "never_excluded": ["seed", "config_hash"],
            }
        )
    )


def test_forbidden_name_in_exclusion_list_fails(prereg: dict[str, Any], tmp_path: Path) -> None:
    _write_fields_config(tmp_path, {"run_identifiers": ["run_id", "seed"]})
    result, _ = vr.check_nondeterministic_fields(prereg, tmp_path)
    assert not result.passed
    assert any("seed" in p for p in result.observed["problems"])


def test_unregistered_category_fails(prereg: dict[str, Any], tmp_path: Path) -> None:
    _write_fields_config(tmp_path, {"metric_values": ["score"]})
    result, _ = vr.check_nondeterministic_fields(prereg, tmp_path)
    assert not result.passed
    assert any("metric_values" in p for p in result.observed["problems"])


def test_hyphenated_forbidden_name_matches(prereg: dict[str, Any], tmp_path: Path) -> None:
    # "dependency-lock hash" in the pre-registration must catch dependency_lock_hash.
    _write_fields_config(tmp_path, {"timestamps": ["dependency_lock_hash"]})
    result, _ = vr.check_nondeterministic_fields(prereg, tmp_path)
    assert not result.passed


# ------------------------------------------------------------------ determinism


EXCLUDED = frozenset({"run_id", "created_utc", "wallclock_seconds", "hostname", "elapsed_seconds"})


def test_determinism_passes_when_same_seed_identical_and_contrast_differs(
    prereg: dict[str, Any], tmp_path: Path
) -> None:
    proto = prereg["determinism_protocol"]
    _write_run(tmp_path, "run_a", proto["fixed_seed"], 0.5)
    _write_run(tmp_path, "run_b", proto["fixed_seed"], 0.5)
    _write_run(tmp_path, "run_c", proto["contrast_seed"], 0.7)
    result = vr.check_determinism(prereg, tmp_path, EXCLUDED)
    assert result.passed, result.observed
    assert result.observed["identity"] == 1.0
    assert result.observed["contrast_differs"] is True


def test_determinism_fails_when_same_seed_differs(prereg: dict[str, Any], tmp_path: Path) -> None:
    proto = prereg["determinism_protocol"]
    _write_run(tmp_path, "run_a", proto["fixed_seed"], 0.5)
    _write_run(tmp_path, "run_b", proto["fixed_seed"], 0.6)
    _write_run(tmp_path, "run_c", proto["contrast_seed"], 0.7)
    result = vr.check_determinism(prereg, tmp_path, EXCLUDED)
    assert not result.passed
    assert result.observed["identity"] == 0.0


def test_determinism_fails_when_contrast_seed_is_identical(
    prereg: dict[str, Any], tmp_path: Path
) -> None:
    # An implementation that ignores its seed would pass identity trivially; the contrast run
    # is what catches it.
    proto = prereg["determinism_protocol"]
    _write_run(tmp_path, "run_a", proto["fixed_seed"], 0.5)
    _write_run(tmp_path, "run_b", proto["fixed_seed"], 0.5)
    _write_run(tmp_path, "run_c", proto["contrast_seed"], 0.5)
    result = vr.check_determinism(prereg, tmp_path, EXCLUDED)
    assert not result.passed
    assert result.observed["contrast_differs"] is False


def test_determinism_ignores_incomplete_runs(prereg: dict[str, Any], tmp_path: Path) -> None:
    proto = prereg["determinism_protocol"]
    _write_run(tmp_path, "run_a", proto["fixed_seed"], 0.5)
    _write_run(tmp_path, "run_b", proto["fixed_seed"], 0.5, status="killed")
    _write_run(tmp_path, "run_c", proto["contrast_seed"], 0.7)
    result = vr.check_determinism(prereg, tmp_path, EXCLUDED)
    assert not result.passed
    assert result.observed["fixed_seed_runs"] == ["run_a"]


def test_exclusion_does_not_hide_a_differing_result_value(
    prereg: dict[str, Any], tmp_path: Path
) -> None:
    # Excluding 'score' is forbidden by the bounds check, but even if it were passed in, the
    # metrics.csv column drop must not mask a nested results.json difference.
    proto = prereg["determinism_protocol"]
    _write_run(tmp_path, "run_a", proto["fixed_seed"], 0.5)
    _write_run(tmp_path, "run_b", proto["fixed_seed"], 0.6)
    _write_run(tmp_path, "run_c", proto["contrast_seed"], 0.7)
    result = vr.check_determinism(prereg, tmp_path, EXCLUDED | {"score"})
    assert not result.passed, "nested levels[].v still differs"


def test_strip_keys_removes_at_any_depth() -> None:
    obj = {"a": 1, "run_id": "x", "n": [{"run_id": "y", "b": 2}, 3]}
    assert vr.strip_keys(obj, frozenset({"run_id"})) == {"a": 1, "n": [{"b": 2}, 3]}


# ------------------------------------------------------------------ SHA256SUMS


def test_sha256sums_passes_for_intact_runs(prereg: dict[str, Any], tmp_path: Path) -> None:
    _write_run(tmp_path, "run_a", 1, 0.5)
    result = vr.check_sha256sums(prereg, tmp_path)
    assert result.passed, result.observed
    assert result.observed["fraction"] == 1.0


def test_sha256sums_fails_on_tampered_file(prereg: dict[str, Any], tmp_path: Path) -> None:
    _write_run(tmp_path, "run_a", 1, 0.5, corrupt_after_hash="results.json")
    result = vr.check_sha256sums(prereg, tmp_path)
    assert not result.passed
    assert any("mismatch" in p for p in result.observed["problems"])


def test_sha256sums_fails_on_unlisted_file(prereg: dict[str, Any], tmp_path: Path) -> None:
    _write_run(tmp_path, "run_a", 1, 0.5, omit_from_sums="stdout.log")
    result = vr.check_sha256sums(prereg, tmp_path)
    assert not result.passed
    assert any("unlisted" in p for p in result.observed["problems"])


def test_sha256sums_fails_with_no_runs(prereg: dict[str, Any], tmp_path: Path) -> None:
    assert not vr.check_sha256sums(prereg, tmp_path).passed


# ------------------------------------------------------------------ completeness


def test_run_completeness_requires_every_contract_file(tmp_path: Path) -> None:
    run = _write_run(tmp_path, "run_a", 1, 0.5)
    assert vr.check_run_completeness(tmp_path).passed
    (run / "transitions.jsonl").unlink()
    result = vr.check_run_completeness(tmp_path)
    assert not result.passed
    assert "run_a: missing transitions.jsonl" in result.observed["problems"]


def test_run_completeness_requires_every_manifest_key(tmp_path: Path) -> None:
    run = _write_run(tmp_path, "run_a", 1, 0.5)
    m = json.loads((run / "manifest.json").read_text())
    del m["prompt_hash"]
    (run / "manifest.json").write_text(json.dumps(m))
    result = vr.check_run_completeness(tmp_path)
    assert not result.passed
    assert "run_a: manifest lacks prompt_hash" in result.observed["problems"]


# ------------------------------------------------------------------ evidence section 11


SECTION = """## 10. Other

text

## 11. Open items for bootstrap to close

Each is [VERIFY-ON-MACHINE].

1. The accepted effort set.
   - Resolved 2026-09-04: low|medium|high|xhigh|max, from `claude --help`.
2. Whether the status line fires headless.
   - Hypothesis: probably not.
3. Rate-limit signature.
   - Not observable 2026-09-04: no limit hit yet; see state/tool_errors.jsonl.
4. Token sustains a turn.
5. Hook blocks sed -i.
   Resolved: 2026-09-04 blocked, see ledger.
6. Context exhaustion.
7. Separate allowance.
8. Installed version.
   - resolved 2026-09-04 2.1.0 WSL

## 12. Next
"""


def test_verify_on_machine_parsing_counts_only_dated_resolutions() -> None:
    total, resolved, unresolved = vr.parse_verify_on_machine(SECTION)
    assert total == 8
    assert resolved == 4
    assert len(unresolved) == 4
    assert unresolved[0].startswith("2.")


def test_verify_on_machine_check_reads_real_document(prereg: dict[str, Any]) -> None:
    result = vr.check_verify_on_machine(prereg, ROOT)
    assert result.observed["items_total"] == vr.threshold(prereg, "verify_on_machine_items_total")


# ------------------------------------------------------------------ licence and report


def test_licence_check_on_real_repo(prereg: dict[str, Any]) -> None:
    assert vr.check_licence(prereg, ROOT).passed


def test_report_with_skipped_tooling_is_never_a_pass(prereg: dict[str, Any], tmp_path: Path) -> None:
    proto = prereg["determinism_protocol"]
    _write_run(tmp_path, "run_a", proto["fixed_seed"], 0.5)
    _write_run(tmp_path, "run_b", proto["fixed_seed"], 0.5)
    _write_run(tmp_path, "run_c", proto["contrast_seed"], 0.7)
    report = vr.evaluate("G0", tmp_path, ROOT, skip_tooling=True)
    assert report.gate == "G0"
    assert len(report.preregistration_sha256) == 64
    assert set(report.skipped) == {
        "uv_sync_exit_code",
        "pytest_exit_code",
        "pytest_min_tests_collected",
        "ruff_exit_code",
        "mypy_exit_code",
    }
    d = report.to_dict()
    assert {c["name"] for c in d["checks"]} >= {
        "nondeterministic_fields_within_bounds",
        "determinism_identity",
        "sha256sums_verify",
        "git_status_clean",
        "licence_text",
        "verify_on_machine_resolved",
    }
