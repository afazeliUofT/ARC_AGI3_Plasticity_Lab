"""Unit tests for the network guard and the wall-clock deadline."""

from __future__ import annotations

import socket
import time

import pytest

from arc_plasticity.core.guards import (
    Deadline,
    NetworkForbiddenError,
    NetworkGuard,
    WallclockExceededError,
    hard_wallclock_limit,
)


def test_guard_blocks_connect_and_counts_attempts() -> None:
    guard = NetworkGuard(allowed_calls=0)
    with guard:
        with pytest.raises(NetworkForbiddenError), socket.socket() as sock:
            sock.connect(("127.0.0.1", 9))
        with pytest.raises(NetworkForbiddenError):
            socket.getaddrinfo("localhost", 80)
        with pytest.raises(NetworkForbiddenError):
            socket.create_connection(("127.0.0.1", 9), timeout=0.01)
    assert guard.attempts == 3


def test_guard_restores_the_originals() -> None:
    original_connect = socket.socket.connect
    original_gai = socket.getaddrinfo
    with NetworkGuard(allowed_calls=0):
        assert socket.socket.connect is not original_connect
    assert socket.socket.connect is original_connect
    assert socket.getaddrinfo is original_gai


def test_guard_allows_up_to_the_allowance() -> None:
    guard = NetworkGuard(allowed_calls=1)
    with guard:
        # The first attempt passes through to the real resolver for the loopback name.
        assert socket.getaddrinfo("127.0.0.1", 80)
        with pytest.raises(NetworkForbiddenError):
            socket.getaddrinfo("127.0.0.1", 80)
    assert guard.attempts == 2


def test_deadline_with_fake_clock() -> None:
    now = [100.0]
    dl = Deadline(5.0, clock=lambda: now[0])
    assert not dl.expired()
    dl.check()
    now[0] = 104.9
    assert dl.remaining() == pytest.approx(0.1)
    now[0] = 105.0
    assert dl.expired()
    with pytest.raises(WallclockExceededError):
        dl.check()


def test_deadline_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError):
        Deadline(0)


def test_hard_limit_interrupts_a_runner_that_never_polls() -> None:
    with pytest.raises(WallclockExceededError), hard_wallclock_limit(0.05):
        time.sleep(2)
