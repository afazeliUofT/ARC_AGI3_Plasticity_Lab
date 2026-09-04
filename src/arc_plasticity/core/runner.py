"""The interface every experiment implements, and the registry the entry point resolves.

A runner is the only experiment-specific code the canonical entry point calls. It receives the
resolved config, the artifact writer for its raw streams, and a deadline to poll. It returns a
``RunOutcome`` whose ``results`` and ``metrics`` are the two files compared for determinism,
so a runner must put nothing in them that varies between same-seed runs except names listed
in ``configs/nondeterministic_fields.yaml``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from arc_plasticity.core.artifacts import RunArtifactWriter
from arc_plasticity.core.config import ExperimentConfig
from arc_plasticity.core.guards import Deadline


@dataclass(frozen=True)
class RunOutcome:
    """What a runner hands back. ``environment_columns`` fixes the CSV column order."""

    results: Mapping[str, Any]
    metrics: Sequence[Mapping[str, Any]]
    environment_results: Sequence[Mapping[str, Any]]
    environment_columns: Sequence[str]
    model_calls: int = 0
    extra: Mapping[str, Any] = field(default_factory=dict)


class ExperimentRunner(Protocol):
    """One experiment kind. ``environment_generator_version`` goes into the manifest."""

    name: str
    environment_generator_version: str

    def run(
        self, config: ExperimentConfig, writer: RunArtifactWriter, deadline: Deadline
    ) -> RunOutcome: ...


class RunPreflightError(RuntimeError):
    """A runner's ``preflight`` found its inputs unusable; no run directory is created.

    Raised before ``scripts/run_experiment.py`` opens the artifact writer, so a refused run
    leaves nothing under ``artifacts/``. Runners that need this declare an optional
    ``preflight(config)`` method; runners without one are never asked.
    """


class UnknownRunnerError(KeyError):
    """The config names a runner that is not registered."""


_REGISTRY: dict[str, Callable[[], ExperimentRunner]] = {}


def register_runner(name: str, factory: Callable[[], ExperimentRunner]) -> None:
    if name in _REGISTRY:
        raise ValueError(f"runner {name!r} already registered")
    _REGISTRY[name] = factory


def unregister_runner(name: str) -> None:
    """For tests only: remove a runner registered by a test."""
    _REGISTRY.pop(name, None)


def get_runner(name: str) -> ExperimentRunner:
    try:
        factory = _REGISTRY[name]
    except KeyError as exc:
        raise UnknownRunnerError(
            f"runner {name!r} is not registered; known: {sorted(_REGISTRY)}"
        ) from exc
    return factory()


def registered_runners() -> list[str]:
    return sorted(_REGISTRY)
