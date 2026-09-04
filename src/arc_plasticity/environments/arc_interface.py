"""The project's one adapter to the official ARC-AGI-3 toolkit (``arc-agi`` / ``arcengine``).

Everything that both a runner and ``scripts/verify_run.py`` must agree on lives here, so the
recorded digest and the replayed digest come from one definition:

* :func:`canonical_frame_digest` - the digest defined in ``preregistration/G1.yaml``
  ``primary_metric.canonical_frame_digest``. Ordered object ``{"state", "levels_completed",
  "win_levels", "frames"}``, JSON with ``separators=(",", ":")`` and no whitespace, every grid
  in the response as a nested list of ints, SHA-256 of the UTF-8 bytes. Independent of
  ``guid`` and timing by construction.
* :func:`open_offline_arcade` - ``Arcade(OperationMode.OFFLINE, environments_dir=...)``.
  OFFLINE never downloads (docs/EVIDENCE_ARC.md section 3.1).
* :func:`make_environment` - ``Arcade.make`` returns ``None`` on failure and does not raise;
  this wrapper raises :class:`EnvironmentLoadError` so no call site can forget the check.
* :func:`replay_actions` - fresh arcade, fresh env, ``reset()``, then the recorded actions in
  order; returns the final digest or the step at which the toolkit returned ``None``.
* :func:`iter_environment_files` - the file walk the cache manifest and its verifier share.
* :func:`parse_public_game_stems` - the 25 public stems as written in
  ``docs/EVIDENCE_ARC.md`` section 1.1, so no module carries its own copy of the list.

Nothing here makes a network call; callers install ``NetworkGuard`` around it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from arc_agi import Arcade, OperationMode
from arc_agi.wrapper import EnvironmentWrapper
from arcengine import GameAction, GameState

TERMINAL_STATES: frozenset[str] = frozenset({GameState.WIN.value, GameState.GAME_OVER.value})

# Derived Python bytecode is not part of a downloaded environment and is never hashed.
_IGNORED_DIR_NAMES: frozenset[str] = frozenset({"__pycache__"})
_IGNORED_SUFFIXES: frozenset[str] = frozenset({".pyc", ".pyo"})

_STEM_RE = re.compile(r"^[a-z0-9]{4}$")


class EnvironmentLoadError(RuntimeError):
    """``Arcade.make`` returned ``None``: the game is not in the offline cache or failed to load."""


class ReplayError(RuntimeError):
    """A recorded action record is malformed and cannot be replayed."""


@dataclass(frozen=True)
class ActionRecord:
    """One recorded action: the ``GameAction`` id (0-7) and its data (x, y for ACTION6)."""

    action: int
    data: Mapping[str, int] = field(default_factory=dict)

    def game_action(self) -> GameAction:
        # GameAction members are (id, action_type) tuples; the toolkit's own lookup is from_id.
        try:
            return GameAction.from_id(int(self.action))
        except ValueError as exc:
            raise ReplayError(f"action id {self.action!r} is not a GameAction") from exc

    @classmethod
    def from_mapping(cls, record: Mapping[str, Any]) -> ActionRecord:
        if "action" not in record:
            raise ReplayError(f"transition record lacks 'action': {dict(record)!r}")
        raw_data = record.get("data") or {}
        if not isinstance(raw_data, Mapping):
            raise ReplayError(f"transition 'data' is not a mapping: {raw_data!r}")
        return cls(action=int(record["action"]), data={str(k): int(v) for k, v in raw_data.items()})


@dataclass(frozen=True)
class FrameSummary:
    """The fields of a toolkit response that enter the canonical digest."""

    state: str
    levels_completed: int
    win_levels: int
    frames: tuple[tuple[tuple[int, ...], ...], ...]
    available_actions: tuple[int, ...]

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def digest(self) -> str:
        return canonical_frame_digest(
            self.state, self.levels_completed, self.win_levels, self.frames
        )


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of :func:`replay_actions`. ``final_digest`` is ``None`` only on a step failure."""

    game_id: str
    steps_applied: int
    final_digest: str | None
    failed_at_step: int | None
    final_state: str | None

    @property
    def succeeded(self) -> bool:
        return self.final_digest is not None and self.failed_at_step is None


# --------------------------------------------------------------------------- digest


def _grid_to_lists(grid: Any) -> tuple[tuple[int, ...], ...]:
    array = np.asarray(grid)
    if array.ndim != 2:
        raise ValueError(f"a frame grid must be 2-D, got shape {array.shape}")
    return tuple(tuple(int(v) for v in row) for row in array.tolist())


def canonical_frame_digest(
    state: str,
    levels_completed: int,
    win_levels: int,
    frames: Sequence[Sequence[Sequence[int]]],
) -> str:
    """SHA-256 of the pre-registered canonical JSON encoding of a response.

    Key order is the order the pre-registration writes the object in; ``json.dumps`` with
    ``sort_keys=False`` preserves it. Grids are coerced to plain ints so numpy dtypes never
    reach the encoder.
    """
    payload = {
        "state": str(state),
        "levels_completed": int(levels_completed),
        "win_levels": int(win_levels),
        "frames": [[[int(v) for v in row] for row in grid] for grid in frames],
    }
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def summarize_response(response: Any) -> FrameSummary:
    """Reduce a toolkit ``FrameDataRaw`` (or anything with the same attributes) to its digest fields."""
    state = response.state
    state_value = state.value if isinstance(state, GameState) else str(state)
    return FrameSummary(
        state=state_value,
        levels_completed=int(response.levels_completed),
        win_levels=int(response.win_levels),
        frames=tuple(_grid_to_lists(g) for g in response.frame),
        available_actions=tuple(int(a) for a in response.available_actions),
    )


# --------------------------------------------------------------------------- toolkit


def quiet_logger(name: str = "arc_plasticity.arc_interface") -> logging.Logger:
    """A logger the toolkit can write to without flooding a run's stdout."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def open_offline_arcade(environments_dir: Path) -> Arcade:
    """An ``Arcade`` that only scans ``environments_dir``. It never downloads."""
    # arc_agi.scorecard logs through the library logger, not the injected one; keep it quiet
    # so verifier and runner output stay readable. Errors still surface.
    for name in list(logging.Logger.manager.loggerDict) + ["arc_agi"]:
        if name == "arc_agi" or name.startswith("arc_agi."):
            logging.getLogger(name).setLevel(logging.ERROR)
    return Arcade(
        operation_mode=OperationMode.OFFLINE,
        environments_dir=str(environments_dir),
        logger=quiet_logger(),
    )


def make_environment(arcade: Arcade, game_id: str, seed: int) -> EnvironmentWrapper:
    """``Arcade.make`` with the ``None`` return turned into an exception."""
    env = arcade.make(game_id, seed=int(seed))
    if env is None:
        raise EnvironmentLoadError(
            f"Arcade.make({game_id!r}, seed={seed}) returned None: not in the offline cache"
        )
    return env


def step_environment(env: EnvironmentWrapper, record: ActionRecord) -> FrameSummary | None:
    """Apply one recorded action. Returns ``None`` when the toolkit swallowed an exception."""
    action = record.game_action()
    data: dict[str, Any] | None = dict(record.data) if record.data else None
    response = env.step(action, data=data)
    return None if response is None else summarize_response(response)


def replay_actions(
    environments_dir: Path,
    game_id: str,
    seed: int,
    actions: Sequence[ActionRecord],
) -> ReplayResult:
    """Fresh arcade, fresh env, ``reset()``, then every recorded action in order.

    The final digest is that of the last response: the reset response when ``actions`` is
    empty. A ``None`` from ``reset()`` or any ``step()`` ends the replay with
    ``failed_at_step`` set (0 for the reset) and no digest.
    """
    arcade = open_offline_arcade(environments_dir)
    env = make_environment(arcade, game_id, seed)
    reset = env.reset()
    if reset is None:
        return ReplayResult(game_id, 0, None, 0, None)
    current = summarize_response(reset)
    applied = 0
    for index, record in enumerate(actions, start=1):
        nxt = step_environment(env, record)
        if nxt is None:
            return ReplayResult(game_id, applied, None, index, current.state)
        current = nxt
        applied = index
    return ReplayResult(game_id, applied, current.digest(), None, current.state)


# --------------------------------------------------------------------------- cache


def iter_environment_files(environments_dir: Path) -> Iterator[Path]:
    """Every file under the cache, sorted, minus derived bytecode. Shared by manifest and verifier."""
    if not environments_dir.exists():
        return
    for path in sorted(environments_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _IGNORED_DIR_NAMES for part in path.relative_to(environments_dir).parts):
            continue
        if path.suffix in _IGNORED_SUFFIXES:
            continue
        yield path


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_environment_files(environments_dir: Path) -> dict[str, str]:
    """``{relative posix path: sha256}`` for every file :func:`iter_environment_files` yields."""
    return {
        p.relative_to(environments_dir).as_posix(): sha256_of(p)
        for p in iter_environment_files(environments_dir)
    }


def game_stem(game_id: str) -> str:
    """``ls20-9607627b`` -> ``ls20``. The stem is the stable part (EVIDENCE_ARC section 1.1)."""
    return game_id.split("-", 1)[0]


def parse_public_game_stems(markdown: str) -> list[str]:
    """The public stems from the fenced block that follows 'Public game ID stems' in EVIDENCE_ARC."""
    anchor = markdown.find("Public game ID stems")
    if anchor < 0:
        return []
    block = re.search(r"```\s*\n(.*?)```", markdown[anchor:], re.DOTALL)
    if not block:
        return []
    return [tok for tok in block.group(1).split() if _STEM_RE.match(tok)]


def public_game_stems(root: Path) -> list[str]:
    """Read the stems from the evidence base under ``root``. Empty if the document is absent."""
    path = root / "docs" / "EVIDENCE_ARC.md"
    if not path.exists():
        return []
    return parse_public_game_stems(path.read_text(encoding="utf-8"))


__all__ = [
    "TERMINAL_STATES",
    "ActionRecord",
    "EnvironmentLoadError",
    "FrameSummary",
    "ReplayError",
    "ReplayResult",
    "canonical_frame_digest",
    "game_stem",
    "hash_environment_files",
    "iter_environment_files",
    "make_environment",
    "open_offline_arcade",
    "parse_public_game_stems",
    "public_game_stems",
    "quiet_logger",
    "replay_actions",
    "sha256_of",
    "step_environment",
    "summarize_response",
]
