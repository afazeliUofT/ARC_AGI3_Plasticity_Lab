"""Human replay ingestion and per-level baseline derivation for gate G2.

The rules implemented here are the ones hash-locked in the G2 pre-registration
(``human_baselines`` section) and pinned by its ``baseline_derivation_vectors``:

* **level attribution** (``attribute_levels``): within one session, level ``l`` is completed at
  the first action index at which ``levels_completed`` reaches at least ``l``; later full resets
  and re-completions are ignored; actions attributed to level ``l`` are ``c_l - c_(l-1)``.
* **first-run rule** (``first_sessions``): only a participant's first session on a game counts.
  With no participant identity every replay unit is its own participant's first session.
* **per-participant best** (``derive_level_baseline``): the minimum attributed count over that
  participant's first-session completions of the level.
* **aggregation**: the UPPER median ``v_(floor(N/2) + 1)`` of the sorted per-participant best
  counts; ``N = 0`` yields ``None`` (no derived baseline).

Everything in the derivation is integer arithmetic on the input records; no seed, no float, no
environment. The loader (``ingest_directory``) reads the documented ARC-AGI-3 recorder format,
one JSON event per line, and records the SHA-256 of every file it reads. Files that do not
parse are counted, never silently skipped, because the pre-registration thresholds parse
failures at zero.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

#: Candidate field names for participant identity, checked in order at the top level of an
#: event and then inside its ``data`` mapping. The first one present in a file's first event is
#: recorded as ``participant_key`` for the ingestion log.
PARTICIPANT_KEYS: tuple[str, ...] = (
    "participant_id",
    "participant",
    "user_id",
    "player_id",
    "session_owner",
)
#: Candidate field names for the session's own identifier (recorded, not used for ordering).
SESSION_ID_KEYS: tuple[str, ...] = ("session_id", "guid", "replay_id")
#: Candidate field names for the game identifier.
GAME_ID_KEYS: tuple[str, ...] = ("game_id", "environment", "game")
#: Candidate field names for levels completed after an action.
LEVELS_COMPLETED_KEYS: tuple[str, ...] = ("levels_completed",)
#: Candidate field names for a per-event timestamp used to order a participant's sessions.
TIMESTAMP_KEYS: tuple[str, ...] = ("timestamp", "ts", "time")


class HumanReplayError(ValueError):
    """A replay record or a derivation input violates the pre-registered contract."""


@dataclass(frozen=True)
class ReplaySession:
    """One replay unit: a contiguous human session on one game.

    ``completion_counts`` maps level number (1-based) to the attributed action counts of every
    completion of that level in the session, in occurrence order. Path P1 (step logs) yields at
    most one count per level, by construction of ``attribute_levels``; path P2 (per-level counts
    supplied by the dataset) may carry several, and the per-participant best takes the minimum.
    """

    game_id: str
    participant: str | None
    session_index: int
    completion_counts: Mapping[int, tuple[int, ...]]
    source_file: str = ""
    actions_total: int = 0
    session_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.game_id, str) or not self.game_id:
            raise HumanReplayError(f"game_id must be a non-empty str, got {self.game_id!r}")
        if self.participant is not None and not isinstance(self.participant, str):
            raise HumanReplayError(f"participant must be a str or None, got {self.participant!r}")
        if isinstance(self.session_index, bool) or not isinstance(self.session_index, int):
            raise HumanReplayError(f"session_index must be an int, got {self.session_index!r}")
        if self.session_index < 1:
            raise HumanReplayError(f"session_index must be >= 1, got {self.session_index}")
        if isinstance(self.actions_total, bool) or not isinstance(self.actions_total, int):
            raise HumanReplayError(f"actions_total must be an int, got {self.actions_total!r}")
        if self.actions_total < 0:
            raise HumanReplayError(f"actions_total must be >= 0, got {self.actions_total}")
        for level, counts in self.completion_counts.items():
            if isinstance(level, bool) or not isinstance(level, int) or level < 1:
                raise HumanReplayError(f"level keys must be positive ints, got {level!r}")
            if not isinstance(counts, tuple):
                raise HumanReplayError(f"level {level}: counts must be a tuple, got {counts!r}")
            for count in counts:
                _require_positive_int(count, f"level {level} completion count")


@dataclass(frozen=True)
class LevelBaseline:
    """The derived record for one (game, level); ``derived`` is ``None`` when ``N = 0``."""

    game_id: str
    level: int
    per_participant_best_counts_sorted: tuple[int, ...]

    @property
    def n_participants_with_completion(self) -> int:
        return len(self.per_participant_best_counts_sorted)

    @property
    def derived(self) -> int | None:
        if not self.per_participant_best_counts_sorted:
            return None
        return upper_median(self.per_participant_best_counts_sorted)


@dataclass(frozen=True)
class ParseFailure:
    """A file that could not be turned into a replay session."""

    source_file: str
    reason: str


@dataclass(frozen=True)
class ParsedFile:
    """One raw file after ingestion: its digest plus what was read from it."""

    source_file: str
    sha256: str
    bytes: int
    sessions: tuple[ReplaySession, ...]
    field_mapping: Mapping[str, str | None]
    failure: ParseFailure | None = None


@dataclass
class IngestionResult:
    """Everything ``ingest_directory`` learned, in a form the run can log and hash."""

    files: list[ParsedFile] = field(default_factory=list)

    @property
    def sessions(self) -> list[ReplaySession]:
        return [s for f in self.files for s in f.sessions]

    @property
    def parse_failures(self) -> list[ParseFailure]:
        return [f.failure for f in self.files if f.failure is not None]

    @property
    def replay_units_ingested(self) -> int:
        return len(self.sessions)

    @property
    def participant_ids_available(self) -> bool:
        return bool(self.sessions) and all(s.participant is not None for s in self.sessions)

    @property
    def file_digests(self) -> dict[str, str]:
        return {f.source_file: f.sha256 for f in self.files}


# --------------------------------------------------------------------------------------------
# Pure derivation
# --------------------------------------------------------------------------------------------


def _require_positive_int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HumanReplayError(f"{what} must be an int, got {value!r}")
    if value < 1:
        raise HumanReplayError(f"{what} must be positive, got {value}")
    return value


def _require_non_negative_int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HumanReplayError(f"{what} must be an int, got {value!r}")
    if value < 0:
        raise HumanReplayError(f"{what} must be non-negative, got {value}")
    return value


def attribute_levels(levels_completed_after_each_action: Sequence[int]) -> list[int]:
    """Actions attributed to each completed level from a step log (``level_attribution_rule``).

    Element ``i`` (0-based) is ``levels_completed`` after action ``i + 1``. Level ``l`` is
    completed at the first 1-based action index ``c_l`` with ``levels_completed >= l``; the
    result is ``[c_1 - c_0, c_2 - c_1, ...]`` with ``c_0 = 0`` for every level reached. A later
    drop (full reset) and re-completion never change an earlier ``c_l``.
    """
    completion_index: list[int] = []
    for position, raw in enumerate(levels_completed_after_each_action, start=1):
        completed = _require_non_negative_int(raw, f"levels_completed at action {position}")
        while len(completion_index) < completed:
            completion_index.append(position)
    attributed: list[int] = []
    previous = 0
    for index in completion_index:
        attributed.append(index - previous)
        previous = index
    return attributed


def upper_median(values: Sequence[int]) -> int:
    """``v_(floor(N/2) + 1)`` of the sorted values (``aggregation_rule``); ``N`` must be > 0."""
    if not values:
        raise HumanReplayError("upper_median of an empty sequence is undefined")
    ordered = sorted(_require_positive_int(v, "count") for v in values)
    return ordered[len(ordered) // 2]


def first_sessions(sessions: Iterable[ReplaySession]) -> list[ReplaySession]:
    """The first session of every (participant, game), per ``first_run_rule``.

    A session with ``participant`` ``None`` is its own participant. Two sessions of the same
    participant on the same game with the same ``session_index`` are an ordering defect in the
    loader and are rejected rather than resolved arbitrarily.
    """
    chosen: dict[tuple[Any, str], ReplaySession] = {}
    for ordinal, session in enumerate(sessions):
        owner: Any = session.participant if session.participant is not None else ("anon", ordinal)
        key = (owner, session.game_id)
        current = chosen.get(key)
        if current is None:
            chosen[key] = session
        elif session.session_index == current.session_index:
            raise HumanReplayError(
                f"participant {session.participant!r} has two sessions on {session.game_id} "
                f"with session_index {session.session_index} "
                f"({current.source_file!r}, {session.source_file!r})"
            )
        elif session.session_index < current.session_index:
            chosen[key] = session
    return list(chosen.values())


def per_participant_best(sessions: Iterable[ReplaySession]) -> dict[tuple[str, int], list[int]]:
    """``(game_id, level) -> sorted per-participant best counts`` over first sessions only."""
    best: dict[tuple[str, int], list[int]] = {}
    for session in first_sessions(sessions):
        for level, counts in session.completion_counts.items():
            if counts:
                best.setdefault((session.game_id, level), []).append(min(counts))
    return {key: sorted(values) for key, values in best.items()}


def derive_level_baseline(
    sessions: Iterable[ReplaySession], game_id: str, level: int
) -> int | None:
    """The derived baseline for one level, or ``None`` if no first session completed it."""
    values = per_participant_best(sessions).get((game_id, level))
    return upper_median(values) if values else None


def derive_level_baselines(
    sessions: Iterable[ReplaySession],
    levels_per_game: Mapping[str, int] | None = None,
) -> dict[tuple[str, int], LevelBaseline]:
    """Every (game, level) record. Pure function of its input; no seed, no float.

    With ``levels_per_game`` (``game_id -> number of levels`` from the official metadata) the
    result carries a record for every official level, with ``derived`` ``None`` where the
    replays contain no completion. Without it only levels seen in the replays appear.
    """
    materialised = list(sessions)
    best = per_participant_best(materialised)
    keys: set[tuple[str, int]] = set(best)
    if levels_per_game is not None:
        for game_id, n_levels in levels_per_game.items():
            _require_positive_int(n_levels, f"levels_per_game[{game_id!r}]")
            keys.update((game_id, level) for level in range(1, n_levels + 1))
    return {key: LevelBaseline(key[0], key[1], tuple(best.get(key, []))) for key in sorted(keys)}


def relative_difference(derived: int, official: int) -> Fraction:
    """``(derived - official) / official`` as an exact rational."""
    _require_positive_int(official, "official baseline")
    _require_positive_int(derived, "derived baseline")
    return Fraction(derived - official, official)


# --------------------------------------------------------------------------------------------
# Pre-registration vector adapters (one shared path for the test and the verifier)
# --------------------------------------------------------------------------------------------


def sessions_from_vector(
    replays: Sequence[Mapping[str, Any]], game_id: str = "vector"
) -> list[ReplaySession]:
    """Map a ``baseline_derivation_vectors`` ``replays`` list to sessions on a single level 1."""
    sessions: list[ReplaySession] = []
    for entry in replays:
        counts = tuple(int(c) for c in entry["level_completion_action_counts"])
        sessions.append(
            ReplaySession(
                game_id=game_id,
                participant=str(entry["participant"]),
                session_index=int(entry["session_index"]),
                completion_counts={1: counts} if counts else {},
            )
        )
    return sessions


def derive_vector_case(case: Mapping[str, Any]) -> int | None | list[int]:
    """Run one embedded derivation vector through the same functions the run uses."""
    if "levels_completed_after_each_action" in case:
        return attribute_levels([int(x) for x in case["levels_completed_after_each_action"]])
    return derive_level_baseline(sessions_from_vector(case["replays"]), "vector", 1)


# --------------------------------------------------------------------------------------------
# Loading raw files
# --------------------------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _first_present(mapping: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return key
    return None


def _lookup(event: Mapping[str, Any], keys: Sequence[str]) -> tuple[str | None, Any]:
    """Find the first candidate key at the top level of ``event`` or inside ``event['data']``."""
    key = _first_present(event, keys)
    if key is not None:
        return key, event[key]
    data = event.get("data")
    if isinstance(data, Mapping):
        key = _first_present(data, keys)
        if key is not None:
            return f"data.{key}", data[key]
    return None, None


def parse_step_log_events(
    events: Sequence[Mapping[str, Any]], source_file: str = ""
) -> tuple[ReplaySession, dict[str, str | None]]:
    """One session from the documented recorder format: one event per action.

    Every event is one issued action (RESET included), matching ``level_attribution_rule``.
    ``session_index`` is set to 1 here; ``ingest_directory`` re-numbers sessions per
    participant and game by timestamp when every event carries one, else by file order.
    """
    if not events:
        raise HumanReplayError(f"{source_file or 'step log'}: no events")
    first = events[0]
    game_key, game_id = _lookup(first, GAME_ID_KEYS)
    if game_key is None or not isinstance(game_id, str) or not game_id:
        raise HumanReplayError(f"{source_file or 'step log'}: first event has no game_id")
    participant_key, participant = _lookup(first, PARTICIPANT_KEYS)
    session_key, session_id = _lookup(first, SESSION_ID_KEYS)
    timestamp_key, _ = _lookup(first, TIMESTAMP_KEYS)
    levels_key: str | None = None
    levels_after: list[int] = []
    for position, event in enumerate(events, start=1):
        key, value = _lookup(event, LEVELS_COMPLETED_KEYS)
        if key is None:
            raise HumanReplayError(
                f"{source_file or 'step log'}: event {position} has no levels_completed"
            )
        levels_key = levels_key or key
        levels_after.append(
            _require_non_negative_int(value, f"levels_completed at event {position}")
        )
        _, this_game = _lookup(event, GAME_ID_KEYS)
        if this_game != game_id:
            raise HumanReplayError(
                f"{source_file or 'step log'}: event {position} game_id {this_game!r} != {game_id!r}"
            )
    attributed = attribute_levels(levels_after)
    session = ReplaySession(
        game_id=game_id,
        participant=None if participant is None else str(participant),
        session_index=1,
        completion_counts={level: (count,) for level, count in enumerate(attributed, start=1)},
        source_file=source_file,
        actions_total=len(events),
        session_id=None if session_id is None else str(session_id),
    )
    mapping: dict[str, str | None] = {
        "game_id": game_key,
        "participant": participant_key,
        "session_id": session_key,
        "timestamp": timestamp_key,
        "levels_completed": levels_key,
    }
    return session, mapping


def read_jsonl_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise HumanReplayError(f"{path.name}: line {line_no}: {exc.msg}") from exc
            if not isinstance(obj, dict):
                raise HumanReplayError(f"{path.name}: line {line_no}: event is not an object")
            events.append(obj)
    return events


def _first_timestamp(events: Sequence[Mapping[str, Any]]) -> Any:
    _, value = _lookup(events[0], TIMESTAMP_KEYS)
    return value


def raw_files(raw_dir: Path) -> list[Path]:
    """Every regular file under ``raw_dir``, sorted by relative POSIX path (the file order)."""
    return sorted(
        (p for p in raw_dir.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(raw_dir).as_posix(),
    )


def ingest_directory(raw_dir: Path) -> IngestionResult:
    """Ingest every file under ``raw_dir``; never raises on a bad file, records it instead.

    Session order per (participant, game): by the first event's timestamp when every session
    of that pair has one, else by file order. The choice is visible in ``session_order_source``
    of the returned files' field mappings ("timestamp" or "file_order").
    """
    if not raw_dir.is_dir():
        raise HumanReplayError(f"{raw_dir} is not a directory")
    result = IngestionResult()
    ordering: dict[tuple[str, str], list[tuple[int, Any]]] = {}
    parsed: list[tuple[int, ReplaySession, dict[str, str | None]]] = []
    for ordinal, path in enumerate(raw_files(raw_dir)):
        rel = path.relative_to(raw_dir).as_posix()
        digest, size = sha256_of(path), path.stat().st_size
        try:
            events = read_jsonl_events(path)
            session, mapping = parse_step_log_events(events, rel)
        except (HumanReplayError, OSError, UnicodeDecodeError) as exc:
            result.files.append(ParsedFile(rel, digest, size, (), {}, ParseFailure(rel, str(exc))))
            continue
        parsed.append((ordinal, session, mapping))
        if session.participant is not None:
            ordering.setdefault((session.participant, session.game_id), []).append(
                (ordinal, _first_timestamp(events))
            )
        result.files.append(ParsedFile(rel, digest, size, (session,), mapping))

    # Re-number sessions per (participant, game).
    index_of: dict[int, tuple[int, str]] = {}
    for entries in ordering.values():
        use_ts = all(ts is not None for _, ts in entries)
        try:
            ranked = sorted(entries, key=(lambda e: (e[1], e[0])) if use_ts else (lambda e: e[0]))
        except TypeError:
            use_ts, ranked = False, sorted(entries, key=lambda e: e[0])
        for rank, (ordinal, _) in enumerate(ranked, start=1):
            index_of[ordinal] = (rank, "timestamp" if use_ts else "file_order")
    renumbered: dict[str, ParsedFile] = {}
    for ordinal, session, mapping in parsed:
        rank, source = index_of.get(
            ordinal, (1, "file_order" if session.participant is None else "timestamp")
        )
        new_session = ReplaySession(
            game_id=session.game_id,
            participant=session.participant,
            session_index=rank,
            completion_counts=session.completion_counts,
            source_file=session.source_file,
            actions_total=session.actions_total,
            session_id=session.session_id,
        )
        new_mapping = dict(mapping)
        new_mapping["session_order_source"] = source
        renumbered[session.source_file] = ParsedFile(
            session.source_file,
            sha256_of(raw_dir / session.source_file),
            (raw_dir / session.source_file).stat().st_size,
            (new_session,),
            new_mapping,
        )
    result.files = [renumbered.get(f.source_file, f) for f in result.files]
    return result
