"""Sandboxed execution of candidate world-model programs (preregistration/G3.yaml ``sandbox``).

A candidate program runs in a **separate Python subprocess** (the worker,
``sandbox_worker.py``) with:

* ``NetworkGuard(allowed_calls=0)`` installed for the life of the process;
* ``resource.RLIMIT_AS`` set to the caller's ``address_space_bytes_max``;
* a per-prediction SIGALRM inside the worker **and** a parent-side read timeout, so a program
  that swallows the alarm is still killed;
* its working directory in a fresh temporary directory outside the repository, an environment
  stripped to the interpreter's needs (no ``ARC_API_KEY``), and an in-process file guard that
  refuses writes under the repository and reads under ``environment_files/`` and ``data/``.
  The guard is best effort (a program using ``ctypes`` could bypass it); the structural
  control is the cwd and the absence of credentials, and every refusal is recorded.

The parent speaks a line-delimited JSON protocol over the worker's stdin/stdout. The worker
keeps the history it has been sent and the parent extends it incrementally, so the program
still receives the **complete** history list on every call while the transport stays linear.
Program ``print`` output is diverted to stderr so it cannot corrupt the protocol.

Every limit is a constructor argument; nothing numeric is defined here.
"""

from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Self

from arc_plasticity.core.guards import Deadline
from arc_plasticity.environments.arc_interface import ActionRecord
from arc_plasticity.hypotheses.interface import (
    History,
    HistoryError,
    Observation,
    WorldModelError,
    action_to_wire,
    history_to_wire,
    observation_from_wire,
    transition_to_wire,
)

VIOLATION_KINDS: tuple[str, ...] = (
    "load_failed",
    "raised",
    "predict_timeout",
    "memory",
    "network",
    "filesystem",
    "protocol",
    "worker_died",
)

_STDERR_TAIL_BYTES = 4000


class SandboxViolation(WorldModelError):
    """The program broke a sandbox rule or failed; ``kind`` is one of :data:`VIOLATION_KINDS`."""

    def __init__(self, kind: str, message: str, detail: str | None = None) -> None:
        if kind not in VIOLATION_KINDS:
            raise ValueError(f"unknown violation kind {kind!r}")
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message
        self.detail = detail


@dataclass(frozen=True)
class SandboxLimits:
    """The three pre-registered sandbox limits plus the parent's kill grace."""

    backtest_seconds_max: float
    predict_seconds_max: float
    address_space_bytes_max: int
    kill_grace_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.backtest_seconds_max <= 0 or self.predict_seconds_max <= 0:
            raise ValueError("time limits must be positive")
        if self.address_space_bytes_max <= 0:
            raise ValueError("address_space_bytes_max must be positive")
        if self.kill_grace_seconds < 0:
            raise ValueError("kill_grace_seconds must be non-negative")


@dataclass(frozen=True)
class SandboxGuards:
    """Paths the worker's file guard enforces. ``repository_root`` is write-forbidden; the
    ``forbidden_read_roots`` are read-forbidden as well."""

    repository_root: Path
    forbidden_read_roots: tuple[Path, ...]

    def to_wire(self) -> dict[str, Any]:
        return {
            "repository_root": str(self.repository_root.resolve()),
            "forbidden_read_roots": [str(p.resolve()) for p in self.forbidden_read_roots],
        }


def default_guards(repository_root: Path) -> SandboxGuards:
    return SandboxGuards(
        repository_root=repository_root,
        forbidden_read_roots=(repository_root / "environment_files", repository_root / "data"),
    )


class _LineReader:
    """Reads newline-terminated messages from a pipe fd with a deadline, using ``select``."""

    def __init__(self, fd: int) -> None:
        self._fd = fd
        self._buffer = bytearray()

    def readline(self, timeout: float) -> bytes | None:
        """A full line without its newline; ``None`` on EOF. Raises ``TimeoutError``."""
        deadline = time.monotonic() + max(timeout, 0.0)
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                line = bytes(self._buffer[:newline])
                del self._buffer[: newline + 1]
                return line
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("no complete line before the deadline")
            ready, _, _ = select.select([self._fd], [], [], remaining)
            if not ready:
                raise TimeoutError("no complete line before the deadline")
            chunk = os.read(self._fd, 1 << 16)
            if not chunk:
                return None
            self._buffer.extend(chunk)


class SandboxedProgram:
    """A candidate program as a :class:`WorldModel`, executed in the worker subprocess.

    Use as a context manager. ``predict`` raises :class:`SandboxViolation` on any failure;
    the backtester turns that into a not-certified record.
    """

    def __init__(
        self,
        source_path: Path,
        limits: SandboxLimits,
        guards: SandboxGuards,
        python_executable: str | None = None,
    ) -> None:
        self.source_path = Path(source_path)
        self.limits = limits
        self.guards = guards
        self._python = python_executable or sys.executable
        self._process: subprocess.Popen[bytes] | None = None
        self._reader: _LineReader | None = None
        self._workdir: Path | None = None
        self._stderr_path: Path | None = None
        self._sent: History | None = None
        self._deadline: Deadline | None = None
        self.violations: list[dict[str, Any]] = []
        self.predictions = 0

    # ------------------------------------------------------------------ lifecycle

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def workdir(self) -> Path | None:
        return self._workdir

    def bind_deadline(self, deadline: Deadline) -> None:
        """Cap every read timeout by the remaining backtest time (called by the backtester)."""
        self._deadline = deadline

    def _environment(self) -> dict[str, str]:
        src_dir = Path(__file__).resolve().parents[2]
        assert self._workdir is not None
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self._workdir),
            "TMPDIR": str(self._workdir),
            "PYTHONPATH": str(src_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }
        for key in ("VIRTUAL_ENV", "LANG", "LC_ALL"):
            if key in os.environ:
                env[key] = os.environ[key]
        return env

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("sandbox already started")
        if not self.source_path.is_file():
            raise SandboxViolation("load_failed", f"{self.source_path} is not a file")
        source = self.source_path.read_text(encoding="utf-8")
        self._workdir = Path(tempfile.mkdtemp(prefix="arc_sandbox_"))
        self._stderr_path = self._workdir / "worker_stderr.log"
        stderr_file = self._stderr_path.open("wb")
        try:
            self._process = subprocess.Popen(
                [self._python, "-m", "arc_plasticity.hypotheses.sandbox_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                cwd=str(self._workdir),
                env=self._environment(),
                close_fds=True,
            )
        finally:
            stderr_file.close()
        assert self._process.stdout is not None
        self._reader = _LineReader(self._process.stdout.fileno())
        response = self._exchange(
            {
                "op": "load",
                "source": source,
                "limits": asdict(self.limits),
                "guards": self.guards.to_wire(),
            },
            timeout=self.limits.predict_seconds_max + self.limits.kill_grace_seconds,
            kind_on_timeout="load_failed",
        )
        if not response.get("ok"):
            self._fail(str(response.get("kind", "load_failed")), response)

    def close(self) -> None:
        process = self._process
        if process is not None:
            if process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:  # pragma: no cover - kernel-level hang
                    pass
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()
        self._process = None
        self._reader = None
        if self._workdir is not None and self._workdir.exists():
            shutil.rmtree(self._workdir, ignore_errors=True)
        self._workdir = None

    def stderr_tail(self) -> str:
        if self._stderr_path is None or not self._stderr_path.exists():
            return ""
        data = self._stderr_path.read_bytes()
        return data[-_STDERR_TAIL_BYTES:].decode("utf-8", errors="replace")

    # ------------------------------------------------------------------ protocol

    def _fail(self, kind: str, response: Mapping[str, Any] | None, message: str = "") -> None:
        text = message or (str(response.get("message", "")) if response else "")
        detail = str(response.get("traceback", "")) if response else self.stderr_tail()
        self.violations.append(
            {"kind": kind, "message": text, "prediction_index": self.predictions}
        )
        self.close()
        raise SandboxViolation(kind, text or kind, detail)

    def _exchange(
        self, request: Mapping[str, Any], timeout: float, kind_on_timeout: str
    ) -> dict[str, Any]:
        process, reader = self._process, self._reader
        if process is None or reader is None or process.stdin is None:
            raise SandboxViolation("worker_died", "sandbox is not running")
        payload = json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n"
        try:
            process.stdin.write(payload)
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            self._fail("worker_died", None, f"worker closed its input: {exc}")
        try:
            line = reader.readline(timeout)
        except TimeoutError:
            self._fail(kind_on_timeout, None, f"no response within {timeout:.1f}s")
        if line is None:
            code = process.poll()
            self._fail("worker_died", None, f"worker exited with code {code}")
        assert line is not None
        try:
            decoded = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._fail("protocol", None, f"undecodable worker response: {exc}")
        if not isinstance(decoded, dict):
            self._fail("protocol", None, "worker response is not an object")
        return dict(decoded)

    def _read_timeout(self) -> float:
        timeout = self.limits.predict_seconds_max + self.limits.kill_grace_seconds
        if self._deadline is not None:
            timeout = min(timeout, max(self._deadline.remaining(), 0.0))
        return timeout

    def _sync_history(self, history: History) -> None:
        if self._sent is not None and self._sent.is_prefix_of(history):
            for transition in history.transitions[len(self._sent) :]:
                response = self._exchange(
                    {"op": "extend", "transition": transition_to_wire(transition)},
                    timeout=self._read_timeout(),
                    kind_on_timeout="predict_timeout",
                )
                if not response.get("ok"):
                    self._fail(str(response.get("kind", "protocol")), response)
        else:
            response = self._exchange(
                {"op": "set_history", "history": history_to_wire(history)},
                timeout=self._read_timeout(),
                kind_on_timeout="predict_timeout",
            )
            if not response.get("ok"):
                self._fail(str(response.get("kind", "protocol")), response)
        self._sent = history

    def predict(self, history: History, action: ActionRecord) -> Observation:
        self._sync_history(history)
        self.predictions += 1
        response = self._exchange(
            {"op": "predict", "action": action_to_wire(action)},
            timeout=self._read_timeout(),
            kind_on_timeout="predict_timeout",
        )
        if not response.get("ok"):
            self._fail(str(response.get("kind", "raised")), response)
        try:
            return observation_from_wire(response.get("prediction"))
        except HistoryError as exc:
            self._fail("protocol", None, f"prediction does not follow the contract: {exc}")
        raise AssertionError("unreachable")  # pragma: no cover


__all__ = [
    "VIOLATION_KINDS",
    "SandboxGuards",
    "SandboxLimits",
    "SandboxViolation",
    "SandboxedProgram",
    "default_guards",
]
