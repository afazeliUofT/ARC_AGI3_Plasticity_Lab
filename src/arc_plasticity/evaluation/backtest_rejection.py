"""E310: does the full-history exact backtester reject injected wrong models?

Pre-registered in ``preregistration/G3.yaml`` ``backtest_rejection_experiment``. The histories
are the action logs of the graded G1 run, replayed through the offline toolkit into full-frame
:class:`~arc_plasticity.hypotheses.interface.History` objects (every replayed frame digest is
compared with the G1 log and the final digest with the G1 ``results.json``). For every game
the runner draws ``trial_seeds_per_game`` wrong models - the true simulator wrapped with one
seeded mutation from :mod:`arc_plasticity.hypotheses.mutations` - and submits each to
:func:`arc_plasticity.hypotheses.backtest.backtest`, which sees only the history and the
model. ``control_trials_per_game`` control trials submit the unmutated true simulator.

Trial randomness is a pure function of the experiment seed: the class plan of a game comes
from ``default_rng([seed, game_index])`` (balanced blocks: a seeded permutation of the eight
classes, repeated, cut to the trial count, so every class gets at least ``trials // 8`` trials
per game while each trial's class is marginally uniform), and the mutation parameters of a
trial from ``default_rng([seed, game_index, trial_index])``.

A trial is *discriminating* when the mutated prediction differs from the recorded
observation on a certification field at the mutation site (index-targeted classes) or at any
transition (the whole-history classes); the generator checks that by predicting with the
mutated model, never by running the backtester, and re-draws the parameters up to
``redraw_max`` times inside the same class. A trial still non-discriminating is recorded as
*vacuous* and excluded from the rejection denominator. Classes with no parameters cannot
be re-drawn; they are checked once.

Every threshold the verifier applies lives in the pre-registration; this module defines none.
The backtest limits come from ``runner_params.sandbox_limits`` and are recorded in
``results.json`` so the verifier can compare them with the locked values.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from arc_plasticity.core.artifacts import RunArtifactWriter
from arc_plasticity.core.config import ExperimentConfig
from arc_plasticity.core.guards import Deadline, NetworkGuard
from arc_plasticity.core.runner import RunOutcome, RunPreflightError, register_runner
from arc_plasticity.environments import arc_interface as ai
from arc_plasticity.hypotheses import backtest as bt
from arc_plasticity.hypotheses import mutations as mu
from arc_plasticity.hypotheses import true_model as tm
from arc_plasticity.hypotheses.interface import (
    CERTIFICATION_FIELDS,
    History,
    Observation,
    WorldModel,
    interface_sha256,
)

RUNNER_NAME = "backtest_rejection"
ENVIRONMENT_GENERATOR_VERSION = "arc-agi-offline-cache-1.0.0"
OPERATION_MODE = "OFFLINE"
CLASS_ASSIGNMENT = "balanced_blocks"

PROJECT_ROOT = Path(__file__).resolve().parents[3]

ENVIRONMENT_COLUMNS: tuple[str, ...] = (
    "environment",
    "history_length",
    "replay_identity",
    "frame_digest_mismatches",
    "wrong_model_trials",
    "vacuous_trials",
    "rejected_trials",
    "control_trials",
    "control_accepted",
)

ModelFactory = Callable[[str], WorldModel]


class RunnerConfigError(ValueError):
    """``runner_params`` are missing or malformed for this runner."""


class HistorySourceError(RuntimeError):
    """The G1 action log, its digests or its replay do not agree with the config."""


# --------------------------------------------------------------------------- parameters


@dataclass(frozen=True)
class RejectionParams:
    environments_dir: Path
    history_source: Path
    history_source_sha256sums_sha256: str
    games: tuple[str, ...] | None  # stems; None means every game in the log
    trial_seeds_per_game: int
    control_trials_per_game: int
    redraw_max: int
    limits: bt.BacktestLimits

    @classmethod
    def from_config(cls, config: ExperimentConfig, root: Path = PROJECT_ROOT) -> RejectionParams:
        params = config.runner_params

        def positive_int(key: str, minimum: int = 1) -> int:
            value = params.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                raise RunnerConfigError(f"runner_params.{key} must be an int >= {minimum}")
            return value

        def non_empty_str(key: str) -> str:
            value = params.get(key)
            if not isinstance(value, str) or not value:
                raise RunnerConfigError(f"runner_params.{key} must be a non-empty string")
            return value

        env_dir = Path(non_empty_str("environments_dir"))
        if not env_dir.is_absolute():
            env_dir = root / env_dir
        source = Path(non_empty_str("history_source"))
        if not source.is_absolute():
            source = root / source
        sums_digest = non_empty_str("history_source_sha256sums_sha256").lower()
        if len(sums_digest) != 64 or any(c not in "0123456789abcdef" for c in sums_digest):
            raise RunnerConfigError(
                "runner_params.history_source_sha256sums_sha256 must be a 64-hex sha256"
            )
        games_raw = params.get("games", "all")
        games: tuple[str, ...] | None
        if games_raw == "all":
            games = None
        elif (
            isinstance(games_raw, list) and games_raw and all(isinstance(g, str) for g in games_raw)
        ):
            games = tuple(games_raw)
        else:
            raise RunnerConfigError(
                "runner_params.games must be 'all' or a non-empty list of stems"
            )
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
        limits = bt.BacktestLimits(
            backtest_seconds_max=float(limits_raw["backtest_seconds_max"]),
            predict_seconds_max=float(limits_raw["predict_seconds_max"]),
            address_space_bytes_max=int(limits_raw["address_space_bytes_max"]),
        )
        extras = params.get("extra_artifacts", [])
        if extras not in ([], None):
            raise RunnerConfigError("this runner declares no extra artifacts")
        return cls(
            environments_dir=env_dir,
            history_source=source,
            history_source_sha256sums_sha256=sums_digest,
            games=games,
            trial_seeds_per_game=positive_int("trial_seeds_per_game"),
            control_trials_per_game=positive_int("control_trials_per_game", minimum=0),
            redraw_max=positive_int("redraw_max", minimum=0),
            limits=limits,
        )


# --------------------------------------------------------------------------- histories


@dataclass(frozen=True)
class GameHistory:
    """One game's full-frame history and the evidence that it is the G1 history."""

    game_index: int
    game_id: str
    history: History
    final_frame_sha256_expected: str | None
    final_frame_sha256_replayed: str | None
    frame_digest_mismatches: int

    @property
    def replay_identity(self) -> bool:
        return (
            self.final_frame_sha256_expected is not None
            and self.final_frame_sha256_expected == self.final_frame_sha256_replayed
            and self.frame_digest_mismatches == 0
        )

    def record(self) -> dict[str, Any]:
        return {
            "game_index": self.game_index,
            "game_id": self.game_id,
            "history_length": len(self.history),
            "final_frame_sha256_expected": self.final_frame_sha256_expected,
            "final_frame_sha256_replayed": self.final_frame_sha256_replayed,
            "frame_digest_mismatches": self.frame_digest_mismatches,
            "replay_identity": self.replay_identity,
        }


@dataclass(frozen=True)
class HistorySource:
    """The G1 run directory the histories come from, with its digests checked."""

    run_dir: Path
    transitions_path: Path
    transitions_sha256: str
    sha256sums_sha256: str
    results_sha256: str
    environment_seed: int
    run_id: str
    final_digests: dict[str, str]
    steps_taken: dict[str, int]

    def record(self, root: Path = PROJECT_ROOT) -> dict[str, Any]:
        path = self.transitions_path
        rel = path.relative_to(root) if path.is_relative_to(root) else path
        return {
            "transitions_path": str(rel),
            "transitions_sha256": self.transitions_sha256,
            "sha256sums_sha256": self.sha256sums_sha256,
            "results_sha256": self.results_sha256,
            "environment_seed": self.environment_seed,
            "run_id": self.run_id,
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_history_source(transitions_path: Path, expected_sums_sha256: str) -> HistorySource:
    """Check the G1 run's ``SHA256SUMS`` digest, that it lists ``transitions.jsonl`` with the
    file's current digest, and read the per-game final digests from ``results.json``."""
    if not transitions_path.exists():
        raise HistorySourceError(f"history source {transitions_path} does not exist")
    run_dir = transitions_path.parent
    sums_path = run_dir / "SHA256SUMS"
    results_path = run_dir / "results.json"
    for path in (sums_path, results_path):
        if not path.exists():
            raise HistorySourceError(f"history source run lacks {path.name}: {path}")
    sums_digest = _sha256(sums_path)
    if sums_digest != expected_sums_sha256:
        raise HistorySourceError(
            f"{sums_path} sha256 {sums_digest} != configured {expected_sums_sha256}"
        )
    listed: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) == 2:
            listed[parts[1]] = parts[0]
    transitions_digest = _sha256(transitions_path)
    if listed.get(transitions_path.name) != transitions_digest:
        raise HistorySourceError(
            f"{transitions_path.name} sha256 {transitions_digest} is not what {sums_path} lists "
            f"({listed.get(transitions_path.name)})"
        )
    results_digest = _sha256(results_path)
    if listed.get(results_path.name) != results_digest:
        raise HistorySourceError(f"{results_path.name} digest is not what {sums_path} lists")
    doc = json.loads(results_path.read_text(encoding="utf-8"))
    games = doc.get("results", {}).get("games")
    if not isinstance(games, list) or not games:
        raise HistorySourceError(f"{results_path} carries no results.games list")
    final: dict[str, str] = {}
    steps: dict[str, int] = {}
    for game in games:
        final[str(game["game_id"])] = str(game["final_frame_sha256"])
        steps[str(game["game_id"])] = int(game["steps_taken"])
    seed = doc.get("seed")
    if not isinstance(seed, int):
        raise HistorySourceError(f"{results_path} carries no integer seed")
    return HistorySource(
        run_dir=run_dir,
        transitions_path=transitions_path,
        transitions_sha256=transitions_digest,
        sha256sums_sha256=sums_digest,
        results_sha256=results_digest,
        environment_seed=seed,
        run_id=str(doc.get("run_id", run_dir.name)),
        final_digests=final,
        steps_taken=steps,
    )


def read_logged_digests(transitions_path: Path, game_id: str) -> list[str | None]:
    """The per-step ``frame_sha256`` values the G1 log recorded for ``game_id``, in step order."""
    rows: list[tuple[int, str | None]] = []
    with transitions_path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("game_id") == game_id:
                digest = row.get("frame_sha256")
                rows.append((int(row["step_index"]), None if digest is None else str(digest)))
    rows.sort(key=lambda item: item[0])
    return [d for _, d in rows]


def replay_game_history(
    environments_dir: Path,
    game_id: str,
    seed: int,
    actions: Sequence[ai.ActionRecord],
    logged_digests: Sequence[str | None],
) -> tuple[History, str, int]:
    """Reset a fresh offline environment, apply ``actions`` keeping every frame, and compare
    every response digest with the G1 log. Returns the history, the final digest and the
    number of per-step digest mismatches."""
    arcade = ai.open_offline_arcade(environments_dir)
    env = ai.make_environment(arcade, game_id, seed)
    reset = env.reset()
    if reset is None:
        raise HistorySourceError(f"{game_id}: reset() returned None")
    current = ai.summarize_response(reset)
    history = History(Observation.from_summary(current))
    mismatches = 0
    for index, action in enumerate(actions):
        nxt = ai.step_environment(env, action)
        if nxt is None:
            raise HistorySourceError(f"{game_id}: step {index + 1} returned None on replay")
        current = nxt
        history = history.extend(action, Observation.from_summary(current))
        if index < len(logged_digests) and logged_digests[index] != current.digest():
            mismatches += 1
    if len(logged_digests) != len(actions):
        mismatches += abs(len(logged_digests) - len(actions))
    return history, current.digest(), mismatches


def load_game_histories(
    source: HistorySource, environments_dir: Path, stems: Sequence[str] | None
) -> list[GameHistory]:
    """Replay every requested game of the G1 log (all of them when ``stems`` is ``None``)."""
    game_ids = tm.game_ids_in_action_log(source.transitions_path)
    if stems is not None:
        by_stem = {ai.game_stem(g): g for g in game_ids}
        missing = [s for s in stems if s not in by_stem]
        if missing:
            raise HistorySourceError(f"stems not in the history log: {missing}")
        game_ids = [by_stem[s] for s in stems]
    histories: list[GameHistory] = []
    for index, game_id in enumerate(game_ids):
        actions = tm.read_action_log(source.transitions_path, game_id)
        logged = read_logged_digests(source.transitions_path, game_id)
        history, final_digest, mismatches = replay_game_history(
            environments_dir, game_id, source.environment_seed, actions, logged
        )
        histories.append(
            GameHistory(
                game_index=index,
                game_id=game_id,
                history=history,
                final_frame_sha256_expected=source.final_digests.get(game_id),
                final_frame_sha256_replayed=final_digest,
                frame_digest_mismatches=mismatches,
            )
        )
    return histories


# --------------------------------------------------------------------------- trials


def class_plan(seed: int, game_index: int, trials: int) -> list[str]:
    """The mutation class of every wrong-model trial of one game (``CLASS_ASSIGNMENT``)."""
    rng = np.random.default_rng([int(seed), int(game_index)])
    plan: list[str] = []
    while len(plan) < trials:
        plan.extend(mu.MUTATION_CLASSES[int(i)] for i in rng.permutation(len(mu.MUTATION_CLASSES)))
    return plan[:trials]


def trial_rng(seed: int, game_index: int, trial_index: int) -> np.random.Generator:
    return np.random.default_rng([int(seed), int(game_index), int(trial_index)])


def discrimination_site(
    mutated: WorldModel, history: History, spec: mu.MutationSpec
) -> tuple[int | None, str | None]:
    """The first transition where the mutated model's prediction differs from the record on
    a certification field, or ``None`` when the mutation is vacuous for this history.

    Index-targeted classes are checked at their one site; the whole-history classes at every
    transition in order. A prediction that raises counts as discriminating (the backtester
    never certifies a model that raises) and the kind is returned in place of the field.
    """
    if "index" in spec.params:
        sites: Sequence[int] = (int(spec.params["index"]),)
    else:
        sites = range(len(history))
    for index in sites:
        transition = history.transitions[index]
        try:
            predicted = mutated.predict(history.prefix(index), transition.action)
        except Exception as exc:  # noqa: BLE001 - recorded as the discrimination kind
            return index, f"raised:{type(exc).__name__}"
        for name in CERTIFICATION_FIELDS:
            if predicted.field(name) != transition.observation.field(name):
                return index, name
    return None, None


@dataclass
class TrialResult:
    """One backtest submission and, for wrong models, how the mutation was drawn."""

    game_index: int
    game_id: str
    trial_index: int
    kind: str  # "wrong_model" or "control"
    mutation_class: str | None
    mutation_params: dict[str, Any]
    redraws: int
    vacuous: bool
    discrimination_index: int | None
    discrimination_field: str | None
    record: bt.BacktestRecord | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return self.record is not None and not self.record.certified

    def transition_row(self) -> dict[str, Any]:
        rec = self.record
        return {
            "game_index": self.game_index,
            "game_id": self.game_id,
            "trial_index": self.trial_index,
            "kind": self.kind,
            "mutation_class": self.mutation_class,
            "mutation_params": dict(self.mutation_params),
            "redraws": self.redraws,
            "vacuous": self.vacuous,
            "discrimination_index": self.discrimination_index,
            "discrimination_field": self.discrimination_field,
            "backtested": rec is not None,
            "certified": None if rec is None else rec.certified,
            "rejected": None if rec is None else (not rec.certified),
            "history_length": None if rec is None else rec.history_length,
            "history_length_checked": None if rec is None else rec.history_length_checked,
            "mismatches": None if rec is None else rec.mismatches,
            "first_mismatch_index": None if rec is None else rec.first_mismatch_index,
            "failure_kind": None if rec is None else rec.failure_kind,
            "notes": list(self.notes),
        }

    def hypothesis_row(self) -> dict[str, Any] | None:
        if self.record is None:
            return None
        row = self.record.to_dict()
        row.update(
            {
                "game_index": self.game_index,
                "game_id": self.game_id,
                "trial_index": self.trial_index,
                "kind": self.kind,
                "mutation_class": self.mutation_class,
            }
        )
        return row


def draw_discriminating_mutation(
    mutation_class: str,
    rng: np.random.Generator,
    game: GameHistory,
    model_factory: ModelFactory,
    other_game_ids: Sequence[str],
    redraw_max: int,
) -> tuple[mu.MutationSpec, int, int | None, str | None]:
    """Draw ``mutation_class`` parameters until the mutation is discriminating, re-drawing
    at most ``redraw_max`` times. Returns the spec, the re-draw count and the site."""
    has_params = mutation_class not in ("identity_model", "stale_frame")
    redraws = 0
    while True:
        spec = mu.draw_mutation(mutation_class, rng, game.history, other_game_ids)
        other = (
            model_factory(str(spec.params["other_game_id"]))
            if mutation_class == "other_game_simulator"
            else None
        )
        mutated = mu.MutatedModel(model_factory(game.game_id), spec, other)
        index, why = discrimination_site(mutated, game.history, spec)
        if index is not None or not has_params or redraws >= redraw_max:
            return spec, redraws, index, why
        redraws += 1


def run_game_trials(
    game: GameHistory,
    seed: int,
    params: RejectionParams,
    model_factory: ModelFactory,
    other_game_ids: Sequence[str],
    deadline: Deadline,
) -> list[TrialResult]:
    """All wrong-model trials then all control trials of one game."""
    results: list[TrialResult] = []
    plan = class_plan(seed, game.game_index, params.trial_seeds_per_game)
    for trial_index, mutation_class in enumerate(plan):
        deadline.check()
        rng = trial_rng(seed, game.game_index, trial_index)
        spec, redraws, site, why = draw_discriminating_mutation(
            mutation_class, rng, game, model_factory, other_game_ids, params.redraw_max
        )
        trial = TrialResult(
            game_index=game.game_index,
            game_id=game.game_id,
            trial_index=trial_index,
            kind="wrong_model",
            mutation_class=mutation_class,
            mutation_params=json.loads(json.dumps(spec.params)),
            redraws=redraws,
            vacuous=site is None,
            discrimination_index=site,
            discrimination_field=why,
        )
        if trial.vacuous:
            trial.notes.append("non-discriminating after re-draws; excluded from the denominator")
        # Fresh models for the backtest: the backtester sees only the history and the model.
        other = (
            model_factory(str(spec.params["other_game_id"]))
            if mutation_class == "other_game_simulator"
            else None
        )
        mutated = mu.MutatedModel(model_factory(game.game_id), spec, other)
        trial.record = bt.backtest(mutated, game.history, params.limits)
        results.append(trial)
    for control_index in range(params.control_trials_per_game):
        deadline.check()
        trial = TrialResult(
            game_index=game.game_index,
            game_id=game.game_id,
            trial_index=params.trial_seeds_per_game + control_index,
            kind="control",
            mutation_class=None,
            mutation_params={},
            redraws=0,
            vacuous=False,
            discrimination_index=None,
            discrimination_field=None,
        )
        trial.record = bt.backtest(model_factory(game.game_id), game.history, params.limits)
        results.append(trial)
    return results


# --------------------------------------------------------------------------- aggregation


def _fraction(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def summarize_trials(trials: Sequence[TrialResult]) -> dict[str, Any]:
    """The E310 result numbers the pre-registration names, all derived from the trials."""
    wrong = [t for t in trials if t.kind == "wrong_model"]
    controls = [t for t in trials if t.kind == "control"]
    non_vacuous = [t for t in wrong if not t.vacuous]
    rejected = [t for t in non_vacuous if t.rejected]
    per_class: dict[str, dict[str, Any]] = {}
    for name in mu.MUTATION_CLASSES:
        cls_trials = [t for t in wrong if t.mutation_class == name]
        cls_non_vacuous = [t for t in cls_trials if not t.vacuous]
        cls_rejected = [t for t in cls_non_vacuous if t.rejected]
        per_class[name] = {
            "trials": len(cls_trials),
            "vacuous_trials": len(cls_trials) - len(cls_non_vacuous),
            "non_vacuous_trials": len(cls_non_vacuous),
            "rejected_trials": len(cls_rejected),
            "rejection_fraction": _fraction(len(cls_rejected), len(cls_non_vacuous)),
            "redraws_total": sum(t.redraws for t in cls_trials),
            "vacuous_rejected_anyway": sum(1 for t in cls_trials if t.vacuous and t.rejected),
        }
    backtested = [t for t in trials if t.record is not None]
    unequal = [
        t
        for t in backtested
        if t.record is not None and t.record.history_length_checked != t.record.history_length
    ]
    controls_accepted = [t for t in controls if t.record is not None and t.record.certified]
    return {
        "wrong_model_trials": len(wrong),
        "vacuous_trials": len(wrong) - len(non_vacuous),
        "non_vacuous_trials": len(non_vacuous),
        "rejected_trials": len(rejected),
        "rejection_fraction": _fraction(len(rejected), len(non_vacuous)),
        "rejection_denominator": "non_vacuous_trials",
        "mutation_classes": list(mu.MUTATION_CLASSES),
        "mutation_classes_used": sorted({t.mutation_class for t in wrong if t.mutation_class}),
        "per_class": per_class,
        "control_trials": len(controls),
        "control_accepted": len(controls_accepted),
        "correct_model_acceptance_fraction": _fraction(len(controls_accepted), len(controls)),
        "trials_backtested": len(backtested),
        "history_length_checked_equal_length_all": not unequal,
        "history_length_checked_unequal_trials": [
            {"game_id": t.game_id, "trial_index": t.trial_index, "kind": t.kind} for t in unequal
        ],
        "failure_kinds": sorted(
            {t.record.failure_kind for t in backtested if t.record and t.record.failure_kind}
        ),
    }


def metrics_rows(summary: dict[str, Any], games: Sequence[GameHistory]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {"metric": "games", "value": len(games)},
        {"metric": "replay_identity_games", "value": sum(1 for g in games if g.replay_identity)},
        {"metric": "history_length_total", "value": sum(len(g.history) for g in games)},
        {"metric": "history_length_min", "value": min((len(g.history) for g in games), default=0)},
        {"metric": "wrong_model_trials", "value": summary["wrong_model_trials"]},
        {"metric": "vacuous_trials", "value": summary["vacuous_trials"]},
        {"metric": "non_vacuous_trials", "value": summary["non_vacuous_trials"]},
        {"metric": "rejected_trials", "value": summary["rejected_trials"]},
        {"metric": "rejection_fraction", "value": summary["rejection_fraction"]},
        {"metric": "control_trials", "value": summary["control_trials"]},
        {"metric": "control_accepted", "value": summary["control_accepted"]},
        {
            "metric": "correct_model_acceptance_fraction",
            "value": summary["correct_model_acceptance_fraction"],
        },
        {
            "metric": "history_length_checked_equal_length_all",
            "value": int(summary["history_length_checked_equal_length_all"]),
        },
    ]
    for name, cls in summary["per_class"].items():
        rows.append({"metric": f"{name}_trials", "value": cls["trials"]})
        rows.append({"metric": f"{name}_vacuous_trials", "value": cls["vacuous_trials"]})
        rows.append({"metric": f"{name}_rejected_trials", "value": cls["rejected_trials"]})
    return rows


def environment_rows(
    games: Sequence[GameHistory], trials: Sequence[TrialResult]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for game in games:
        mine = [t for t in trials if t.game_index == game.game_index]
        wrong = [t for t in mine if t.kind == "wrong_model"]
        controls = [t for t in mine if t.kind == "control"]
        rows.append(
            {
                "environment": game.game_id,
                "history_length": len(game.history),
                "replay_identity": int(game.replay_identity),
                "frame_digest_mismatches": game.frame_digest_mismatches,
                "wrong_model_trials": len(wrong),
                "vacuous_trials": sum(1 for t in wrong if t.vacuous),
                "rejected_trials": sum(1 for t in wrong if not t.vacuous and t.rejected),
                "control_trials": len(controls),
                "control_accepted": sum(
                    1 for t in controls if t.record is not None and t.record.certified
                ),
            }
        )
    return rows


def module_digests() -> dict[str, str]:
    return {
        "backtest_module_sha256": bt.backtest_module_sha256(),
        "interface_sha256": interface_sha256(),
        "mutations_sha256": _sha256(Path(mu.__file__)),
        "true_model_sha256": _sha256(Path(tm.__file__)),
        "generator_sha256": _sha256(Path(__file__)),
    }


def run_experiment_core(
    games: Sequence[GameHistory],
    seed: int,
    params: RejectionParams,
    model_factory: ModelFactory,
    writer: RunArtifactWriter | None,
    deadline: Deadline,
) -> tuple[list[TrialResult], dict[str, Any]]:
    """Run every trial over ``games`` and build the results mapping. Toolkit-free."""
    all_ids = [g.game_id for g in games]
    trials: list[TrialResult] = []
    for game in games:
        deadline.check()
        others = [g for g in all_ids if g != game.game_id]
        game_trials = run_game_trials(game, seed, params, model_factory, others, deadline)
        trials.extend(game_trials)
        if writer is not None:
            for trial in game_trials:
                writer.append_transition(trial.transition_row())
                hypothesis = trial.hypothesis_row()
                if hypothesis is not None:
                    writer.append_hypothesis(hypothesis)
            wrong = [t for t in game_trials if t.kind == "wrong_model"]
            writer.log(
                f"game {game.game_index} {game.game_id}: history={len(game.history)} "
                f"replay_identity={game.replay_identity} wrong={len(wrong)} "
                f"vacuous={sum(1 for t in wrong if t.vacuous)} "
                f"rejected={sum(1 for t in wrong if not t.vacuous and t.rejected)} "
                f"controls_accepted={sum(1 for t in game_trials if t.kind == 'control' and t.record and t.record.certified)}"
                f"/{sum(1 for t in game_trials if t.kind == 'control')}"
            )
    summary = summarize_trials(trials)
    summary.update(
        {
            "seed": int(seed),
            "trial_seeds_per_game": params.trial_seeds_per_game,
            "control_trials_per_game": params.control_trials_per_game,
            "redraw_max": params.redraw_max,
            "class_assignment": CLASS_ASSIGNMENT,
            "trial_seed_derivation": "default_rng([seed, game_index]) for the class plan; "
            "default_rng([seed, game_index, trial_index]) for the mutation parameters",
            "backtester": bt.BACKTESTER_NAME,
            "backtest_limits": {
                "backtest_seconds_max": params.limits.backtest_seconds_max,
                "predict_seconds_max": params.limits.predict_seconds_max,
                "address_space_bytes_max": params.limits.address_space_bytes_max,
            },
            "certification_fields": list(CERTIFICATION_FIELDS),
            "games": [g.record() for g in games],
            "replay_identity_games": sum(1 for g in games if g.replay_identity),
            "replay_divergent_games": sum(1 for g in games if not g.replay_identity),
        }
    )
    summary.update(module_digests())
    return trials, summary


# --------------------------------------------------------------------------- runner


class BacktestRejectionRunner:
    name = RUNNER_NAME
    environment_generator_version = ENVIRONMENT_GENERATOR_VERSION

    def preflight(self, config: ExperimentConfig) -> None:
        """Refuse to run (no run directory) when the inputs cannot be what the config claims."""
        try:
            params = RejectionParams.from_config(config)
            if not params.environments_dir.is_dir():
                raise HistorySourceError(f"{params.environments_dir} is not a directory")
            load_history_source(params.history_source, params.history_source_sha256sums_sha256)
        except (RunnerConfigError, HistorySourceError) as exc:
            raise RunPreflightError(str(exc)) from exc

    def run(
        self, config: ExperimentConfig, writer: RunArtifactWriter, deadline: Deadline
    ) -> RunOutcome:
        params = RejectionParams.from_config(config)
        source = load_history_source(params.history_source, params.history_source_sha256sums_sha256)
        writer.log(
            f"{RUNNER_NAME} seed={config.seed} history_run={source.run_id} "
            f"transitions_sha256={source.transitions_sha256} environment_seed="
            f"{source.environment_seed} trials_per_game={params.trial_seeds_per_game} "
            f"controls_per_game={params.control_trials_per_game} redraw_max={params.redraw_max} "
            f"operation_mode={OPERATION_MODE}"
        )
        games = load_game_histories(
            source, params.environments_dir, list(params.games) if params.games else None
        )
        divergent = [g.game_id for g in games if not g.replay_identity]
        for game in games:
            writer.log(
                f"replayed {game.game_id}: length={len(game.history)} "
                f"final={game.final_frame_sha256_replayed} identity={game.replay_identity}"
            )
        if divergent:
            # A history that is not the G1 history is not the pre-registered input; stop
            # rather than grade against it. The run is sealed as failed by the entry point.
            raise HistorySourceError(f"replay diverged from the G1 log for {divergent}")
        env_dir, env_seed = params.environments_dir, source.environment_seed

        def factory(game_id: str) -> WorldModel:
            return tm.TrueModel(env_dir, game_id, env_seed)

        trials, summary = run_experiment_core(games, config.seed, params, factory, writer, deadline)
        results: dict[str, Any] = {
            "environment_generator_version": ENVIRONMENT_GENERATOR_VERSION,
            "operation_mode": OPERATION_MODE,
            "network_guard": NetworkGuard.__name__,
            "history_source": source.record(),
            **summary,
        }
        writer.log(
            f"finished wrong_model_trials={summary['wrong_model_trials']} "
            f"vacuous={summary['vacuous_trials']} rejected={summary['rejected_trials']} "
            f"rejection_fraction={summary['rejection_fraction']} "
            f"controls={summary['control_accepted']}/{summary['control_trials']}"
        )
        return RunOutcome(
            results=results,
            metrics=metrics_rows(summary, games),
            environment_results=environment_rows(games, trials),
            environment_columns=ENVIRONMENT_COLUMNS,
            model_calls=0,
        )


register_runner(RUNNER_NAME, BacktestRejectionRunner)

__all__ = [
    "CLASS_ASSIGNMENT",
    "ENVIRONMENT_COLUMNS",
    "RUNNER_NAME",
    "BacktestRejectionRunner",
    "GameHistory",
    "HistorySource",
    "HistorySourceError",
    "RejectionParams",
    "RunnerConfigError",
    "TrialResult",
    "class_plan",
    "discrimination_site",
    "draw_discriminating_mutation",
    "load_game_histories",
    "load_history_source",
    "replay_game_history",
    "run_experiment_core",
    "run_game_trials",
    "summarize_trials",
    "trial_rng",
]
