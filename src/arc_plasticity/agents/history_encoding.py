"""A compact, lossless text rendering of a history for the induction prompt (G3.5).

The candidate program still receives the history as the plain JSON records of
``PROGRAM_CONTRACT`` (``history_to_wire``); this module only changes how those same records
are shown to the language model inside the prompt. Raw JSON costs about 11 KB per 64x64
grid; the rendering here writes every row as run-length pairs, collapses identical consecutive
rows, and writes each later frame either as the list of cells that changed since the previous
record or in full, whichever is shorter. Decoding is exact: :func:`decode_history_compact`
inverts :func:`encode_history_compact` cell for cell, which ``tests/unit`` asserts.

Format ``rle_rows_delta_v1`` (one record per observation, records in order):

    record <i>: reset | action=<int> data=<json>; state=<str>; levels_completed=<int>;
        available_actions=<json list>
    frame: full, <g> grid(s)              then one line per row group:
        g<k> r<a>: v*n v*n ...            (row a of grid k: value v repeated n times, ...)
        g<k> r<a>-r<b>: v*n ...           (rows a..b inclusive are identical)
    frame: delta from record <i-1>, <c> cell(s)   then one line per grid with changes:
        g<k> (y,x)=v (y,x)=v ...          (every other cell equals record i-1)
    frame: unchanged from record <i-1>

``state`` is written as a JSON string so any character is unambiguous. The digest of this
file (:func:`history_encoding_sha256`) is recorded in every E300 ``results.json`` next to the
encoding name, because the rendering is part of what the model sees.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ENCODING_NAME = "rle_rows_delta_v1"

ENCODING_DESCRIPTION = """\
The recorded history below is a lossless compact rendering of exactly the JSON records your
program will receive (record 0 is the reset observation, record i the observation after the
i-th action). Read it as follows. Each record starts with a line
`record <i>: reset|action=<int> data=<json>; state=<json string>; levels_completed=<int>;
available_actions=<json list>`. Its frame follows in one of three forms.
`frame: full, <g> grid(s)` is followed by row lines `g<k> r<a>: v*n v*n ...` meaning row a of
grid k is value v repeated n times, then the next run, left to right; `g<k> r<a>-r<b>: ...`
means rows a to b inclusive are all identical to the runs given. Rows and columns are 0-based;
grid k row y column x is history[i]["frame"][k][y][x]. `frame: delta from record <i-1>,
<c> cell(s)` is followed by lines `g<k> (y,x)=v ...` listing every cell whose value differs
from record i-1; all other cells are unchanged. `frame: unchanged from record <i-1>` means
the whole frame equals the previous record's. Your program never sees this rendering: it
receives the decoded JSON records described in the program contract.
"""

_RECORD_RE = re.compile(
    r"^record (\d+): (reset|action=(-?\d+) data=(\{.*\})); state=(\".*\"); "
    r"levels_completed=(-?\d+); available_actions=(\[.*\])$"
)
_FULL_RE = re.compile(r"^frame: full, (\d+) grid\(s\)$")
_DELTA_RE = re.compile(r"^frame: delta from record (\d+), (\d+) cell\(s\)$")
_UNCHANGED_RE = re.compile(r"^frame: unchanged from record (\d+)$")
_ROW_RE = re.compile(r"^g(\d+) r(\d+)(?:-r(\d+))?: (.*)$")
_CELLS_RE = re.compile(r"^g(\d+) (.*)$")
_CELL_RE = re.compile(r"^\((\d+),(\d+)\)=(-?\d+)$")
_RUN_RE = re.compile(r"^(-?\d+)\*(\d+)$")


class HistoryEncodingError(ValueError):
    """The compact text does not decode."""


def _rle_row(row: Sequence[int]) -> str:
    runs: list[str] = []
    i = 0
    n = len(row)
    while i < n:
        value = int(row[i])
        j = i
        while j < n and int(row[j]) == value:
            j += 1
        runs.append(f"{value}*{j - i}")
        i = j
    return " ".join(runs) if runs else ""


def _encode_full(frame: Sequence[Sequence[Sequence[int]]]) -> list[str]:
    lines = [f"frame: full, {len(frame)} grid(s)"]
    for k, grid in enumerate(frame):
        rows = [tuple(int(v) for v in row) for row in grid]
        a = 0
        while a < len(rows):
            b = a
            while b + 1 < len(rows) and rows[b + 1] == rows[a]:
                b += 1
            label = f"g{k} r{a}:" if a == b else f"g{k} r{a}-r{b}:"
            body = _rle_row(rows[a])
            lines.append(f"{label} {body}".rstrip())
            a = b + 1
    return lines


def _same_shape(
    previous: Sequence[Sequence[Sequence[int]]], frame: Sequence[Sequence[Sequence[int]]]
) -> bool:
    if len(previous) != len(frame):
        return False
    for pg, g in zip(previous, frame, strict=True):
        if len(pg) != len(g) or any(len(pr) != len(r) for pr, r in zip(pg, g, strict=True)):
            return False
    return True


def _encode_delta(
    index: int,
    previous: Sequence[Sequence[Sequence[int]]],
    frame: Sequence[Sequence[Sequence[int]]],
) -> list[str] | None:
    if not _same_shape(previous, frame):
        return None
    per_grid: list[str] = []
    count = 0
    for k, (pg, g) in enumerate(zip(previous, frame, strict=True)):
        cells: list[str] = []
        for y, (pr, r) in enumerate(zip(pg, g, strict=True)):
            for x, (pv, v) in enumerate(zip(pr, r, strict=True)):
                if int(pv) != int(v):
                    cells.append(f"({y},{x})={int(v)}")
        if cells:
            count += len(cells)
            per_grid.append(f"g{k} " + " ".join(cells))
    if count == 0:
        return [f"frame: unchanged from record {index - 1}"]
    return [f"frame: delta from record {index - 1}, {count} cell(s)", *per_grid]


def encode_history_compact(records: Sequence[Mapping[str, Any]]) -> str:
    """Render wire records (``history_to_wire`` output) as ``rle_rows_delta_v1`` text."""
    lines: list[str] = []
    previous: Sequence[Sequence[Sequence[int]]] | None = None
    for i, record in enumerate(records):
        action = record.get("action")
        if action is None:
            head = "reset"
        else:
            data = json.dumps(dict(action.get("data", {})), sort_keys=True, separators=(",", ":"))
            head = f"action={int(action['action'])} data={data}"
        state = json.dumps(str(record["state"]), ensure_ascii=False)
        available = json.dumps([int(a) for a in record["available_actions"]], separators=(",", ":"))
        lines.append(
            f"record {i}: {head}; state={state}; "
            f"levels_completed={int(record['levels_completed'])}; available_actions={available}"
        )
        frame = record["frame"]
        full = _encode_full(frame)
        delta = _encode_delta(i, previous, frame) if previous is not None else None
        if delta is not None and sum(map(len, delta)) < sum(map(len, full)):
            lines.extend(delta)
        else:
            lines.extend(full)
        previous = frame
    return "\n".join(lines) + "\n"


def _decode_runs(body: str) -> list[int]:
    row: list[int] = []
    for token in body.split():
        match = _RUN_RE.match(token)
        if match is None:
            raise HistoryEncodingError(f"bad run {token!r}")
        row.extend([int(match.group(1))] * int(match.group(2)))
    return row


def decode_history_compact(text: str) -> list[dict[str, Any]]:
    """Invert :func:`encode_history_compact`. Raises :class:`HistoryEncodingError`."""
    lines = [line for line in text.split("\n") if line != ""]
    records: list[dict[str, Any]] = []
    pos = 0
    while pos < len(lines):
        match = _RECORD_RE.match(lines[pos])
        if match is None:
            raise HistoryEncodingError(f"expected a record line at line {pos + 1}: {lines[pos]!r}")
        index = int(match.group(1))
        if index != len(records):
            raise HistoryEncodingError(f"record {index} out of order (expected {len(records)})")
        action: dict[str, Any] | None
        if match.group(2) == "reset":
            action = None
        else:
            action = {"action": int(match.group(3)), "data": json.loads(match.group(4))}
        state = json.loads(match.group(5))
        levels = int(match.group(6))
        available = json.loads(match.group(7))
        pos += 1
        if pos >= len(lines):
            raise HistoryEncodingError(f"record {index} has no frame line")
        frame: list[list[list[int]]]
        full = _FULL_RE.match(lines[pos])
        delta = _DELTA_RE.match(lines[pos])
        unchanged = _UNCHANGED_RE.match(lines[pos])
        pos += 1
        if full is not None:
            frame = [[] for _ in range(int(full.group(1)))]
            while pos < len(lines) and (row := _ROW_RE.match(lines[pos])) is not None:
                k, a = int(row.group(1)), int(row.group(2))
                b = int(row.group(3)) if row.group(3) is not None else a
                if k >= len(frame) or a != len(frame[k]) or b < a:
                    raise HistoryEncodingError(f"row line out of place: {lines[pos]!r}")
                values = _decode_runs(row.group(4))
                frame[k].extend([list(values) for _ in range(b - a + 1)])
                pos += 1
        elif delta is not None or unchanged is not None:
            ref = int((delta or unchanged).group(1))  # type: ignore[union-attr]
            if ref != index - 1 or not records:
                raise HistoryEncodingError(f"record {index} refers to record {ref}")
            frame = [[list(r) for r in g] for g in records[-1]["frame"]]
            if delta is not None:
                counted = 0
                while pos < len(lines) and (cells := _CELLS_RE.match(lines[pos])) is not None:
                    if _RECORD_RE.match(lines[pos]):
                        break
                    k = int(cells.group(1))
                    for token in cells.group(2).split():
                        cell = _CELL_RE.match(token)
                        if cell is None:
                            raise HistoryEncodingError(f"bad cell {token!r}")
                        y, x, v = (int(cell.group(j)) for j in (1, 2, 3))
                        frame[k][y][x] = v
                        counted += 1
                    pos += 1
                if counted != int(delta.group(2)):
                    raise HistoryEncodingError(
                        f"record {index} lists {counted} cells, header says {delta.group(2)}"
                    )
        else:
            raise HistoryEncodingError(f"bad frame line for record {index}: {lines[pos - 1]!r}")
        records.append(
            {
                "action": action,
                "frame": frame,
                "state": state,
                "levels_completed": levels,
                "available_actions": available,
            }
        )
    return records


def history_encoding_sha256() -> str:
    """SHA-256 of this file, recorded in every E300 results.json as history_encoding.module_sha256."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


__all__ = [
    "ENCODING_DESCRIPTION",
    "ENCODING_NAME",
    "HistoryEncodingError",
    "decode_history_compact",
    "encode_history_compact",
    "history_encoding_sha256",
]
