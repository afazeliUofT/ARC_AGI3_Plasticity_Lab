"""The derivation module against the hand-computed vectors hash-locked in the G2 pre-registration.

Every expected value and the count floor are read from the real ``preregistration/G2.yaml``
through the verifier's own ``load_preregistration``, so this file carries no copy of a gate
threshold. A failure is a derivation bug; the pre-registration forbids editing a case.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from arc_plasticity.evaluation import human_replays as hr

ROOT = Path(__file__).resolve().parents[2]


def _load_verify_run() -> ModuleType:
    if "verify_run" in sys.modules:
        return sys.modules["verify_run"]
    spec = importlib.util.spec_from_file_location("verify_run", ROOT / "scripts" / "verify_run.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _script(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def prereg() -> dict[str, Any]:
    data, _, _ = _load_verify_run().load_preregistration("G2", ROOT)
    return data


@pytest.fixture(scope="module")
def cases(prereg: dict[str, Any]) -> list[dict[str, Any]]:
    vectors = prereg["baseline_derivation_vectors"]["cases"]
    assert isinstance(vectors, list) and vectors
    return vectors


# ------------------------------------------------------------------ pre-registered vectors


def test_case_count_meets_preregistered_floor(
    prereg: dict[str, Any], cases: list[dict[str, Any]]
) -> None:
    assert len(cases) >= prereg["thresholds"]["derivation_vectors_min"]
    ids = [c["id"] for c in cases]
    assert len(set(ids)) == len(ids), f"duplicate case ids: {ids}"


def test_every_vector_reproduces_exactly(cases: list[dict[str, Any]]) -> None:
    failures: list[str] = []
    for case in cases:
        got = hr.derive_vector_case(case)
        if "expected_attributed_actions_per_level" in case:
            want: Any = [int(x) for x in case["expected_attributed_actions_per_level"]]
        else:
            want = case["expected_baseline"]
            if want is not None:
                want = int(want)
        # Exact comparison, and the type must match too (an int, a None, or a list of ints).
        if got != want or type(got) is not type(want):
            failures.append(f"{case['id']}: got {got!r}, expected {want!r}")
    assert not failures, "\n".join(failures)


def test_d7_yields_none_not_zero(cases: list[dict[str, Any]]) -> None:
    case = next(c for c in cases if c["id"].startswith("D7"))
    assert case["expected_baseline"] is None
    assert hr.derive_vector_case(case) is None


def test_d8_attribution_list(cases: list[dict[str, Any]]) -> None:
    case = next(c for c in cases if c["id"].startswith("D8"))
    assert hr.derive_vector_case(case) == [
        int(x) for x in case["expected_attributed_actions_per_level"]
    ]


def test_alternative_statistics_are_not_produced(cases: list[dict[str, Any]]) -> None:
    """D3 discriminates upper median from lower median and mean; D6b from including session 2."""
    d3 = next(c for c in cases if c["id"].startswith("D3"))
    values = sorted(int(r["level_completion_action_counts"][0]) for r in d3["replays"])
    assert hr.upper_median(values) == int(d3["expected_baseline"])
    assert hr.upper_median(values) != values[len(values) // 2 - 1]  # lower median
    assert hr.upper_median(values) * len(values) != sum(values)  # mean
    d6b = next(c for c in cases if c["id"].startswith("D6b"))
    all_sessions = hr.sessions_from_vector(d6b["replays"])
    including_second = hr.upper_median(
        [min(s.completion_counts[1]) for s in all_sessions if s.completion_counts]
    )
    assert including_second != int(d6b["expected_baseline"])


# ------------------------------------------------------------------ rule-level unit tests


def test_upper_median_indexing() -> None:
    assert hr.upper_median([1]) == 1
    assert hr.upper_median([2, 1]) == 2
    assert hr.upper_median([3, 1, 2]) == 2
    assert hr.upper_median([4, 3, 2, 1]) == 3
    with pytest.raises(hr.HumanReplayError):
        hr.upper_median([])
    with pytest.raises(hr.HumanReplayError):
        hr.upper_median([0, 1])


def test_attribute_levels_edge_cases() -> None:
    assert hr.attribute_levels([]) == []
    assert hr.attribute_levels([0, 0, 0]) == []
    assert hr.attribute_levels([2]) == [1, 0]  # two levels at once: second charged 0 actions
    assert hr.attribute_levels([0, 1, 0, 0, 2]) == [2, 3]
    with pytest.raises(hr.HumanReplayError):
        hr.attribute_levels([0, -1])
    with pytest.raises(hr.HumanReplayError):
        hr.attribute_levels([True])


def test_first_sessions_rejects_tied_session_index() -> None:
    a = hr.ReplaySession("g", "P1", 1, {1: (5,)}, source_file="a")
    b = hr.ReplaySession("g", "P1", 1, {1: (3,)}, source_file="b")
    with pytest.raises(hr.HumanReplayError):
        hr.first_sessions([a, b])


def test_anonymous_sessions_are_distinct_participants() -> None:
    sessions = [hr.ReplaySession("g", None, 1, {1: (c,)}) for c in (9, 1, 5)]
    assert hr.derive_level_baseline(sessions, "g", 1) == 5
    assert hr.derive_level_baselines(sessions)[("g", 1)].n_participants_with_completion == 3


def test_derive_level_baselines_fills_official_levels_with_none() -> None:
    sessions = [hr.ReplaySession("g", "P1", 1, {1: (4,), 2: (6,)})]
    table = hr.derive_level_baselines(sessions, {"g": 3, "h": 1})
    assert sorted(table) == [("g", 1), ("g", 2), ("g", 3), ("h", 1)]
    assert table[("g", 1)].derived == 4
    assert table[("g", 3)].derived is None
    assert table[("h", 1)].per_participant_best_counts_sorted == ()


def test_relative_difference_is_exact() -> None:
    assert hr.relative_difference(7, 6) == Fraction(1, 6)
    assert hr.relative_difference(6, 6) == 0
    with pytest.raises(hr.HumanReplayError):
        hr.relative_difference(6, 0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"game_id": "", "participant": "P", "session_index": 1, "completion_counts": {}},
        {"game_id": "g", "participant": "P", "session_index": 0, "completion_counts": {}},
        {"game_id": "g", "participant": "P", "session_index": True, "completion_counts": {}},
        {"game_id": "g", "participant": "P", "session_index": 1, "completion_counts": {0: (1,)}},
        {"game_id": "g", "participant": "P", "session_index": 1, "completion_counts": {1: (0,)}},
        {"game_id": "g", "participant": "P", "session_index": 1, "completion_counts": {1: [1]}},
        {"game_id": "g", "participant": 3, "session_index": 1, "completion_counts": {}},
    ],
)
def test_invalid_sessions_are_rejected(kwargs: dict[str, Any]) -> None:
    with pytest.raises(hr.HumanReplayError):
        hr.ReplaySession(**kwargs)


# ------------------------------------------------------------------ loader on a synthetic tree


def _event(
    game: str, levels: int, *, participant: str | None = None, ts: str | None = None
) -> dict[str, Any]:
    data: dict[str, Any] = {"game_id": game, "levels_completed": levels, "state": "NOT_FINISHED"}
    top: dict[str, Any] = {"data": data}
    if participant is not None:
        data["participant_id"] = participant
    if ts is not None:
        top["timestamp"] = ts
    return top


def _write_log(path: Path, events: list[dict[str, Any]]) -> None:
    """Write ``events`` as issued actions, preceded by the opening (play-start) frame.

    The opening frame copies the first action's identity fields with ``levels_completed`` 0,
    matching the released recorder format where record 1 is not an issued action.
    """
    opening = json.loads(json.dumps(events[0]))
    opening["data"]["levels_completed"] = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in [opening, *events]), encoding="utf-8")


def _synthetic_raw(root: Path) -> Path:
    raw = root / "data" / "human_replays" / "raw"
    # P1 first session on game g (by timestamp, though it sorts later by file name): 3 actions to
    # level 1. P1 second session: 1 action. P2: 5 actions to level 1, then 2 more to level 2.
    _write_log(
        raw / "b_p1_first.jsonl",
        [_event("g", 0, participant="P1", ts="2026-01-01T00:00:00Z")] * 2
        + [_event("g", 1, participant="P1", ts="2026-01-01T00:00:00Z")],
    )
    _write_log(
        raw / "a_p1_second.jsonl", [_event("g", 1, participant="P1", ts="2026-02-01T00:00:00Z")]
    )
    _write_log(
        raw / "sub" / "p2.jsonl",
        [_event("g", 0, participant="P2", ts="2026-01-05T00:00:00Z")] * 4
        + [_event("g", 1, participant="P2", ts="2026-01-05T00:00:00Z")]
        + [_event("g", 2, participant="P2", ts="2026-01-05T00:00:00Z")] * 1
        + [_event("g", 2, participant="P2", ts="2026-01-05T00:00:00Z")],
    )
    return raw


def test_ingest_synthetic_tree(tmp_path: Path) -> None:
    raw = _synthetic_raw(tmp_path)
    result = hr.ingest_directory(raw)
    assert result.replay_units_ingested == 3
    assert result.parse_failures == []
    assert result.participant_ids_available is True
    assert sorted(result.file_digests) == ["a_p1_second.jsonl", "b_p1_first.jsonl", "sub/p2.jsonl"]
    by_file = {f.source_file: f for f in result.files}
    assert by_file["b_p1_first.jsonl"].sessions[0].session_index == 1
    assert by_file["a_p1_second.jsonl"].sessions[0].session_index == 2
    assert by_file["b_p1_first.jsonl"].field_mapping["session_order_source"] == "timestamp"
    assert by_file["b_p1_first.jsonl"].field_mapping["participant"] == "data.participant_id"
    table = hr.derive_level_baselines(result.sessions)
    # Level 1: P1 first session 3 (second session's 1 excluded), P2 5 -> upper median 5.
    assert table[("g", 1)].derived == 5
    assert table[("g", 1)].per_participant_best_counts_sorted == (3, 5)
    # Level 2: only P2, 6 actions at completion minus 5 -> 1.
    assert table[("g", 2)].derived == 1


def test_ingest_counts_parse_failures_without_raising(tmp_path: Path) -> None:
    raw = _synthetic_raw(tmp_path)
    (raw / "broken.jsonl").write_text('{"data": {"game_id": "g"}}\n', encoding="utf-8")
    (raw / "notjson.txt").write_bytes(b"\xff\xfe")
    result = hr.ingest_directory(raw)
    assert result.replay_units_ingested == 3
    assert sorted(f.source_file for f in result.parse_failures) == ["broken.jsonl", "notjson.txt"]
    assert len(result.file_digests) == 5


def test_ingest_without_participant_ids_uses_file_order(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _write_log(raw / "x.jsonl", [_event("g", 1)])
    _write_log(raw / "y.jsonl", [_event("g", 0), _event("g", 1)])
    result = hr.ingest_directory(raw)
    assert result.participant_ids_available is False
    assert all(s.session_index == 1 for s in result.sessions)
    assert hr.derive_level_baselines(result.sessions)[("g", 1)].derived == 2


# ------------------------------------------------------------------ manifest builder script


def test_manifest_builder_on_synthetic_tree(tmp_path: Path) -> None:
    mod = _script("build_human_replays_manifest")
    raw = _synthetic_raw(tmp_path)
    m = mod.build_manifest(
        tmp_path,
        raw,
        source_url="https://example.invalid/dataset",
        retrieval_method="human_placed",
        retrieval_utc=datetime(2026, 9, 4, 8, 0, tzinfo=UTC),
        revision=None,
    )
    assert m["schema_version"] == 1
    assert m["raw_dir"] == "data/human_replays/raw"
    assert m["retrieval_utc"] == "2026-09-04T08:00:00Z"
    assert m["totals"]["files"] == 3
    assert m["totals"]["replay_units"] == 3
    assert m["totals"]["parse_failures"] == 0
    assert m["totals"]["participant_ids_available"] is True
    for key in ("source_url", "retrieval_utc", "retrieval_method", "files"):
        assert key in m
    entry = m["files"]["sub/p2.jsonl"]
    assert entry["sha256"] == hr.sha256_of(raw / "sub" / "p2.jsonl")
    assert entry["bytes"] == (raw / "sub" / "p2.jsonl").stat().st_size
    assert entry["replay_units"] == 1 and entry["parse_failure"] is None
    assert mod.drift(m, raw) == []
    (raw / "extra.jsonl").write_text("", encoding="utf-8")
    assert mod.drift(m, raw) == ["present but unlisted: extra.jsonl"]


def test_manifest_builder_refuses_absent_or_empty_raw_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _script("build_human_replays_manifest")
    out = tmp_path / "out" / "manifest.json"
    common = [
        "--source-url",
        "https://example.invalid",
        "--retrieval-method",
        "human_placed",
        "--output",
        str(out),
    ]
    absent = tmp_path / "absent"
    assert mod.main(["--raw-dir", str(absent), *common]) == 1
    assert "not a directory" in capsys.readouterr().err
    empty = tmp_path / "empty"
    empty.mkdir()
    assert mod.main(["--raw-dir", str(empty), *common]) == 1
    assert "holds no files" in capsys.readouterr().err
    assert not out.exists()
    assert not (tmp_path / "artifacts").exists()


def test_manifest_builder_cli_writes_and_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _script("build_human_replays_manifest")
    raw = _synthetic_raw(tmp_path)
    out = tmp_path / "experiments" / "human_replays_manifest.json"
    rc = mod.main(
        [
            "--root",
            str(tmp_path),
            "--raw-dir",
            str(raw),
            "--output",
            str(out),
            "--source-url",
            "https://example.invalid",
            "--retrieval-method",
            "human_placed",
            "--retrieval-utc",
            "2026-09-04T08:00:00Z",
        ]
    )
    assert rc == 0, capsys.readouterr().err
    assert json.loads(out.read_text())["totals"]["replay_units"] == 3
    assert mod.main(["--check", "--raw-dir", str(raw), "--output", str(out)]) == 0
    (raw / "sub" / "p2.jsonl").write_text("", encoding="utf-8")
    assert mod.main(["--check", "--raw-dir", str(raw), "--output", str(out)]) == 1
    assert "sha256 differs: sub/p2.jsonl" in capsys.readouterr().err


def test_manifest_builder_requires_provenance_flags(tmp_path: Path) -> None:
    mod = _script("build_human_replays_manifest")
    raw = _synthetic_raw(tmp_path)
    assert mod.main(["--raw-dir", str(raw), "--output", str(tmp_path / "m.json")]) == 2
