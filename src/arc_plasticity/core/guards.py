"""Run-time guards: no network beyond the declared allowance, no run past its wall-clock limit.

``NetworkGuard`` is the socket guard PROPOSAL_v2.md section 9 (G1) asks for. It is installed
around every experiment by the canonical entry point, with the allowance taken from the
experiment config. It patches the process-wide socket entry points, so any library that opens
a connection, by any route, is caught and counted.

``Deadline`` is the soft limit an experiment loop polls. ``hard_wallclock_limit`` is the hard
limit: a SIGALRM that raises ``WallclockExceededError`` inside the main thread so a runner
that never polls still stops. The supervisor is the final backstop above both.
"""

from __future__ import annotations

import signal
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Self


class NetworkForbiddenError(RuntimeError):
    """A network call was attempted beyond the experiment's declared allowance."""


class WallclockExceededError(RuntimeError):
    """The experiment ran past its declared wall-clock limit."""


class NetworkGuard:
    """Context manager that counts outbound network attempts and raises past the allowance.

    ``attempts`` records every attempt, allowed or not, so a manifest can state the true
    number even when it is zero.
    """

    def __init__(self, allowed_calls: int) -> None:
        if allowed_calls < 0:
            raise ValueError("allowed_calls must be non-negative")
        self.allowed_calls = allowed_calls
        self.attempts = 0
        self._lock = threading.Lock()
        self._originals: dict[str, Any] = {}

    def _record(self, what: str) -> None:
        with self._lock:
            self.attempts += 1
            if self.attempts > self.allowed_calls:
                raise NetworkForbiddenError(
                    f"{what} attempted: network call {self.attempts} exceeds the allowance of "
                    f"{self.allowed_calls} declared in the experiment config"
                )

    def __enter__(self) -> Self:
        guard = self
        originals: dict[str, Any] = {
            "socket.connect": socket.socket.connect,
            "socket.connect_ex": socket.socket.connect_ex,
            "create_connection": socket.create_connection,
            "getaddrinfo": socket.getaddrinfo,
        }

        def connect(sock: socket.socket, address: Any) -> None:
            guard._record(f"socket.connect({address!r})")
            originals["socket.connect"](sock, address)

        def connect_ex(sock: socket.socket, address: Any) -> int:
            guard._record(f"socket.connect_ex({address!r})")
            return int(originals["socket.connect_ex"](sock, address))

        def create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
            guard._record(f"socket.create_connection({address!r})")
            return originals["create_connection"](address, *args, **kwargs)

        def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
            guard._record(f"socket.getaddrinfo({host!r})")
            return originals["getaddrinfo"](host, *args, **kwargs)

        self._originals = originals
        socket.socket.connect = connect  # type: ignore[method-assign, assignment]
        socket.socket.connect_ex = connect_ex  # type: ignore[method-assign, assignment]
        socket.create_connection = create_connection  # type: ignore[assignment]
        socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
        return self

    def __exit__(self, *exc_info: object) -> None:
        socket.socket.connect = self._originals["socket.connect"]  # type: ignore[method-assign]
        socket.socket.connect_ex = self._originals["socket.connect_ex"]  # type: ignore[method-assign]
        socket.create_connection = self._originals["create_connection"]
        socket.getaddrinfo = self._originals["getaddrinfo"]
        self._originals = {}


class Deadline:
    """A monotonic soft deadline that experiment loops poll between steps."""

    def __init__(self, limit_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        if limit_seconds <= 0:
            raise ValueError("limit_seconds must be positive")
        self.limit_seconds = float(limit_seconds)
        self._clock = clock
        self._start = clock()

    def elapsed(self) -> float:
        return self._clock() - self._start

    def remaining(self) -> float:
        return self.limit_seconds - self.elapsed()

    def expired(self) -> bool:
        return self.remaining() <= 0.0

    def check(self) -> None:
        """Raise ``WallclockExceededError`` if the deadline has passed."""
        if self.expired():
            raise WallclockExceededError(
                f"wall-clock limit of {self.limit_seconds:.0f}s exceeded after {self.elapsed():.1f}s"
            )


@contextmanager
def hard_wallclock_limit(limit_seconds: float) -> Iterator[None]:
    """Raise ``WallclockExceededError`` from a SIGALRM once ``limit_seconds`` elapse.

    Only the main thread may install signal handlers; elsewhere this is a no-op and the soft
    ``Deadline`` is the only in-process limit.
    """
    if limit_seconds <= 0:
        raise ValueError("limit_seconds must be positive")
    if threading.current_thread() is not threading.main_thread() or not hasattr(
        signal, "setitimer"
    ):
        yield
        return

    def on_alarm(signum: int, frame: object) -> None:
        raise WallclockExceededError(f"hard wall-clock limit of {limit_seconds:.0f}s reached")

    previous = signal.signal(signal.SIGALRM, on_alarm)
    signal.setitimer(signal.ITIMER_REAL, limit_seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
