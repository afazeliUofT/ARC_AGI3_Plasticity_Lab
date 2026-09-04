"""Validated experiment configuration.

Every experiment is described by one YAML file under ``configs/experiments/`` and run through
the single canonical entry point ``scripts/run_experiment.py`` (AGENT_CONSTITUTION.md section
11). This module owns the schema. Unknown keys are rejected so a typo in a budget name cannot
silently disable a budget.

Wall-clock discipline (constitution section 2, ``BUDGET.json``): a config may omit its own
``wallclock_limit_seconds``, in which case the caller supplies the fallback read from
``state/BUDGET.json``. An experiment with no limit from either source does not run;
``resolve_config`` raises rather than defaulting.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ConfigError(ValueError):
    """The experiment configuration is missing, malformed, or incomplete."""


class BudgetConfig(BaseModel):
    """The budgets that are frozen during a mechanism comparison (constitution section 4)."""

    model_config = ConfigDict(extra="forbid")

    action_budget: int = Field(ge=0)
    simulation_budget: int = Field(ge=0)
    token_budget: int = Field(ge=0)
    persistent_state_size_cap_bytes: int = Field(ge=0)


class LanguageModelConfig(BaseModel):
    """Which model, if any, the experiment calls. ``None`` means no model at all."""

    model_config = ConfigDict(extra="forbid")

    identifier: str | None = None
    prompt: str | None = None


class ExperimentConfig(BaseModel):
    """One experiment, fully specified. Validated on load, frozen once resolved."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=1)
    experiment_id: str = Field(pattern=r"^E\d{3}_[a-z0-9_]+$")
    description: str = ""
    runner: str = Field(min_length=1)
    seed: int = Field(ge=0)
    wallclock_limit_seconds: int | None = Field(default=None, gt=0)
    network_calls_allowed: int = Field(ge=0)
    model_calls_allowed: int = Field(ge=0)
    budgets: BudgetConfig
    language_model: LanguageModelConfig = LanguageModelConfig()
    runner_params: dict[str, Any] = Field(default_factory=dict)

    @property
    def prompt_hash(self) -> str | None:
        """SHA-256 of the prompt text, or ``None`` when the experiment uses no prompt."""
        prompt = self.language_model.prompt
        if prompt is None:
            return None
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def load_experiment_config(path: Path) -> ExperimentConfig:
    """Parse and validate a config file. Raises ``ConfigError`` with the validation detail."""
    if not path.exists():
        raise ConfigError(f"config file {path} does not exist")
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ConfigError(f"config file {path} is not a mapping")
    try:
        return ExperimentConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"config file {path} is invalid:\n{exc}") from exc


def resolve_config(
    config: ExperimentConfig,
    *,
    seed: int | None = None,
    wallclock_fallback_seconds: int | None = None,
) -> ExperimentConfig:
    """Apply command-line overrides and the budget fallback; refuse to run without a limit.

    The returned config is what actually ran and is what ``resolved_config.yaml`` records.
    """
    updates: dict[str, Any] = {}
    if seed is not None:
        if seed < 0:
            raise ConfigError(f"seed must be non-negative, got {seed}")
        updates["seed"] = seed
    if config.wallclock_limit_seconds is None:
        if wallclock_fallback_seconds is None or wallclock_fallback_seconds <= 0:
            raise ConfigError(
                f"experiment {config.experiment_id} declares no wallclock_limit_seconds and no "
                "positive fallback was supplied; an experiment with no limit does not run"
            )
        updates["wallclock_limit_seconds"] = int(wallclock_fallback_seconds)
    return config.model_copy(update=updates) if updates else config


def config_canonical_json(config: ExperimentConfig) -> str:
    """Canonical serialisation used for hashing: sorted keys, no whitespace."""
    return json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def config_hash(config: ExperimentConfig) -> str:
    """SHA-256 of the resolved config. Two runs with the same hash ran the same experiment."""
    return hashlib.sha256(config_canonical_json(config).encode("utf-8")).hexdigest()


def config_to_yaml(config: ExperimentConfig) -> str:
    """The resolved config as YAML, for ``resolved_config.yaml``."""
    return yaml.safe_dump(config.model_dump(mode="json"), sort_keys=True)
