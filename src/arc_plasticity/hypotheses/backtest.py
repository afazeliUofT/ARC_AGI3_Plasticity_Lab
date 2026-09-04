"""The full-history exact backtester (preregistration/G3.yaml ``backtest_certification``).

A candidate model is certified only if, for **every** recorded transition, its prediction
from the complete prefix reproduces the recorded frame (all grids), state and
levels_completed exactly. ``available_actions`` is compared and recorded but never certifies.
There is no window, no sample and no tolerance: ``history_length_checked`` must equal
``history_length`` and ``mismatches`` must be zero. A model that raises, times out or breaks
a sandbox limit is not certified and the reason is recorded.

The backtester sees only the history and the model; it never knows how a wrong model was
made. E310 imports :func:`backtest` unchanged and records :func:`backtest_module_sha256`.

Limits are constructor arguments (:class:`BacktestLimits`); the runner reads them from the
pre-registration. This module defines no number.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from arc_plasticity.core.guards import Deadline
from arc_plasticity.hypotheses.interface import (
    CERTIFICATION_FIELDS,
    COMPARED_FIELDS,
    History,
    Observation,
    WorldModel,
    WorldModelError,
    interface_sha256,
)
from arc_plasticity.hypotheses.sandbox import (
    SandboxedProgram,
    SandboxGuards,
    SandboxLimits,
    SandboxViolation,
)

BACKTESTER_NAME = "full_history_exact"


@dataclass(frozen=True)
class BacktestLimits:
    """The pre-registered sandbox limits as the backtester needs them."""

    backtest_seconds_max: float
    predict_seconds_max: float
    address_space_bytes_max: int

    def __post_init__(self) -> None:
        if self.backtest_seconds_max <= 0 or self.predict_seconds_max <= 0:
            raise ValueError("time limits must be positive")
        if self.address_space_bytes_max <= 0:
            raise ValueError("address_space_bytes_max must be positive")

    def sandbox_limits(self) -> SandboxLimits:
        return SandboxLimits(
            backtest_seconds_max=self.backtest_seconds_max,
            predict_seconds_max=self.predict_seconds_max,
            address_space_bytes_max=self.address_space_bytes_max,
        )


@runtime_checkable
class DeadlineAware(Protocol):
    """A model that can cap its own waits by the backtest deadline (the sandbox does)."""

    def bind_deadline(self, deadline: Deadline) -> None: ...


@dataclass
class BacktestRecord:
    """What a backtest writes to hypotheses.jsonl. ``certified`` is derived, never set by hand."""

    history_length: int
    history_length_checked: int
    mismatches: int
    first_mismatch_index: int | None
    available_actions_mismatches: int
    field_mismatch_counts: dict[str, int]
    wallclock_seconds: float
    failure_kind: str | None
    reason: str | None
    failed_at_index: int | None
    interface_sha256: str
    backtest_module_sha256: str
    backtester: str = BACKTESTER_NAME
    certification_fields: tuple[str, ...] = CERTIFICATION_FIELDS
    certified: bool = field(init=False)

    def __post_init__(self) -> None:
        self.certified = (
            self.history_length_checked == self.history_length
            and self.mismatches == 0
            and self.failure_kind is None
        )

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["certification_fields"] = list(self.certification_fields)
        return out


def compare_observations(predicted: Observation, actual: Observation) -> dict[str, bool]:
    """``{field: matches}`` over every compared field."""
    return {name: predicted.field(name) == actual.field(name) for name in COMPARED_FIELDS}


def backtest_module_sha256() -> str:
    """SHA-256 of this file; E300 and E310 must record the same value."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def backtest(
    model: WorldModel,
    history: History,
    limits: BacktestLimits,
    clock: Callable[[], float] = time.monotonic,
) -> BacktestRecord:
    """Replay the complete history through ``model`` and grade it exactly.

    For every transition ``i`` the model predicts from ``history.prefix(i)`` and the recorded
    action; the prediction is compared with the recorded observation. All transitions are
    checked, even after a mismatch, so the record states how wrong a model is and
    ``history_length_checked`` equals ``history_length`` whenever the model kept running.
    """
    deadline = Deadline(limits.backtest_seconds_max, clock=clock)
    if isinstance(model, DeadlineAware):
        model.bind_deadline(deadline)
    started = clock()
    field_counts: dict[str, int] = dict.fromkeys(COMPARED_FIELDS, 0)
    mismatches = 0
    first_mismatch: int | None = None
    checked = 0
    failure_kind: str | None = None
    reason: str | None = None
    failed_at: int | None = None

    for index, transition in enumerate(history.transitions):
        if deadline.expired():
            failure_kind, failed_at = "backtest_timeout", index
            reason = f"backtest wall-clock limit {limits.backtest_seconds_max:.1f}s reached"
            break
        try:
            predicted = model.predict(history.prefix(index), transition.action)
        except SandboxViolation as exc:
            failure_kind, reason, failed_at = exc.kind, exc.message, index
            break
        except WorldModelError as exc:
            failure_kind, reason, failed_at = "raised", str(exc), index
            break
        except Exception as exc:  # noqa: BLE001 - recorded as failure_kind, never certified
            failure_kind, failed_at = "raised", index
            reason = f"{type(exc).__name__}: {exc}"
            break
        matches = compare_observations(predicted, transition.observation)
        for name, ok in matches.items():
            if not ok:
                field_counts[name] += 1
        if not all(matches[name] for name in CERTIFICATION_FIELDS):
            mismatches += 1
            if first_mismatch is None:
                first_mismatch = index
        checked = index + 1

    return BacktestRecord(
        history_length=len(history),
        history_length_checked=checked,
        mismatches=mismatches,
        first_mismatch_index=first_mismatch,
        available_actions_mismatches=field_counts["available_actions"],
        field_mismatch_counts=field_counts,
        wallclock_seconds=clock() - started,
        failure_kind=failure_kind,
        reason=reason,
        failed_at_index=failed_at,
        interface_sha256=interface_sha256(),
        backtest_module_sha256=backtest_module_sha256(),
    )


def backtest_program(
    source_path: Path,
    history: History,
    limits: BacktestLimits,
    guards: SandboxGuards,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[BacktestRecord, list[dict[str, Any]]]:
    """Backtest a candidate program file inside the sandbox.

    Returns the record and the sandbox's violation log. A program that fails to load yields
    a record with nothing checked and ``failure_kind`` ``load_failed`` (or the violation kind).
    """
    started = clock()
    program = SandboxedProgram(source_path, limits.sandbox_limits(), guards)
    try:
        program.start()
    except SandboxViolation as exc:
        record = BacktestRecord(
            history_length=len(history),
            history_length_checked=0,
            mismatches=0,
            first_mismatch_index=None,
            available_actions_mismatches=0,
            field_mismatch_counts=dict.fromkeys(COMPARED_FIELDS, 0),
            wallclock_seconds=clock() - started,
            failure_kind=exc.kind,
            reason=exc.message,
            failed_at_index=None,
            interface_sha256=interface_sha256(),
            backtest_module_sha256=backtest_module_sha256(),
        )
        return record, list(program.violations)
    try:
        return backtest(program, history, limits, clock=clock), list(program.violations)
    finally:
        program.close()


__all__ = [
    "BACKTESTER_NAME",
    "BacktestLimits",
    "BacktestRecord",
    "DeadlineAware",
    "backtest",
    "backtest_module_sha256",
    "backtest_program",
    "compare_observations",
]
