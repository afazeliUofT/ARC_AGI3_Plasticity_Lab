"""E300: the reference architecture (REF) game-run runner.

Implements ``preregistration/G3.yaml`` ``reference_architecture`` as one control loop over
one cached public game per invocation (``experiment.one_game_per_run``):

* **episodic_store** - every executed action is appended to ``transitions.jsonl`` with the
  pre-action frame digest, the action, the full post-action frame verbatim, state,
  levels_completed, available_actions, the hypothesis whose prediction was compared, the
  predicted digest and whether it matched.
* **program_induction** - when no certified program exists and the model budget remains, the
  model is asked (through :mod:`arc_plasticity.agents.model_client`) for a program; the
  program is written verbatim to ``world_models/<hypothesis_id>.py`` and logged in
  ``hypotheses.jsonl`` with its sha256, the model call index and its parent.
* **backtest_certification** - :func:`arc_plasticity.hypotheses.backtest.backtest_program`
  over the COMPLETE history, in the sandbox, with the pre-registered limits; the record goes
  to ``backtests.jsonl``.
* **planner** - :func:`arc_plasticity.planning.ref_planner.plan_to_next_level` inside the
  certified program, charged to one :class:`SimulationBudget` per game-run; every plan goes
  to ``plans.jsonl`` with the hypothesis it cites and that hypothesis's certification length.
* **predict_before_act** - the certified program's predicted digest is recorded before every
  executed action; on a mismatch the plan is abandoned, the program decertified and the
  mismatch becomes a counterexample for the next induction call.
* **exploration_fallback** - :class:`ExplorationPolicy` when no certified program or no plan
  exists; the only source of randomness.
* **budget_enforcement** - :class:`LevelAccounting` (level_accounting_rule, per_game_stop_rule)
  enforced by the runner, never by the model; **scoring** through the G2 RHAE adapter.

The loop is written against :class:`GameEnvironment` (``reset`` / ``step`` returning the
toolkit's :class:`FrameSummary`) so the same code runs on the offline toolkit and on the
synthetic world of the unit tests. Every numeric limit arrives through ``runner_params`` (the
config copies them from the pre-registration; the verifier checks the copies); this module
defines none.

Two design decisions recorded in the ledger (G3.4 second half) and restated here:

1. Stop reason ``model_budget_exhausted`` fires when the model budget has been *consumed*
   (calls or tokens at their ceiling, or a configured client refusing) and no certified
   program exists. A configuration with no client and ``model_calls_allowed`` 0 consumes
   nothing, so exploration runs the whole game under the level budget: that is the
   model-free REF, useful as a control and for tests, never a graded configuration.
2. ``step()`` returning ``None`` is a run failure (``per_game_stop_rule`` e): the accounting
   records ``step_failed``, every artifact is written, and :class:`RefRunError` is raised so
   the entry point seals the run as ``failed`` rather than ``completed``.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from arc_agi.wrapper import EnvironmentWrapper

from arc_plasticity.agents import model_client as mc
from arc_plasticity.core.artifacts import RunArtifactWriter
from arc_plasticity.core.config import ExperimentConfig
from arc_plasticity.core.guards import Deadline, NetworkGuard
from arc_plasticity.core.runner import RunOutcome, RunPreflightError, register_runner
from arc_plasticity.environments import arc_interface as ai
from arc_plasticity.evaluation import level_accounting as la
from arc_plasticity.hypotheses import backtest as bt
from arc_plasticity.hypotheses.interface import (
    PROGRAM_CONTRACT,
    History,
    Observation,
    history_to_wire,
    interface_sha256,
    observation_to_wire,
)
from arc_plasticity.hypotheses.sandbox import (
    SandboxedProgram,
    SandboxGuards,
    SandboxViolation,
    default_guards,
)
from arc_plasticity.planning import ref_planner as rp

RUNNER_NAME = "ref_world_model"
ENVIRONMENT_GENERATOR_VERSION = "arc-agi-offline-cache-1.0.0"
OPERATION_MODE = "OFFLINE"
GAME_OVER_STATE = "GAME_OVER"

PROJECT_ROOT = Path(__file__).resolve().parents[3]

EXTRA_ARTIFACTS: tuple[str, ...] = (
    "model_calls.jsonl",
    "model_calls/",
    "world_models/",
    "backtests.jsonl",
    "plans.jsonl",
    "level_accounting.json",
    "rhae.json",
)
MODEL_CALLS_DIR = "model_calls"
WORLD_MODELS_DIR = "world_models"

SOURCE_PLAN = "plan"
SOURCE_EXPLORATION = "exploration"
SOURCE_RESET = "reset"

ENVIRONMENT_COLUMNS: tuple[str, ...] = (
    "environment",
    "level",
    "official_baseline_actions",
    "budget",
    "actions_attributed",
    "completed",
    "completion_action_index",
    "rhae_level_score",
)


class RunnerConfigError(ValueError):
    """``runner_params`` are missing or malformed for this runner."""


class RefRunError(RuntimeError):
    """The game-run failed (a ``None`` from the toolkit): the run is sealed as failed."""


# --------------------------------------------------------------------------- parameters


def _positive_int(
    params: Mapping[str, Any], key: str, minimum: int = 1, prefix: str = "runner_params"
) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RunnerConfigError(f"{prefix}.{key} must be an int >= {minimum}")
    return value


def _non_empty_str(params: Mapping[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise RunnerConfigError(f"runner_params.{key} must be a non-empty string")
    return value


def click_points_for_step(step: int, grid_size: int = 64) -> tuple[tuple[int, int], ...]:
    """The ACTION6 coordinates the planner fans out over: a lattice of pitch ``step``
    starting at ``step // 2``; ``0`` means clicks are not planned over."""
    if step <= 0:
        return ()
    coords = list(range(step // 2, grid_size, step))
    return tuple((x, y) for y in coords for x in coords)


@dataclass(frozen=True)
class RefParams:
    environments_dir: Path
    cache_manifest: Path
    cache_manifest_sha256: str
    games: tuple[str, ...]
    game: str | None
    action_budget_multiplier: int
    simulation_steps_per_game_max: int
    model_calls_per_game_max: int
    tokens_per_game_max: int
    model_effort: str
    induction_min_history: int
    wallclock_reserve_seconds: int
    planner_limits: rp.PlannerLimits
    click_grid_step: int
    limits: bt.BacktestLimits
    model_client: Mapping[str, Any] | None

    @classmethod
    def from_config(cls, config: ExperimentConfig, root: Path = PROJECT_ROOT) -> RefParams:
        params = config.runner_params
        env_dir = Path(_non_empty_str(params, "environments_dir"))
        if not env_dir.is_absolute():
            env_dir = root / env_dir
        manifest = Path(_non_empty_str(params, "cache_manifest"))
        if not manifest.is_absolute():
            manifest = root / manifest
        digest = _non_empty_str(params, "cache_manifest_sha256").lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise RunnerConfigError("runner_params.cache_manifest_sha256 must be a 64-hex sha256")
        games_raw = params.get("games")
        if (
            not isinstance(games_raw, list)
            or not games_raw
            or not all(isinstance(g, str) and g for g in games_raw)
            or len(set(games_raw)) != len(games_raw)
        ):
            raise RunnerConfigError(
                "runner_params.games must be a non-empty list of distinct stems"
            )
        game_raw = params.get("game")
        if game_raw is not None and (not isinstance(game_raw, str) or game_raw not in games_raw):
            raise RunnerConfigError(f"runner_params.game {game_raw!r} is not one of games")
        effort = _non_empty_str(params, "model_effort")
        planner_raw = params.get("planner")
        if not isinstance(planner_raw, dict):
            raise RunnerConfigError("runner_params.planner must be a mapping")
        planner_prefix = "runner_params.planner"
        click_step = _positive_int(planner_raw, "click_grid_step", 0, planner_prefix)
        try:
            planner_limits = rp.PlannerLimits(
                max_depth=_positive_int(planner_raw, "max_depth", 1, planner_prefix),
                max_nodes=_positive_int(planner_raw, "max_nodes", 1, planner_prefix),
                click_points=click_points_for_step(click_step),
            )
        except rp.PlannerError as exc:
            raise RunnerConfigError(f"runner_params.planner: {exc}") from exc
        limits_raw = params.get("sandbox_limits")
        if not isinstance(limits_raw, dict):
            raise RunnerConfigError("runner_params.sandbox_limits must be a mapping")
        expected = {"backtest_seconds_max", "predict_seconds_max", "address_space_bytes_max"}
        if set(limits_raw) != expected:
            raise RunnerConfigError(
                f"runner_params.sandbox_limits must have exactly {sorted(expected)}"
            )
        for key, value in limits_raw.items():
            if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
                raise RunnerConfigError(f"runner_params.sandbox_limits.{key} must be positive")
        client_raw = params.get("model_client")
        if client_raw is not None and not isinstance(client_raw, dict):
            raise RunnerConfigError("runner_params.model_client must be a mapping or absent")
        extras = params.get("extra_artifacts")
        if extras != list(EXTRA_ARTIFACTS):
            raise RunnerConfigError(
                f"runner_params.extra_artifacts must be exactly {list(EXTRA_ARTIFACTS)}"
            )
        return cls(
            environments_dir=env_dir,
            cache_manifest=manifest,
            cache_manifest_sha256=digest,
            games=tuple(games_raw),
            game=game_raw,
            action_budget_multiplier=_positive_int(params, "action_budget_multiplier"),
            simulation_steps_per_game_max=_positive_int(params, "simulation_steps_per_game_max"),
            model_calls_per_game_max=_positive_int(params, "model_calls_per_game_max", 0),
            tokens_per_game_max=_positive_int(params, "tokens_per_game_max", 0),
            model_effort=effort,
            induction_min_history=_positive_int(params, "induction_min_history", 0),
            wallclock_reserve_seconds=_positive_int(params, "wallclock_reserve_seconds", 0),
            planner_limits=planner_limits,
            click_grid_step=click_step,
            limits=bt.BacktestLimits(
                backtest_seconds_max=float(limits_raw["backtest_seconds_max"]),
                predict_seconds_max=float(limits_raw["predict_seconds_max"]),
                address_space_bytes_max=int(limits_raw["address_space_bytes_max"]),
            ),
            model_client=client_raw,
        )


# --------------------------------------------------------------------------- cache manifest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_game_id(params: RefParams, stem: str) -> str:
    """The full game id of ``stem`` from the committed cache manifest, whose digest must equal
    the one the config carries (the verifier checks that copy against the locked value)."""
    if not params.cache_manifest.is_file():
        raise RunnerConfigError(f"cache manifest {params.cache_manifest} does not exist")
    actual = _sha256(params.cache_manifest)
    if actual != params.cache_manifest_sha256:
        raise RunnerConfigError(
            f"{params.cache_manifest} sha256 {actual} != configured {params.cache_manifest_sha256}"
        )
    doc = json.loads(params.cache_manifest.read_text(encoding="utf-8"))
    for entry in doc.get("games", []):
        if entry.get("stem") == stem and isinstance(entry.get("game_id"), str):
            return str(entry["game_id"])
    raise RunnerConfigError(f"stem {stem!r} is not in {params.cache_manifest}")


# --------------------------------------------------------------------------- environment


class GameEnvironment(Protocol):
    """What the loop steps: the toolkit wrapper or a synthetic world (tests)."""

    def reset(self) -> ai.FrameSummary | None: ...

    def step(self, action: ai.ActionRecord) -> ai.FrameSummary | None: ...


class ToolkitEnvironment:
    """The offline toolkit environment behind :class:`GameEnvironment`."""

    def __init__(self, env: EnvironmentWrapper) -> None:
        self._env = env

    def reset(self) -> ai.FrameSummary | None:
        response = self._env.reset()
        return None if response is None else ai.summarize_response(response)

    def step(self, action: ai.ActionRecord) -> ai.FrameSummary | None:
        return ai.step_environment(self._env, action)


# --------------------------------------------------------------------------- prompt


def build_prompt(
    template: str,
    history: History,
    counterexamples: Sequence[Mapping[str, Any]],
    rejected_sources: Sequence[tuple[str, str]],
    remaining_actions_on_level: int | None,
    current_level: int | None,
) -> str:
    """The induction prompt: the committed template, the program contract, the run's own
    history, the rejected programs with their counterexamples, and the remaining budget.

    Nothing from environment_files/ or data/ enters here (leak_controls); the official
    baseline appears only as the remaining per-level budget, which the platform's public 5n
    rule makes public.
    """
    parts = [template.rstrip(), "", "## Program contract", "", PROGRAM_CONTRACT.rstrip(), ""]
    budget_line = (
        f"current level: {current_level}; actions remaining on this level: "
        f"{remaining_actions_on_level}"
    )
    parts += ["## Budget", "", budget_line, ""]
    if rejected_sources:
        parts += ["## Rejected programs (most recent last)", ""]
        for hypothesis_id, source in rejected_sources:
            parts += [f"### {hypothesis_id}", "", "```python", source.rstrip(), "```", ""]
    if counterexamples:
        parts += ["## Counterexamples", ""]
        for ce in counterexamples:
            parts.append(json.dumps(dict(ce), sort_keys=True, separators=(",", ":")))
        parts.append("")
    parts += [
        "## Recorded history (JSON; record 0 is the reset observation)",
        "",
        json.dumps(history_to_wire(history), separators=(",", ":")),
        "",
        "Reply with one Python program in a ```python fenced block.",
    ]
    return "\n".join(parts) + "\n"


# --------------------------------------------------------------------------- the game-run


@dataclass
class CertifiedProgram:
    hypothesis_id: str
    program: SandboxedProgram
    certification_history_length: int


@dataclass
class GameRunReport:
    """Everything ``results.json`` and the CSVs need, plus the accounting object."""

    game_id: str
    stem: str
    game_index: int
    seed: int
    accounting: la.LevelAccounting
    final_state: str | None
    final_frame_sha256: str | None
    exploration_actions: int
    plan_actions: int
    reset_actions: int
    model_calls: int
    tokens_by_kind: dict[str, int]
    hypotheses_proposed: int
    hypotheses_certified: int
    plans_searched: int
    plans_executed: int
    prediction_mismatches: int
    predictions_compared: int
    predictions_matched: int
    simulation_budget: dict[str, int]
    exploration: dict[str, Any]
    model_unavailable_reason: str | None
    model_budget_consumed: bool
    step_failed_at: int | None
    counterexamples: list[dict[str, Any]] = field(default_factory=list)


class RefGameRun:
    """One game-run: the REF control loop over a :class:`GameEnvironment`."""

    def __init__(
        self,
        *,
        game_id: str,
        game_index: int,
        seed: int,
        environment: GameEnvironment,
        baselines: Sequence[int],
        params: RefParams,
        client: mc.ModelClient | None,
        writer: RunArtifactWriter,
        deadline: Deadline,
        model_identifier: str | None,
        prompt_template: str | None,
        guards: SandboxGuards | None = None,
    ) -> None:
        self.game_id = game_id
        self.stem = ai.game_stem(game_id)
        self.game_index = int(game_index)
        self.seed = int(seed)
        self.env = environment
        self.params = params
        self.client = client
        self.writer = writer
        self.deadline = deadline
        self.model_identifier = model_identifier
        self.prompt_template = prompt_template or ""
        self.guards = guards or default_guards(PROJECT_ROOT)
        self.accounting = la.LevelAccounting(
            baselines, params.action_budget_multiplier, game_id=game_id
        )
        self.budget = rp.SimulationBudget(params.simulation_steps_per_game_max)
        self.policy = rp.ExplorationPolicy(self.seed, self.game_index)
        self.history: History | None = None
        self.current: ai.FrameSummary | None = None
        self.certified: CertifiedProgram | None = None
        self.queue: deque[ai.ActionRecord] = deque()
        self.queue_plan_index: int | None = None
        self.counterexamples: list[dict[str, Any]] = []
        self.rejected_sources: list[tuple[str, str]] = []
        self.model_calls = 0
        self.tokens_by_kind: dict[str, int] = dict.fromkeys(mc.USAGE_KEYS, 0)
        self.model_unavailable_reason: str | None = None
        self.hypotheses_proposed = 0
        self.hypotheses_certified = 0
        self.last_hypothesis_id: str | None = None
        self.plans: list[dict[str, Any]] = []
        self.backtests: list[dict[str, Any]] = []
        self.model_call_rows: list[dict[str, Any]] = []
        self.plans_executed = 0
        self.prediction_mismatches = 0
        self.predictions_compared = 0
        self.predictions_matched = 0
        self.exploration_actions = 0
        self.plan_actions = 0
        self.reset_actions = 0
        self.step_index = 0
        self.step_failed_at: int | None = None

    # ------------------------------------------------------------------ model budget

    @property
    def tokens_total(self) -> int:
        return sum(self.tokens_by_kind.values())

    def model_budget_consumed(self) -> bool:
        """Design decision 1: consumed, not merely absent."""
        if self.model_unavailable_reason is not None:
            return True
        if self.client is None:
            return False
        if self.params.model_calls_per_game_max > 0 and (
            self.model_calls >= self.params.model_calls_per_game_max
        ):
            return True
        return self.params.tokens_per_game_max > 0 and (
            self.tokens_total >= self.params.tokens_per_game_max
        )

    def may_induce(self) -> bool:
        assert self.history is not None
        return (
            self.client is not None
            and self.certified is None
            and not self.model_budget_consumed()
            and len(self.history) >= self.params.induction_min_history
        )

    # ------------------------------------------------------------------ induction

    def induce(self) -> None:
        """One model call, one program file, one backtest; certifies on success."""
        assert self.history is not None and self.client is not None
        call_index = self.model_calls + 1
        purpose = "induce" if self.last_hypothesis_id is None else "revise"
        prompt = build_prompt(
            self.prompt_template,
            self.history,
            self.counterexamples,
            self.rejected_sources[-1:],
            self.accounting.remaining_on_current_level,
            self.accounting.current_level,
        )
        request = mc.ModelRequest(
            call_index=call_index,
            purpose=purpose,
            prompt=prompt,
            model_identifier=self.model_identifier or "",
            effort=self.params.model_effort,
        )
        try:
            response = self.client.call(request)
        except mc.ModelClientError as exc:
            self.model_unavailable_reason = str(exc)
            self.writer.log(
                f"model call {call_index} refused ({purpose}, prompt_sha256="
                f"{request.prompt_sha256}): {exc}"
            )
            return
        self.model_calls = call_index
        for kind, value in response.tokens_by_kind().items():
            self.tokens_by_kind[kind] += value
        self.writer.write_extra_file(MODEL_CALLS_DIR, f"{call_index}.prompt.txt", prompt)
        self.writer.write_extra_file(
            MODEL_CALLS_DIR,
            f"{call_index}.response.json",
            mc.canonical_response_text(response.raw),
        )
        self.model_call_rows.append(
            {
                "call_index": call_index,
                "purpose": purpose,
                "client_kind": self.client.kind,
                "model_identifier_sent": request.model_identifier,
                "model_identifier_reported": response.model_reported,
                "effort": request.effort,
                "cwd": response.cwd,
                "tools_disabled": response.tools_disabled,
                "prompt_sha256": request.prompt_sha256,
                "response_sha256": response.response_sha256,
                "usage": dict(response.usage),
                "tokens_by_kind": response.tokens_by_kind(),
                "total_cost_usd": response.raw.get("total_cost_usd"),
                "wallclock_seconds": response.wallclock_seconds,
                "exit_code": response.exit_code,
                "prompt_path": f"{MODEL_CALLS_DIR}/{call_index}.prompt.txt",
                "response_path": f"{MODEL_CALLS_DIR}/{call_index}.response.json",
                "history_length_at_call": len(self.history),
            }
        )
        self.hypotheses_proposed += 1
        hypothesis_id = f"h{self.hypotheses_proposed:03d}"
        parent = self.last_hypothesis_id
        self.last_hypothesis_id = hypothesis_id
        source = mc.extract_program_source(response.text)
        path = self.writer.write_extra_file(WORLD_MODELS_DIR, f"{hypothesis_id}.py", source)
        source_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
        record, violations = bt.backtest_program(
            path, self.history, self.params.limits, self.guards
        )
        self.backtests.append(
            {
                "hypothesis_id": hypothesis_id,
                "model_call_index": call_index,
                "source_sha256": source_sha256,
                **record.to_dict(),
                "violations": violations,
            }
        )
        self.writer.append_hypothesis(
            {
                "event": "proposed",
                "hypothesis_id": hypothesis_id,
                "parent_hypothesis_id": parent,
                "model_call_index": call_index,
                "purpose": purpose,
                "source_path": f"{WORLD_MODELS_DIR}/{hypothesis_id}.py",
                "source_sha256": source_sha256,
                "source_bytes": len(source.encode("utf-8")),
                "certified": record.certified,
                "history_length": record.history_length,
                "history_length_checked": record.history_length_checked,
                "mismatches": record.mismatches,
                "first_mismatch_index": record.first_mismatch_index,
                "failure_kind": record.failure_kind,
                "backtest_module_sha256": record.backtest_module_sha256,
                "interface_sha256": record.interface_sha256,
            }
        )
        self.writer.log(
            f"call {call_index} ({purpose}) -> {hypothesis_id} sha256={source_sha256[:16]} "
            f"certified={record.certified} checked={record.history_length_checked}/"
            f"{record.history_length} mismatches={record.mismatches} "
            f"failure_kind={record.failure_kind}"
        )
        if not record.certified:
            self.rejected_sources.append((hypothesis_id, source))
            self.counterexamples.append(
                {
                    "hypothesis_id": hypothesis_id,
                    "kind": "backtest",
                    "history_length": record.history_length,
                    "history_length_checked": record.history_length_checked,
                    "mismatches": record.mismatches,
                    "first_mismatch_index": record.first_mismatch_index,
                    "failure_kind": record.failure_kind,
                    "reason": record.reason,
                }
            )
            return
        program = SandboxedProgram(path, self.params.limits.sandbox_limits(), self.guards)
        try:
            program.start()
        except SandboxViolation as exc:
            self.writer.log(f"{hypothesis_id} certified but failed to reload: {exc}")
            self.counterexamples.append(
                {"hypothesis_id": hypothesis_id, "kind": "reload_failed", "reason": str(exc)}
            )
            return
        self.hypotheses_certified += 1
        self.certified = CertifiedProgram(hypothesis_id, program, len(self.history))

    def decertify(self, reason: str, detail: Mapping[str, Any]) -> None:
        assert self.certified is not None
        cert = self.certified
        self.certified = None
        self.queue.clear()
        self.queue_plan_index = None
        cert.program.close()
        self.writer.append_hypothesis(
            {
                "event": "decertified",
                "hypothesis_id": cert.hypothesis_id,
                "reason": reason,
                "history_length": len(self.history) if self.history else 0,
                **dict(detail),
            }
        )
        self.counterexamples.append(
            {"hypothesis_id": cert.hypothesis_id, "kind": reason, **dict(detail)}
        )
        self.rejected_sources.append(
            (cert.hypothesis_id, cert.program.source_path.read_text(encoding="utf-8"))
        )

    # ------------------------------------------------------------------ planning

    def plan(self) -> None:
        assert self.certified is not None and self.history is not None
        cert = self.certified
        plan = rp.plan_to_next_level(
            cert.program,
            self.history,
            hypothesis_id=cert.hypothesis_id,
            certification_history_length=cert.certification_history_length,
            budget=self.budget,
            limits=self.params.planner_limits,
            deadline=self.deadline,
        )
        plan_index = len(self.plans)
        self.plans.append(
            {
                "plan_index": plan_index,
                "game_id": self.game_id,
                "step_index_at_plan": self.step_index,
                **plan.to_dict(),
                "simulation_budget_used_after": self.budget.used,
            }
        )
        self.writer.log(
            f"plan {plan_index} from {cert.hypothesis_id}: {plan.outcome} "
            f"actions={len(plan.actions)} nodes={plan.nodes_expanded} "
            f"steps={plan.steps_simulated} budget_used={self.budget.used}"
        )
        if plan.outcome == rp.PLAN_FOUND:
            self.queue.extend(plan.actions)
            self.queue_plan_index = plan_index
            self.plans_executed += 1
        elif plan.outcome == rp.PLAN_MODEL_ERROR:
            self.decertify("plan_model_error", {"reason": plan.reason, "plan_index": plan_index})

    # ------------------------------------------------------------------ the loop

    def _choose(self) -> tuple[ai.ActionRecord, str, int | None]:
        assert self.history is not None
        obs = self.history.last_observation()
        if obs.state == GAME_OVER_STATE:
            self.queue.clear()
            self.queue_plan_index = None
            return ai.ActionRecord(la.RESET_ACTION_ID), SOURCE_RESET, None
        if self.certified is not None and not self.queue:
            self.plan()
        if self.queue:
            return self.queue.popleft(), SOURCE_PLAN, self.queue_plan_index
        return self.policy.choose(obs), SOURCE_EXPLORATION, None

    def _predict(self, action: ai.ActionRecord) -> tuple[str | None, str | None]:
        """The certified program's predicted digest for ``action``, charged as one program
        step; ``(None, note)`` when there is no certified program or it could not predict."""
        if self.certified is None or self.history is None:
            return None, None
        if not self.budget.try_consume(1):
            return None, "simulation_budget_exhausted"
        try:
            predicted = self.certified.program.predict(self.history, action)
        except SandboxViolation as exc:
            self.decertify(
                "predict_failed",
                {
                    "step_index": self.step_index + 1,
                    "failure_kind": exc.kind,
                    "reason": exc.message,
                },
            )
            return None, f"predict_failed:{exc.kind}"
        return rp.observation_digest(predicted), None

    def _execute(self) -> bool:
        """One executed action. Returns ``False`` when the run must stop."""
        assert self.history is not None and self.current is not None
        action, source, plan_index = self._choose()
        hypothesis_id = self.certified.hypothesis_id if self.certified else None
        predicted_digest, note = self._predict(action)
        pre = self.current
        pre_observation = self.history.last_observation()
        summary = self.env.step(action)
        if summary is None:
            self.step_failed_at = self.step_index + 1
            self.accounting.stop(la.STOP_STEP_FAILED)
            self.writer.log_error(
                f"step {self.step_failed_at} ({source}, action {action.action} "
                f"{dict(action.data)}) returned None: stop_reason step_failed"
            )
            return False
        actual = Observation.from_summary(summary)
        actual_digest = rp.observation_digest(actual)
        matched: bool | None = None
        if predicted_digest is not None:
            matched = predicted_digest == actual_digest
            self.predictions_compared += 1
            if matched:
                self.predictions_matched += 1
        self.step_index += 1
        self.writer.append_transition(
            {
                "game_id": self.game_id,
                "game_index": self.game_index,
                "step_index": self.step_index,
                "action": int(action.action),
                "data": {k: int(v) for k, v in action.data.items()},
                "source": source,
                "plan_index": plan_index,
                "pre_frame_sha256": pre.digest(),
                "pre_observation_sha256": rp.observation_digest(pre_observation),
                "frame_sha256": summary.digest(),
                "observation_sha256": actual_digest,
                "frame": observation_to_wire(actual)["frame"],
                "state": actual.state,
                "levels_completed": actual.levels_completed,
                "win_levels": summary.win_levels,
                "available_actions": list(actual.available_actions),
                "hypothesis_id": hypothesis_id,
                "predicted_observation_sha256": predicted_digest,
                "prediction_matched": matched,
                "prediction_note": note,
            }
        )
        self.history = self.history.extend(action, actual)
        self.current = summary
        if source == SOURCE_EXPLORATION:
            self.exploration_actions += 1
        elif source == SOURCE_PLAN:
            self.plan_actions += 1
        else:
            self.reset_actions += 1
        if matched is False:
            self.prediction_mismatches += 1
            assert hypothesis_id is not None
            if self.certified is not None and self.certified.hypothesis_id == hypothesis_id:
                self.decertify(
                    "prediction_mismatch",
                    {
                        "step_index": self.step_index,
                        "action": int(action.action),
                        "data": {k: int(v) for k, v in action.data.items()},
                        "predicted_observation_sha256": predicted_digest,
                        "observation_sha256": actual_digest,
                        "plan_index": plan_index,
                    },
                )
        self.accounting.record_action(action.action, actual.levels_completed, actual.state)
        reason = self.accounting.evaluate_stop(actual.state)
        if reason is not None:
            self.accounting.stop(reason)
            return False
        if actual.state == GAME_OVER_STATE:
            self.queue.clear()
            self.queue_plan_index = None
        return True

    def run(self) -> GameRunReport:
        reset = self.env.reset()
        if reset is None:
            raise RefRunError(f"{self.game_id}: reset() returned None before any action")
        self.current = reset
        self.history = History(Observation.from_summary(reset))
        self.writer.log(
            f"{self.game_id} reset: state={reset.state} win_levels={reset.win_levels} "
            f"available={list(reset.available_actions)} frame_sha256={reset.digest()} "
            f"action_budget_total={self.accounting.action_budget_total}"
        )
        try:
            while not self.accounting.stopped:
                if self.deadline.remaining() <= self.params.wallclock_reserve_seconds:
                    self.accounting.stop(la.STOP_WALLCLOCK)
                    self.writer.log("stop: wall-clock reserve reached")
                    break
                if self.may_induce():
                    self.induce()
                    continue
                if self.certified is None and self.model_budget_consumed():
                    self.accounting.stop(la.STOP_MODEL_BUDGET_EXHAUSTED)
                    self.writer.log(
                        f"stop: model budget consumed (calls={self.model_calls}, "
                        f"tokens={self.tokens_total}, unavailable="
                        f"{self.model_unavailable_reason!r}) and no certified program"
                    )
                    break
                if not self._execute():
                    break
        finally:
            if self.certified is not None:
                self.certified.program.close()
            self._write_reports()
        return self.report()

    # ------------------------------------------------------------------ reports

    def report(self) -> GameRunReport:
        return GameRunReport(
            game_id=self.game_id,
            stem=self.stem,
            game_index=self.game_index,
            seed=self.seed,
            accounting=self.accounting,
            final_state=self.current.state if self.current else None,
            final_frame_sha256=self.current.digest() if self.current else None,
            exploration_actions=self.exploration_actions,
            plan_actions=self.plan_actions,
            reset_actions=self.reset_actions,
            model_calls=self.model_calls,
            tokens_by_kind=dict(self.tokens_by_kind),
            hypotheses_proposed=self.hypotheses_proposed,
            hypotheses_certified=self.hypotheses_certified,
            plans_searched=len(self.plans),
            plans_executed=self.plans_executed,
            prediction_mismatches=self.prediction_mismatches,
            predictions_compared=self.predictions_compared,
            predictions_matched=self.predictions_matched,
            simulation_budget=self.budget.to_dict(),
            exploration=self.policy.to_dict(),
            model_unavailable_reason=self.model_unavailable_reason,
            model_budget_consumed=self.model_budget_consumed(),
            step_failed_at=self.step_failed_at,
            counterexamples=list(self.counterexamples),
        )

    def _write_reports(self) -> None:
        acc = self.accounting
        self.writer.write_extra_json("level_accounting.json", acc.to_dict())
        self.writer.write_extra_json(
            "rhae.json",
            {
                "game_id": self.game_id,
                "stem": self.stem,
                "canonical_scoring_baseline": "official metadata.json baseline_actions",
                "official_baseline_actions": list(acc.baselines),
                "levels": [
                    {**r.to_dict(), "rhae_level_score": s}
                    for r, s in zip(acc.level_records(), acc.rhae_level_scores(), strict=True)
                ],
                "rhae_environment_score": acc.rhae_environment_score(),
                "levels_completed": acc.levels_completed,
                "win_levels": acc.win_levels,
                "stop_reason": acc.stop_reason,
            },
        )
        self.writer.write_extra_jsonl("plans.jsonl", self.plans)
        self.writer.write_extra_jsonl("backtests.jsonl", self.backtests)
        self.writer.write_extra_jsonl("model_calls.jsonl", self.model_call_rows)


# --------------------------------------------------------------------------- rows


def results_mapping(
    report: GameRunReport, params: RefParams, config: ExperimentConfig
) -> dict[str, Any]:
    acc = report.accounting
    return {
        "environment_generator_version": ENVIRONMENT_GENERATOR_VERSION,
        "operation_mode": OPERATION_MODE,
        "network_guard": NetworkGuard.__name__,
        "game_id": report.game_id,
        "stem": report.stem,
        "game_index": report.game_index,
        "seed": report.seed,
        "win_levels": acc.win_levels,
        "levels_completed": acc.levels_completed,
        "final_state": report.final_state,
        "final_frame_sha256": report.final_frame_sha256,
        "stop_reason": acc.stop_reason,
        "actions_total": acc.actions_total,
        "resets_issued": acc.resets_issued,
        "exploration_actions": report.exploration_actions,
        "plan_actions": report.plan_actions,
        "reset_actions": report.reset_actions,
        "action_budget_multiplier": acc.multiplier,
        "action_budget_total": acc.action_budget_total,
        "official_baseline_actions": list(acc.baselines),
        "levels": [r.to_dict() for r in acc.level_records()],
        "over_budget_levels": acc.over_budget_levels(),
        "rhae_environment_score": acc.rhae_environment_score(),
        "rhae_level_scores": acc.rhae_level_scores(),
        "model_calls": report.model_calls,
        "model_calls_per_game_max": params.model_calls_per_game_max,
        "tokens_by_kind": report.tokens_by_kind,
        "tokens_total": sum(report.tokens_by_kind.values()),
        "tokens_per_game_max": params.tokens_per_game_max,
        "model_identifier": config.language_model.identifier,
        "model_effort": params.model_effort,
        "model_client_kind": (params.model_client or {}).get("kind", "none"),
        "model_unavailable_reason": report.model_unavailable_reason,
        "model_budget_consumed": report.model_budget_consumed,
        "hypotheses_proposed": report.hypotheses_proposed,
        "hypotheses_certified": report.hypotheses_certified,
        "plans_searched": report.plans_searched,
        "plans_executed": report.plans_executed,
        "predictions_compared": report.predictions_compared,
        "predictions_matched": report.predictions_matched,
        "prediction_mismatches": report.prediction_mismatches,
        "simulation_budget": report.simulation_budget,
        "simulation_steps_per_game_max": params.simulation_steps_per_game_max,
        "exploration": report.exploration,
        "induction_min_history": params.induction_min_history,
        "planner": {
            "max_depth": params.planner_limits.max_depth,
            "max_nodes": params.planner_limits.max_nodes,
            "click_grid_step": params.click_grid_step,
            "click_points": len(params.planner_limits.click_points),
        },
        "sandbox_limits": {
            "backtest_seconds_max": params.limits.backtest_seconds_max,
            "predict_seconds_max": params.limits.predict_seconds_max,
            "address_space_bytes_max": params.limits.address_space_bytes_max,
        },
        "resumptions": 0,
        "step_failed_at": report.step_failed_at,
        "backtest_module_sha256": bt.backtest_module_sha256(),
        "interface_module_sha256": interface_sha256(),
        "model_client_sha256": mc.model_client_sha256(),
        "prompt_hash": config.prompt_hash,
        "level_accounting_rule": la.LEVEL_ACCOUNTING_RULE,
    }


def metrics_rows(report: GameRunReport) -> list[dict[str, Any]]:
    acc = report.accounting
    rows: list[dict[str, Any]] = [
        {"metric": "rhae_environment_score", "value": acc.rhae_environment_score()},
        {"metric": "win_levels", "value": acc.win_levels},
        {"metric": "levels_completed", "value": acc.levels_completed},
        {"metric": "actions_total", "value": acc.actions_total},
        {"metric": "exploration_actions", "value": report.exploration_actions},
        {"metric": "plan_actions", "value": report.plan_actions},
        {"metric": "model_calls", "value": report.model_calls},
        {"metric": "tokens_total", "value": sum(report.tokens_by_kind.values())},
        {"metric": "hypotheses_proposed", "value": report.hypotheses_proposed},
        {"metric": "hypotheses_certified", "value": report.hypotheses_certified},
        {"metric": "plans_executed", "value": report.plans_executed},
        {"metric": "prediction_mismatches", "value": report.prediction_mismatches},
        {"metric": "simulation_steps_used", "value": report.simulation_budget["used"]},
    ]
    for record, score in zip(acc.level_records(), acc.rhae_level_scores(), strict=True):
        prefix = f"level_{record.level}"
        rows += [
            {
                "metric": f"{prefix}_official_baseline_actions",
                "value": record.official_baseline_actions,
            },
            {"metric": f"{prefix}_budget", "value": record.budget},
            {"metric": f"{prefix}_actions_attributed", "value": record.actions_attributed},
            {"metric": f"{prefix}_completed", "value": int(record.completed)},
            {"metric": f"{prefix}_rhae_level_score", "value": score},
        ]
    return rows


def environment_rows(report: GameRunReport) -> list[dict[str, Any]]:
    acc = report.accounting
    return [
        {
            "environment": report.game_id,
            "level": record.level,
            "official_baseline_actions": record.official_baseline_actions,
            "budget": record.budget,
            "actions_attributed": record.actions_attributed,
            "completed": int(record.completed),
            "completion_action_index": record.completion_action_index,
            "rhae_level_score": score,
        }
        for record, score in zip(acc.level_records(), acc.rhae_level_scores(), strict=True)
    ]


# --------------------------------------------------------------------------- runner


class RefWorldModelRunner:
    name = RUNNER_NAME
    environment_generator_version = ENVIRONMENT_GENERATOR_VERSION

    def select_game(self, config: ExperimentConfig, stem: str) -> ExperimentConfig:
        """The config resolved for one game: ``runner_params.game`` set and
        ``budgets.action_budget`` = multiplier x sum(official baselines) of that game."""
        try:
            params = RefParams.from_config(config)
            if stem not in params.games:
                raise RunnerConfigError(f"--game {stem!r} is not one of runner_params.games")
            game_id = resolve_game_id(params, stem)
            baselines = la.load_official_baselines(params.environments_dir, game_id)
        except (RunnerConfigError, la.LevelAccountingError) as exc:
            raise RunPreflightError(str(exc)) from exc
        budget = params.action_budget_multiplier * sum(baselines)
        return config.model_copy(
            update={
                "runner_params": {**config.runner_params, "game": stem},
                "budgets": config.budgets.model_copy(update={"action_budget": budget}),
            }
        )

    def preflight(self, config: ExperimentConfig) -> None:
        """Refuse to run (no run directory) unless every input is what the config claims and
        a model call, if one could be needed, has a client to go to."""
        try:
            params = RefParams.from_config(config)
            if params.game is None:
                raise RunnerConfigError("E300 runs one game per invocation: pass --game <stem>")
            if not params.environments_dir.is_dir():
                raise RunnerConfigError(f"{params.environments_dir} is not a directory")
            game_id = resolve_game_id(params, params.game)
            baselines = la.load_official_baselines(params.environments_dir, game_id)
            expected = params.action_budget_multiplier * sum(baselines)
            if config.budgets.action_budget != expected:
                raise RunnerConfigError(
                    f"budgets.action_budget {config.budgets.action_budget} != "
                    f"{params.action_budget_multiplier} x sum{list(baselines)} = {expected}"
                )
            if config.model_calls_allowed != params.model_calls_per_game_max:
                raise RunnerConfigError(
                    "model_calls_allowed must equal runner_params.model_calls_per_game_max"
                )
            if config.budgets.simulation_budget != params.simulation_steps_per_game_max:
                raise RunnerConfigError(
                    "budgets.simulation_budget must equal runner_params.simulation_steps_per_game_max"
                )
            if config.budgets.token_budget != params.tokens_per_game_max:
                raise RunnerConfigError(
                    "budgets.token_budget must equal runner_params.tokens_per_game_max"
                )
            client = mc.build_client(params.model_client, PROJECT_ROOT)
            try:
                if client is None and config.model_calls_allowed > 0:
                    raise RunnerConfigError(
                        f"model_calls_allowed is {config.model_calls_allowed} but no model "
                        "client is configured (runner_params.model_client); refusing to start"
                    )
                if client is not None and not config.language_model.identifier:
                    raise RunnerConfigError("language_model.identifier is required with a client")
            finally:
                if client is not None:
                    client.close()
        except (RunnerConfigError, la.LevelAccountingError, mc.ModelClientError) as exc:
            raise RunPreflightError(str(exc)) from exc

    def run(
        self, config: ExperimentConfig, writer: RunArtifactWriter, deadline: Deadline
    ) -> RunOutcome:
        params = RefParams.from_config(config)
        if params.game is None:
            raise RunnerConfigError("E300 runs one game per invocation: pass --game <stem>")
        game_id = resolve_game_id(params, params.game)
        game_index = params.games.index(params.game)
        baselines = la.load_official_baselines(params.environments_dir, game_id)
        client = mc.build_client(params.model_client, PROJECT_ROOT)
        writer.log(
            f"{RUNNER_NAME} game={game_id} game_index={game_index} seed={config.seed} "
            f"multiplier={params.action_budget_multiplier} baselines={list(baselines)} "
            f"model_calls_max={params.model_calls_per_game_max} "
            f"tokens_max={params.tokens_per_game_max} client={client.kind if client else None} "
            f"operation_mode={OPERATION_MODE} interface_sha256={interface_sha256()[:16]} "
            f"backtest_sha256={bt.backtest_module_sha256()[:16]} "
            f"model_client_sha256={mc.model_client_sha256()[:16]}"
        )
        arcade = ai.open_offline_arcade(params.environments_dir)
        env = ToolkitEnvironment(ai.make_environment(arcade, game_id, config.seed))
        game_run = RefGameRun(
            game_id=game_id,
            game_index=game_index,
            seed=config.seed,
            environment=env,
            baselines=baselines,
            params=params,
            client=client,
            writer=writer,
            deadline=deadline,
            model_identifier=config.language_model.identifier,
            prompt_template=config.language_model.prompt,
        )
        try:
            report = game_run.run()
        finally:
            if client is not None:
                client.close()
        acc = report.accounting
        writer.log(
            f"finished stop_reason={acc.stop_reason} levels={acc.levels_completed}/"
            f"{acc.win_levels} actions={acc.actions_total} rhae={acc.rhae_environment_score():.4f} "
            f"model_calls={report.model_calls} proposed={report.hypotheses_proposed} "
            f"certified={report.hypotheses_certified} plans_executed={report.plans_executed} "
            f"mismatches={report.prediction_mismatches} exploration={report.exploration_actions}"
        )
        if acc.stop_reason == la.STOP_STEP_FAILED:
            raise RefRunError(
                f"{game_id}: step {report.step_failed_at} returned None (stop_reason "
                "step_failed); the run is a failure, artifacts preserved"
            )
        return RunOutcome(
            results=results_mapping(report, params, config),
            metrics=metrics_rows(report),
            environment_results=environment_rows(report),
            environment_columns=ENVIRONMENT_COLUMNS,
            model_calls=report.model_calls,
        )


register_runner(RUNNER_NAME, RefWorldModelRunner)

__all__ = [
    "ENVIRONMENT_COLUMNS",
    "EXTRA_ARTIFACTS",
    "MODEL_CALLS_DIR",
    "RUNNER_NAME",
    "WORLD_MODELS_DIR",
    "GameEnvironment",
    "GameRunReport",
    "RefGameRun",
    "RefParams",
    "RefRunError",
    "RefWorldModelRunner",
    "RunnerConfigError",
    "ToolkitEnvironment",
    "build_prompt",
    "click_points_for_step",
    "environment_rows",
    "metrics_rows",
    "resolve_game_id",
    "results_mapping",
]
