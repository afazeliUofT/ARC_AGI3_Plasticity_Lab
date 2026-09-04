"""Unit tests for arc_plasticity.core.config against the real E000 config."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from arc_plasticity.core.config import (
    ConfigError,
    config_hash,
    config_to_yaml,
    load_experiment_config,
    resolve_config,
)

ROOT = Path(__file__).resolve().parents[2]
E000 = ROOT / "configs" / "experiments" / "E000_bootstrap.yaml"


def test_e000_config_matches_the_preregistered_smoke_experiment() -> None:
    cfg = load_experiment_config(E000)
    prereg = yaml.safe_load((ROOT / "preregistration" / "G0.yaml").read_text())
    smoke = prereg["smoke_experiment"]
    assert cfg.experiment_id == smoke["experiment_id"]
    assert cfg.network_calls_allowed == smoke["network_calls_allowed"]
    assert cfg.model_calls_allowed == smoke["model_calls_allowed"]
    assert cfg.wallclock_limit_seconds == smoke["wallclock_limit_seconds"]
    assert cfg.seed == prereg["determinism_protocol"]["fixed_seed"]
    assert cfg.language_model.identifier is None
    assert cfg.prompt_hash is None


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    raw = yaml.safe_load(E000.read_text())
    raw["budgets"]["acton_budget"] = 5  # typo must not silently pass
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ConfigError, match="acton_budget"):
        load_experiment_config(path)


def test_missing_config_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_experiment_config(tmp_path / "nope.yaml")


def test_no_wallclock_limit_from_either_source_refuses_to_run(tmp_path: Path) -> None:
    raw = yaml.safe_load(E000.read_text())
    del raw["wallclock_limit_seconds"]
    path = tmp_path / "nolimit.yaml"
    path.write_text(yaml.safe_dump(raw))
    cfg = load_experiment_config(path)
    assert cfg.wallclock_limit_seconds is None
    with pytest.raises(ConfigError, match="no limit"):
        resolve_config(cfg, wallclock_fallback_seconds=None)
    resolved = resolve_config(cfg, wallclock_fallback_seconds=7200)
    assert resolved.wallclock_limit_seconds == 7200


def test_seed_override_changes_only_the_seed_and_the_hash() -> None:
    cfg = load_experiment_config(E000)
    other = resolve_config(cfg, seed=12346)
    assert other.seed == 12346
    assert other.model_dump(exclude={"seed"}) == cfg.model_dump(exclude={"seed"})
    assert config_hash(other) != config_hash(cfg)
    assert config_hash(resolve_config(cfg, seed=cfg.seed)) == config_hash(cfg)


def test_resolved_yaml_round_trips() -> None:
    cfg = load_experiment_config(E000)
    again = yaml.safe_load(config_to_yaml(cfg))
    assert again == cfg.model_dump(mode="json")
