#!/usr/bin/env python3
"""The single canonical entry point for every experiment (AGENT_CONSTITUTION.md section 11).

    uv run python scripts/run_experiment.py --config configs/experiments/<experiment>.yaml
                                            [--seed N] [--artifacts-root DIR] [--run-id ID]
                                            [--game STEM]

What one invocation does, in order:

1. Load and validate the config; apply ``--seed``; fill a missing wall-clock limit from
   ``state/BUDGET.json`` ``default_experiment_wallclock_seconds``. No limit, no run. If
   ``--game`` is given the runner must declare ``select_game(config, stem)``, which returns
   the config resolved for that one game (G3 ``experiment.one_game_per_run``: the config
   lists every game, the flag selects one, and the selection and the per-game action budget
   are recorded in ``resolved_config.yaml``). If the runner declares ``preflight(config)``,
   it runs here; a ``RunPreflightError`` exits 2 before any run directory exists.
2. Record provenance before anything runs: resolved config, git state, environment info.
3. Run the registered runner inside a ``NetworkGuard`` set to the config's allowance and a
   hard wall-clock limit. A guard violation or timeout is recorded as the run's completion
   status, never hidden.
4. Write results, metrics, environment results and the manifest, then seal the run directory
   with ``SHA256SUMS``. Nothing is written twice.

Exit status 0 only when ``completion_status`` is ``completed``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path

from arc_plasticity.agents import ref_world_model  # noqa: F401  (registers the E300 runner)
from arc_plasticity.core.artifacts import RunArtifactWriter, RunManifest
from arc_plasticity.core.config import (
    ConfigError,
    ExperimentConfig,
    config_hash,
    config_to_yaml,
    load_experiment_config,
    resolve_config,
)
from arc_plasticity.core.guards import (
    Deadline,
    NetworkForbiddenError,
    NetworkGuard,
    WallclockExceededError,
    hard_wallclock_limit,
)
from arc_plasticity.core.provenance import (
    dependency_lock_hash,
    environment_info,
    git_state,
    hardware_description,
    python_version,
)
from arc_plasticity.core.runner import RunOutcome, RunPreflightError, get_runner
from arc_plasticity.environments import (  # noqa: F401  (registers the built-in runners)
    arc_random_walk,
    toy,
)
from arc_plasticity.evaluation import (  # noqa: F401  (registers the E020 and E310 runners)
    backtest_rejection,
    human_baseline_run,
)

ROOT = Path(__file__).resolve().parents[1]


def config_file_sha256(path: Path) -> str:
    """SHA-256 of the config file as committed: identical across the game-runs of a set even
    though ``config_hash`` (the resolved, per-game config) differs by the selected game."""
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def extra_artifacts(config: ExperimentConfig, runner: object = None) -> tuple[str, ...]:
    """The extra one-shot artifacts a config declares under ``runner_params.extra_artifacts``,
    followed by the runner's always-on ``diagnostic_artifacts`` (G3.6b: the REF runner's
    ``plan_traces.jsonl``), which a config never declares and never switches off."""
    raw = config.runner_params.get("extra_artifacts", [])
    if not isinstance(raw, list) or not all(isinstance(n, str) for n in raw):
        raise ConfigError("runner_params.extra_artifacts must be a list of file names")
    diagnostics = getattr(runner, "diagnostic_artifacts", ())
    if not isinstance(diagnostics, tuple) or not all(isinstance(n, str) for n in diagnostics):
        raise ConfigError("runner.diagnostic_artifacts must be a tuple of file names")
    overlap = sorted(set(raw) & set(diagnostics))
    if overlap:
        raise ConfigError(f"runner_params.extra_artifacts redeclares diagnostic {overlap}")
    return tuple(raw) + diagnostics


def budget_wallclock_fallback(root: Path) -> int | None:
    path = root / "state" / "BUDGET.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    value = data.get("default_experiment_wallclock_seconds")
    return int(value) if isinstance(value, int) and value > 0 else None


def make_run_id(seed: int, now: datetime) -> str:
    return f"{now:%Y%m%dT%H%M%SZ}_seed{seed}_{uuid.uuid4().hex[:8]}"


def _empty_outcome() -> RunOutcome:
    return RunOutcome(
        results={},
        metrics=[],
        environment_results=[],
        environment_columns=("environment",),
        model_calls=0,
    )


def run(
    config_path: Path,
    *,
    seed: int | None = None,
    artifacts_root: Path | None = None,
    run_id: str | None = None,
    game: str | None = None,
    root: Path = ROOT,
) -> tuple[Path, str]:
    """Run one experiment. Returns the run directory and its completion status."""
    config: ExperimentConfig = resolve_config(
        load_experiment_config(config_path),
        seed=seed,
        wallclock_fallback_seconds=budget_wallclock_fallback(root),
    )
    runner = get_runner(config.runner)
    if game is not None:
        select_game = getattr(runner, "select_game", None)
        if not callable(select_game):
            raise ConfigError(f"runner {config.runner!r} does not accept --game")
        config = select_game(config, game)
    limit = config.wallclock_limit_seconds
    assert limit is not None  # resolve_config guarantees it

    started = datetime.now(UTC)
    rid = run_id or make_run_id(config.seed, started)
    run_dir = (artifacts_root or root / "artifacts") / config.experiment_id / rid

    git = git_state(root)
    lock_hash = dependency_lock_hash(root)
    cfg_hash = config_hash(config)
    file_hash = config_file_sha256(config_path)
    preflight = getattr(runner, "preflight", None)
    if callable(preflight):
        # A RunPreflightError propagates before any directory exists (constitution: a run
        # over unusable inputs must not leave an artifact directory behind).
        preflight(config)

    status = "completed"
    outcome = _empty_outcome()
    failure: BaseException | None = None
    t0 = time.monotonic()

    with RunArtifactWriter(run_dir, extra_artifacts(config, runner)) as writer:
        writer.write_resolved_config(config_to_yaml(config))
        writer.write_git_state(git.as_text())
        writer.write_environment_info(environment_info())
        writer.log(
            f"run_id={rid} experiment={config.experiment_id} runner={config.runner} "
            f"seed={config.seed} config_hash={cfg_hash} git={git.commit} dirty={git.dirty} "
            f"wallclock_limit={limit}s network_allowed={config.network_calls_allowed}"
        )
        guard = NetworkGuard(config.network_calls_allowed)
        try:
            with guard, hard_wallclock_limit(limit):
                outcome = runner.run(config, writer, Deadline(limit))
        except WallclockExceededError as exc:
            status = "timed_out"
            writer.log_error(f"timed_out: {exc}")
        except NetworkForbiddenError as exc:
            status = "failed"
            writer.log_error(f"network guard: {exc}")
        except Exception as exc:  # noqa: BLE001  not silent: logged to stderr.log, re-raised after sealing
            status = "failed"
            failure = exc
            writer.log_error("".join(traceback.format_exception(exc)))
        elapsed = time.monotonic() - t0

        if outcome.model_calls > config.model_calls_allowed:
            status = "failed"
            writer.log_error(
                f"model calls {outcome.model_calls} exceed allowance {config.model_calls_allowed}"
            )

        results = {
            "experiment_id": config.experiment_id,
            "run_id": rid,
            "seed": config.seed,
            "config_hash": cfg_hash,
            "config_file_sha256": file_hash,
            "completion_status": status,
            "created_utc": started.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "wallclock_seconds": elapsed,
            "results": dict(outcome.results),
            "extra": dict(outcome.extra),
        }
        writer.write_results(results)
        writer.write_metrics(list(outcome.metrics))
        writer.write_environment_results(
            list(outcome.environment_results), list(outcome.environment_columns)
        )
        manifest = RunManifest(
            experiment_id=config.experiment_id,
            run_id=rid,
            timestamp_utc=results["created_utc"],
            git_commit=git.commit,
            git_dirty=git.dirty,
            python_version=python_version(),
            dependency_lock_hash=lock_hash,
            config_hash=cfg_hash,
            environment_generator_version=runner.environment_generator_version,
            seed=config.seed,
            model_identifier=config.language_model.identifier,
            prompt_hash=config.prompt_hash,
            action_budget=config.budgets.action_budget,
            simulation_budget=config.budgets.simulation_budget,
            token_budget=config.budgets.token_budget,
            persistent_state_size_cap=config.budgets.persistent_state_size_cap_bytes,
            hardware=hardware_description(),
            wallclock_limit_seconds=limit,
            completion_status=status,
            wallclock_seconds=elapsed,
            network_calls_allowed=config.network_calls_allowed,
            network_attempts=guard.attempts,
            model_calls_allowed=config.model_calls_allowed,
            model_calls=outcome.model_calls,
        )
        writer.write_manifest(manifest)
        writer.log(f"completion_status={status} wallclock_seconds={elapsed:.3f}")
        writer.finalize()

    if failure is not None:
        raise failure
    return run_dir, status


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=None, help="override the config seed")
    ap.add_argument("--artifacts-root", type=Path, default=None, help="default: artifacts/")
    ap.add_argument("--run-id", default=None, help="default: <utc>_seed<seed>_<8 hex>")
    ap.add_argument(
        "--game", default=None, help="the one game stem this invocation runs (E300: required)"
    )
    args = ap.parse_args(argv)

    try:
        run_dir, status = run(
            args.config,
            seed=args.seed,
            artifacts_root=args.artifacts_root,
            run_id=args.run_id,
            game=args.game,
        )
    except ConfigError as exc:
        print(f"FAIL config: {exc}", file=sys.stderr)
        return 2
    except RunPreflightError as exc:
        print(f"FAIL preflight: {exc}", file=sys.stderr)
        return 2
    rel = run_dir.relative_to(ROOT) if run_dir.is_relative_to(ROOT) else run_dir
    print(json.dumps({"run_dir": str(rel), "completion_status": status}))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
