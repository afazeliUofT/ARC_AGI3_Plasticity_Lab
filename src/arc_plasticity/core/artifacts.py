"""The run artifact contract: every run writes the same files, once, and seals them.

AGENT_CONSTITUTION.md section 11 lists the files every run produces and the keys every
manifest carries. ``scripts/verify_run.py`` checks the same list; a unit test asserts the two
agree. Raw evidence is never overwritten (section 4): the writer refuses to reuse a run
directory, refuses to write any contract file twice, and refuses every write after
``finalize`` has written ``SHA256SUMS``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import IO, Any, Self

CONTRACT_FILES: tuple[str, ...] = (
    "manifest.json",
    "resolved_config.yaml",
    "results.json",
    "metrics.csv",
    "environment_results.csv",
    "transitions.jsonl",
    "hypotheses.jsonl",
    "memory_operations.jsonl",
    "stdout.log",
    "stderr.log",
    "git_state.txt",
    "environment_info.json",
    "SHA256SUMS",
)

SUMS_FILE = "SHA256SUMS"
_STREAM_FILES = ("transitions.jsonl", "hypotheses.jsonl", "memory_operations.jsonl", "stdout.log", "stderr.log")

COMPLETION_STATUSES = ("completed", "timed_out", "failed")


class ArtifactError(RuntimeError):
    """A write would violate the artifact contract or the raw-evidence rule."""


@dataclass(frozen=True)
class RunManifest:
    """Every key the constitution requires, in the order it lists them, plus run accounting."""

    experiment_id: str
    run_id: str
    timestamp_utc: str
    git_commit: str
    git_dirty: bool
    python_version: str
    dependency_lock_hash: str
    config_hash: str
    environment_generator_version: str
    seed: int
    model_identifier: str | None
    prompt_hash: str | None
    action_budget: int
    simulation_budget: int
    token_budget: int
    persistent_state_size_cap: int
    hardware: str
    wallclock_limit_seconds: int
    completion_status: str
    wallclock_seconds: float
    network_calls_allowed: int
    network_attempts: int
    model_calls_allowed: int
    model_calls: int

    def __post_init__(self) -> None:
        if self.completion_status not in COMPLETION_STATUSES:
            raise ArtifactError(
                f"completion_status {self.completion_status!r} not in {COMPLETION_STATUSES}"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _csv_text(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    """Render rows as CSV with a fixed column order. Every row must supply every column."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(list(columns))
    for i, row in enumerate(rows):
        missing = [c for c in columns if c not in row]
        extra = [k for k in row if k not in columns]
        if missing or extra:
            raise ArtifactError(f"row {i} columns mismatch: missing={missing} extra={extra}")
        writer.writerow([row[c] for c in columns])
    return buf.getvalue()


class RunArtifactWriter:
    """Writes one run directory under the contract. Use as a context manager.

    Order of use: open (creates the directory and the five streaming files), any number of
    ``log`` / ``append_*`` calls interleaved with the one-shot ``write_*`` calls, then
    ``finalize``, which closes the streams, checks every contract file exists and writes
    ``SHA256SUMS``. Leaving the context without ``finalize`` closes the streams but leaves the
    directory unsealed, which the verifier reports as incomplete.
    """

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self._streams: dict[str, IO[str]] = {}
        self._sealed = False
        self._opened = False

    # ----------------------------------------------------------------- lifecycle

    def open(self) -> RunArtifactWriter:
        if self._opened:
            raise ArtifactError(f"{self.run_dir} already opened")
        if self.run_dir.exists():
            raise ArtifactError(
                f"run directory {self.run_dir} already exists; raw evidence is never overwritten"
            )
        self.run_dir.mkdir(parents=True, exist_ok=False)
        for name in _STREAM_FILES:
            self._streams[name] = (self.run_dir / name).open("x", encoding="utf-8")
        self._opened = True
        return self

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._close_streams()

    def _close_streams(self) -> None:
        for stream in self._streams.values():
            if not stream.closed:
                stream.close()

    def _guard(self, name: str) -> None:
        if not self._opened:
            raise ArtifactError("writer not opened")
        if self._sealed:
            raise ArtifactError(f"cannot write {name}: {self.run_dir} is sealed by {SUMS_FILE}")

    def _write_once(self, name: str, text: str) -> Path:
        self._guard(name)
        if name not in CONTRACT_FILES:
            raise ArtifactError(f"{name} is not a contract file")
        path = self.run_dir / name
        if path.exists():
            raise ArtifactError(f"{path} already written; raw evidence is never overwritten")
        with path.open("x", encoding="utf-8") as fh:
            fh.write(text)
        return path

    # ----------------------------------------------------------------- streams

    def _append(self, name: str, record: Mapping[str, Any]) -> None:
        self._guard(name)
        stream = self._streams[name]
        stream.write(json.dumps(dict(record), sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()

    def append_transition(self, record: Mapping[str, Any]) -> None:
        self._append("transitions.jsonl", record)

    def append_hypothesis(self, record: Mapping[str, Any]) -> None:
        self._append("hypotheses.jsonl", record)

    def append_memory_operation(self, record: Mapping[str, Any]) -> None:
        self._append("memory_operations.jsonl", record)

    def log(self, message: str) -> None:
        self._guard("stdout.log")
        self._streams["stdout.log"].write(message.rstrip("\n") + "\n")
        self._streams["stdout.log"].flush()

    def log_error(self, message: str) -> None:
        self._guard("stderr.log")
        self._streams["stderr.log"].write(message.rstrip("\n") + "\n")
        self._streams["stderr.log"].flush()

    # ----------------------------------------------------------------- one-shot files

    def write_resolved_config(self, yaml_text: str) -> Path:
        return self._write_once("resolved_config.yaml", yaml_text)

    def write_git_state(self, text: str) -> Path:
        return self._write_once("git_state.txt", text)

    def write_environment_info(self, info: Mapping[str, Any]) -> Path:
        return self._write_once("environment_info.json", _canonical_json(dict(info)))

    def write_results(self, results: Mapping[str, Any]) -> Path:
        return self._write_once("results.json", _canonical_json(dict(results)))

    def write_metrics(self, rows: Sequence[Mapping[str, Any]]) -> Path:
        return self._write_once("metrics.csv", _csv_text(rows, ("metric", "value")))

    def write_environment_results(
        self, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]
    ) -> Path:
        return self._write_once("environment_results.csv", _csv_text(rows, columns))

    def write_manifest(self, manifest: RunManifest) -> Path:
        return self._write_once("manifest.json", _canonical_json(manifest.to_dict()))

    # ----------------------------------------------------------------- seal

    def finalize(self) -> dict[str, str]:
        """Close streams, check completeness, write ``SHA256SUMS``. Returns name -> digest."""
        self._guard(SUMS_FILE)
        self._close_streams()
        missing = [n for n in CONTRACT_FILES if n != SUMS_FILE and not (self.run_dir / n).exists()]
        if missing:
            raise ArtifactError(f"cannot seal {self.run_dir}: missing {missing}")
        digests: dict[str, str] = {}
        for path in sorted(p for p in self.run_dir.rglob("*") if p.is_file()):
            rel = str(path.relative_to(self.run_dir))
            if rel == SUMS_FILE:
                raise ArtifactError(f"{SUMS_FILE} already present in {self.run_dir}")
            digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        text = "".join(f"{digest}  {rel}\n" for rel, digest in digests.items())
        with (self.run_dir / SUMS_FILE).open("x", encoding="utf-8") as fh:
            fh.write(text)
        self._sealed = True
        return digests

    @property
    def sealed(self) -> bool:
        return self._sealed
