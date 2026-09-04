"""The loader against the released ARC-AGI-3 recorder format (``<guid>.recording.jsonl``).

Fixtures are hand-built in the shape observed on 2026-09-04 over all 342 files of the human
dataset (ledger G2.6): record 1 is the frame returned by the play-start RESET, every later
record is the frame returned by one issued action (RESET included), and the last record is the
toolkit scorecard whose ``actions_by_level`` pairs are the dataset-supplied per-level counts
(path P2). The opening-record rule follows ``arc_agi.scorecard.Card`` (a play opens at 0
actions; every action and every later RESET adds 1), which the pre-registered attribution rule
says it reproduces. No number here is a gate threshold.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from arc_plasticity.evaluation import human_replays as hr

GAME = "ka59-38d34dbb"
GUID = "52dd648e-dc33-4b71-8bb8-6ce0f3bd61ed"


def _frame(levels: int, action_id: Any, *, state: str = "NOT_FINISHED") -> dict[str, Any]:
    return {
        "timestamp": "2026-02-27T19:05:19.368230+00:00",
        "data": {
            "game_id": GAME,
            "frame": [[[0]]],
            "state": state,
            "levels_completed": levels,
            "win_levels": 7,
            "action_input": {"id": action_id, "data": {"game_id": "ka59-9f096b4a"}},
            "guid": GUID,
            "full_reset": False,
            "available_actions": [1, 2, 3, 4, 6],
        },
    }


def _scorecard(
    actions_by_level: list[list[list[int]]] | None,
    actions: list[int],
    *,
    guids: list[str] | None = None,
    levels: list[int] | None = None,
    with_timestamp: bool = True,
) -> dict[str, Any]:
    card: dict[str, Any] = {
        "game_id": GAME,
        "total_plays": len(actions),
        "levels_completed": levels or [0] * len(actions),
        "states": ["NOT_FINISHED"] * len(actions),
        "actions": actions,
        "resets": [0] * len(actions),
        "total_actions": sum(actions),
    }
    if actions_by_level is not None:
        card["actions_by_level"] = actions_by_level
    if guids is not None:
        card["guids"] = guids
    record: dict[str, Any] = {
        "data": {
            "won": 0,
            "played": 1,
            "total_actions": sum(actions),
            "levels_completed": max(card["levels_completed"]),
            "cards": {GAME: card},
        }
    }
    if with_timestamp:
        record["timestamp"] = "2026-02-27T19:06:58.924871+00:00"
    return record


def _new_format_events() -> list[dict[str, Any]]:
    """Opening RESET, 5 actions to level 1 (one of them a mid-play RESET), 3 more to level 2."""
    levels = [0, 0, 0, 0, 1, 1, 1, 2]
    ids = [1, 2, 0, 3, 6, 1, 2, 3]
    return [_frame(0, 0)] + [_frame(lv, i) for lv, i in zip(levels, ids, strict=True)]


def _write(path: Path, events: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return path


def test_new_format_counts_actions_after_the_opening_frame() -> None:
    events = _new_format_events() + [_scorecard([[[1, 5], [2, 8]]], [8], guids=[GUID], levels=[2])]
    session, mapping = hr.parse_step_log_events(events, "x.recording.jsonl")
    assert session.game_id == GAME
    assert session.session_id == GUID and mapping["session_id"] == "data.guid"
    assert session.participant is None and mapping["participant"] is None
    assert session.actions_total == 8  # 9 frame records minus the opening one
    assert session.completion_counts == {1: (5,), 2: (3,)}
    assert session.dataset_completion_counts == {1: (5,), 2: (3,)}
    assert session.dataset_actions_total == 8
    assert session.dataset_agreement == {1: True, 2: True}
    assert mapping["opening_record"] == hr.OPENING_RECORD_RULE
    assert mapping["scorecard"] == "data.cards"
    assert mapping["dataset_completion_counts"] == f"data.cards[{GAME!r}].actions_by_level[0]"
    assert mapping["dataset_actions_total"] == f"data.cards[{GAME!r}].actions[0]"
    assert mapping["scorecard_play"].endswith("play 0 by guid")
    assert mapping["levels_completed"] == "data.levels_completed"


def test_old_format_first_record_is_still_the_opening_frame() -> None:
    """23 dataset files label record 1 with a real action id; the toolkit still counts k - 1."""
    levels = [0, 0, 1]
    events = [_frame(0, "ACTION6")] + [_frame(lv, "ACTION6") for lv in levels]
    events.append(_scorecard([[[1, 3]]], [3], levels=[1]))
    session, _ = hr.parse_step_log_events(events)
    assert session.actions_total == 3
    assert session.completion_counts == {1: (3,)}
    assert session.dataset_agreement == {1: True}


def test_disagreement_with_the_scorecard_is_recorded_not_resolved() -> None:
    events = _new_format_events() + [_scorecard([[[1, 6], [2, 8]]], [9])]
    session, _ = hr.parse_step_log_events(events)
    assert session.completion_counts == {1: (5,), 2: (3,)}
    assert session.dataset_completion_counts == {1: (6,), 2: (2,)}
    assert session.dataset_agreement == {1: False, 2: False}
    assert session.dataset_actions_total == 9 and session.actions_total == 8


def test_scorecard_without_actions_by_level_means_p2_unavailable() -> None:
    events = [_frame(0, 0), _frame(0, 1)] + [_scorecard(None, [1])]
    session, mapping = hr.parse_step_log_events(events)
    assert session.completion_counts == {}
    assert session.dataset_completion_counts is None
    assert session.dataset_agreement is None
    assert mapping["dataset_completion_counts"] is None
    assert session.dataset_actions_total == 1


def test_empty_actions_by_level_means_p2_says_nothing_completed() -> None:
    events = [_frame(0, 0), _frame(0, 1)] + [_scorecard([[]], [1])]
    session, _ = hr.parse_step_log_events(events)
    assert session.dataset_completion_counts == {}
    assert session.dataset_agreement == {}


def test_two_play_card_uses_the_play_matching_the_guid() -> None:
    events = _new_format_events() + [
        _scorecard(
            [[[1, 99]], [[1, 5], [2, 8]]], [99, 8], guids=["other-guid", GUID], levels=[1, 2]
        )
    ]
    session, mapping = hr.parse_step_log_events(events)
    assert session.dataset_completion_counts == {1: (5,), 2: (3,)}
    assert session.dataset_actions_total == 8
    assert mapping["scorecard_play"].endswith("play 1 by guid")


def test_two_play_card_without_guids_uses_the_last_play() -> None:
    events = _new_format_events() + [_scorecard([[], [[1, 5], [2, 8]]], [0, 8], levels=[0, 2])]
    session, mapping = hr.parse_step_log_events(events)
    assert session.dataset_completion_counts == {1: (5,), 2: (3,)}
    assert mapping["scorecard_play"].endswith("play 1 by last_play")


def test_no_scorecard_still_parses_with_p2_none() -> None:
    session, mapping = hr.parse_step_log_events(_new_format_events())
    assert session.completion_counts == {1: (5,), 2: (3,)}
    assert session.dataset_completion_counts is None and session.dataset_actions_total is None
    assert mapping["scorecard"] is None and mapping["scorecard_play"] is None


def test_unit_with_zero_actions_counts_and_contributes_nothing() -> None:
    session, _ = hr.parse_step_log_events([_frame(0, 0), _scorecard([[]], [0])])
    assert session.actions_total == 0
    assert session.completion_counts == {}


@pytest.mark.parametrize(
    ("events", "fragment"),
    [
        (_new_format_events()[:3] + [_scorecard([[]], [2])] + _new_format_events()[3:], "not last"),
        (_new_format_events() + [_scorecard([[]], [8]), _scorecard([[]], [8])], "2 scorecard"),
        ([_scorecard([[]], [0])], "no frame records"),
        ([_frame(1, 0), _frame(1, 1)], "opening record reports levels_completed 1"),
        ([_frame(0, 0), {"data": {"game_id": GAME}}], "record 2 has no levels_completed"),
        ([_frame(0, 0), _frame(0, 1)] + [{"data": {"cards": {}}}], "no cards"),
        (
            [_frame(0, 0), _frame(0, 1)]
            + [{"data": {"cards": {"a-1": {"actions": [1]}, "b-2": {"actions": [1]}}}}],
            "none for",
        ),
        ([_frame(0, 0), _frame(1, 1)] + [_scorecard([[[1, "x"]]], [1])], "actions_by_level"),
    ],
)
def test_malformed_recordings_are_loud_parse_failures(
    events: list[dict[str, Any]], fragment: str
) -> None:
    with pytest.raises(hr.HumanReplayError, match=fragment):
        hr.parse_step_log_events(events, "bad.recording.jsonl")


def test_attribute_levels_from_pairs_applies_the_first_reach_rule() -> None:
    assert hr.attribute_levels_from_pairs([[1, 43], [2, 326], [3, 401]]) == [43, 283, 75]
    # A drop after a full reset and a re-completion never move an earlier completion.
    assert hr.attribute_levels_from_pairs([[1, 10], [0, 12], [1, 20], [2, 25]]) == [10, 15]
    # Two levels completed on one pair share the count; the second gets 0 and is rejected
    # downstream by the positive-integer contract, never turned into a baseline.
    assert hr.attribute_levels_from_pairs([[2, 7]]) == [7, 0]
    assert hr.attribute_levels_from_pairs([]) == []


def test_ingest_directory_carries_p2_through_renumbering(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _write(
        raw / "g" / "a.recording.jsonl",
        _new_format_events() + [_scorecard([[[1, 5], [2, 8]]], [8])],
    )
    _write(raw / "g" / "b.recording.jsonl", [_frame(0, 0), _frame(0, 4)] + [_scorecard(None, [1])])
    result = hr.ingest_directory(raw)
    assert result.replay_units_ingested == 2 and result.parse_failures == []
    assert result.participant_ids_available is False
    by_file = {f.source_file: f for f in result.files}
    a = by_file["g/a.recording.jsonl"].sessions[0]
    assert a.dataset_completion_counts == {1: (5,), 2: (3,)} and a.dataset_actions_total == 8
    assert a.session_index == 1
    assert by_file["g/a.recording.jsonl"].field_mapping["session_order_source"] == "file_order"
    assert by_file["g/a.recording.jsonl"].field_mapping["opening_record"] == hr.OPENING_RECORD_RULE
    b = by_file["g/b.recording.jsonl"].sessions[0]
    assert b.dataset_completion_counts is None and b.dataset_actions_total == 1
    table = hr.derive_level_baselines(result.sessions)
    assert table[(GAME, 1)].derived == 5 and table[(GAME, 2)].derived == 3


def test_session_validates_dataset_fields() -> None:
    with pytest.raises(hr.HumanReplayError, match="dataset_completion_counts"):
        hr.ReplaySession("g", None, 1, {}, dataset_completion_counts={1: (0,)})
    with pytest.raises(hr.HumanReplayError, match="dataset_actions_total"):
        hr.ReplaySession("g", None, 1, {}, dataset_actions_total=-1)
