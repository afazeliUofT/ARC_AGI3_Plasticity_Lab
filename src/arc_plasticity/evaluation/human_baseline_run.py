"""E020: derive per-level human baselines from the released replays (G2's experiment).

Pre-registered in ``preregistration/G2.yaml`` ``experiment`` and ``human_baselines``. The
runner reads local files only (the raw replay directory, its committed provenance manifest,
the environment cache manifest with the 25 ``metadata.json`` files, and the three graded G1
runs), applies the hash-locked derivation rules of ``arc_plasticity.evaluation.human_replays``
and writes the artifacts the G2 verifier consumes. It instantiates no environment, calls no
model and consumes no randomness; the seed is recorded because the manifest contract requires
one.

Preflight (``HumanBaselineRunner.preflight``, called by ``scripts/run_experiment.py`` before
any run directory exists): the dataset manifest must exist and describe the raw directory with
no drift in either direction, the cache manifest and the G1 runs must be present. A refused
run therefore never leaves anything under ``artifacts/``; ``artifacts/E020_human_baselines/``
cannot appear before ``experiments/human_replays_manifest.json`` is committed.

Replay-to-game matching: a replay names a game by ``game_id``; the official record is the
cached ``metadata.json``. They are matched on the four-character stem (``game_id`` before the
first ``-``), because the public environment files carry version hashes that differ between
releases (G2 pre-registration ``known_conflicts_at_authoring``), and every distinct replay
``game_id`` seen per stem is recorded in ``input_manifest.json`` so the referee can see which
versions the replays name. A replay on a stem that is not cached is counted as unmatched and
takes no part in the derivation.

What it writes, in the layout ``scripts/verify_run.py`` consumes:

* ``results.json["results"]``: every field of the pre-registration's ``results_json_contract``
  plus ``operation`` ``"offline_local_files"`` and ``network_guard``; no timing.
* ``metrics.csv``: the totals, then per (game, level) one ``official_baseline_actions[...]``
  and one ``derived_baseline_actions[...]`` row (the contract fixes two columns, so the two
  values of a level are two rows; the joint per-level view is ``environment_results.csv``).
* ``environment_results.csv``: one row per (game, level) with official, derived, participant
  count, exact agreement and relative difference.
* ``human_baselines.json``: the derived table (``human_baselines.derived_table_artifact``).
* ``replay_ingestion_log.jsonl``: one line per raw file (path, sha256, bytes, units, field
  mapping, session order source, the P1 counts, the P2 counts and action total from the
  toolkit scorecard, the per-level P1/P2 agreement, failure).
* ``input_manifest.json``: the SHA-256 of every file read, the dataset manifest's own
  provenance fields, the replay game ids seen per stem, and the P1/P2 agreement totals.
* ``g1_termination_vs_budget.json``: the non-thresholded diagnostic of
  ``human_baselines.diagnostics_not_thresholded``.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from arc_plasticity.core.artifacts import RunArtifactWriter
from arc_plasticity.core.config import ExperimentConfig
from arc_plasticity.core.guards import Deadline, NetworkGuard
from arc_plasticity.core.runner import RunOutcome, RunPreflightError, register_runner
from arc_plasticity.evaluation import human_replays as hr

RUNNER_NAME = "human_baseline_derivation"
ENVIRONMENT_GENERATOR_VERSION = "human-replays-derivation-1.0.0"
OPERATION = "offline_local_files"
GAME_ID_MATCH_RULE = "stem"

HUMAN_BASELINES_FILE = "human_baselines.json"
INGESTION_LOG_FILE = "replay_ingestion_log.jsonl"
INPUT_MANIFEST_FILE = "input_manifest.json"
G1_DIAGNOSTIC_FILE = "g1_termination_vs_budget.json"
REQUIRED_EXTRAS: tuple[str, ...] = (
    HUMAN_BASELINES_FILE,
    INGESTION_LOG_FILE,
    INPUT_MANIFEST_FILE,
    G1_DIAGNOSTIC_FILE,
)

SCHEMA_VERSION = 1
PROJECT_ROOT = Path(__file__).resolve().parents[3]

ENVIRONMENT_COLUMNS: tuple[str, ...] = (
    "environment",
    "level",
    "official_baseline_actions",
    "derived_baseline_actions",
    "n_participants_with_completion",
    "exact_agreement",
    "relative_difference",
)

MEDIAN_ABS_RELATIVE_DIFFERENCE_DEFINITION = (
    "statistics.median of |(derived - official) / official| over derived levels; null when "
    "no level is derived"
)


class RunnerConfigError(ValueError):
    """``runner_params`` are missing or malformed for this runner."""


class OfficialBaselineError(RuntimeError):
    """The cache manifest or a cached ``metadata.json`` does not carry usable baselines."""


def game_stem(game_id: str) -> str:
    """The four-character public stem: the part of ``game_id`` before the first ``-``."""
    return game_id.split("-", 1)[0]


# --------------------------------------------------------------------------------------------
# Parameters and inputs
# --------------------------------------------------------------------------------------------


def _path_param(params: Mapping[str, Any], key: str, root: Path) -> Path:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise RunnerConfigError(f"runner_params.{key} must be a non-empty string")
    path = Path(value)
    return path if path.is_absolute() else root / path


@dataclass(frozen=True)
class DerivationParams:
    raw_replays_dir: Path
    dataset_manifest: Path
    environments_dir: Path
    cache_manifest: Path
    g1_runs_dir: Path
    g1_run_ids: tuple[str, ...]
    action_budget_multiplier: int
    extra_artifacts: tuple[str, ...]

    @classmethod
    def from_config(cls, config: ExperimentConfig, root: Path = PROJECT_ROOT) -> DerivationParams:
        params = config.runner_params
        run_ids_raw = params.get("g1_run_ids")
        if (
            not isinstance(run_ids_raw, list)
            or not run_ids_raw
            or not all(isinstance(r, str) and r for r in run_ids_raw)
        ):
            raise RunnerConfigError("runner_params.g1_run_ids must be a non-empty list of run ids")
        multiplier = params.get("action_budget_multiplier")
        if isinstance(multiplier, bool) or not isinstance(multiplier, int) or multiplier < 1:
            raise RunnerConfigError("runner_params.action_budget_multiplier must be a positive int")
        extras_raw = params.get("extra_artifacts", [])
        if not isinstance(extras_raw, list) or not all(isinstance(e, str) for e in extras_raw):
            raise RunnerConfigError("runner_params.extra_artifacts must be a list of file names")
        missing = [name for name in REQUIRED_EXTRAS if name not in extras_raw]
        if missing:
            raise RunnerConfigError(f"runner_params.extra_artifacts must list {missing}")
        return cls(
            raw_replays_dir=_path_param(params, "raw_replays_dir", root),
            dataset_manifest=_path_param(params, "dataset_manifest", root),
            environments_dir=_path_param(params, "environments_dir", root),
            cache_manifest=_path_param(params, "cache_manifest", root),
            g1_runs_dir=_path_param(params, "g1_runs_dir", root),
            g1_run_ids=tuple(run_ids_raw),
            action_budget_multiplier=multiplier,
            extra_artifacts=tuple(extras_raw),
        )


@dataclass(frozen=True)
class OfficialGame:
    """One cached public game: its official per-level baselines and where they came from."""

    stem: str
    game_id: str
    metadata_path: Path
    metadata_sha256: str
    baseline_actions: tuple[int, ...]

    @property
    def levels(self) -> int:
        return len(self.baseline_actions)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_official_games(cache_manifest: Path, environments_dir: Path) -> list[OfficialGame]:
    """Every game of the cache manifest with its ``metadata.json`` baselines, in manifest order.

    ``local_dir`` entries are relative to the manifest's own ``environments_dir``; they are
    re-rooted onto ``environments_dir`` so the same manifest serves the repository and a
    synthetic root.
    """
    if not cache_manifest.is_file():
        raise OfficialBaselineError(f"{cache_manifest} does not exist")
    manifest = _load_json(cache_manifest)
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("games"), list):
        raise OfficialBaselineError(f"{cache_manifest} has no 'games' list")
    manifest_env = str(manifest.get("environments_dir") or "")
    games: list[OfficialGame] = []
    seen: set[str] = set()
    for i, entry in enumerate(manifest["games"]):
        if not isinstance(entry, Mapping):
            raise OfficialBaselineError(f"cache manifest game entry {i} is not a mapping")
        for key in ("stem", "game_id", "local_dir", "baseline_actions_count"):
            if key not in entry:
                raise OfficialBaselineError(f"cache manifest game entry {i} lacks {key}")
        stem, game_id = str(entry["stem"]), str(entry["game_id"])
        if stem in seen:
            raise OfficialBaselineError(f"cache manifest lists stem {stem} twice")
        seen.add(stem)
        local = Path(str(entry["local_dir"]))
        try:
            rel = local.relative_to(manifest_env) if manifest_env else local
        except ValueError as exc:
            raise OfficialBaselineError(
                f"{stem}: local_dir {local} is not under environments_dir {manifest_env!r}"
            ) from exc
        meta_path = environments_dir / rel / "metadata.json"
        if not meta_path.is_file():
            raise OfficialBaselineError(f"{stem}: {meta_path} does not exist")
        meta = _load_json(meta_path)
        if not isinstance(meta, Mapping) or meta.get("game_id") != game_id:
            raise OfficialBaselineError(
                f"{stem}: metadata game_id {getattr(meta, 'get', lambda _k: None)('game_id')!r} "
                f"!= manifest {game_id!r}"
            )
        raw_baselines = meta.get("baseline_actions")
        if not isinstance(raw_baselines, list) or not raw_baselines:
            raise OfficialBaselineError(
                f"{stem}: metadata baseline_actions is not a non-empty list"
            )
        baselines: list[int] = []
        for level, value in enumerate(raw_baselines, start=1):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise OfficialBaselineError(
                    f"{stem}: baseline_actions[{level}] = {value!r} is not a positive int"
                )
            baselines.append(value)
        if len(baselines) != int(entry["baseline_actions_count"]):
            raise OfficialBaselineError(
                f"{stem}: metadata lists {len(baselines)} baselines, manifest says "
                f"{entry['baseline_actions_count']}"
            )
        games.append(
            OfficialGame(stem, game_id, meta_path, hr.sha256_of(meta_path), tuple(baselines))
        )
    if not games:
        raise OfficialBaselineError(f"{cache_manifest} lists no games")
    return games


def load_dataset_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RunPreflightError(
            f"dataset manifest {path} does not exist; build it with "
            "scripts/build_human_replays_manifest.py and commit it before running E020"
        )
    try:
        manifest = _load_json(path)
    except ValueError as exc:
        raise RunPreflightError(f"dataset manifest {path} is not valid JSON: {exc}") from exc
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("files"), Mapping):
        raise RunPreflightError(f"dataset manifest {path} has no 'files' mapping")
    return dict(manifest)


def check_inputs(params: DerivationParams) -> dict[str, Any]:
    """Every input the run needs, or ``RunPreflightError`` naming the first thing missing."""
    manifest = load_dataset_manifest(params.dataset_manifest)
    if not params.raw_replays_dir.is_dir():
        raise RunPreflightError(f"raw replay directory {params.raw_replays_dir} does not exist")
    drift = hr.manifest_drift(manifest["files"], params.raw_replays_dir)
    if drift:
        shown = "; ".join(drift[:5]) + (" ..." if len(drift) > 5 else "")
        raise RunPreflightError(
            f"{len(drift)} file(s) drift between {params.dataset_manifest} and "
            f"{params.raw_replays_dir}: {shown}"
        )
    if not params.cache_manifest.is_file():
        raise RunPreflightError(f"cache manifest {params.cache_manifest} does not exist")
    if not params.environments_dir.is_dir():
        raise RunPreflightError(f"environments dir {params.environments_dir} does not exist")
    for run_id in params.g1_run_ids:
        if not (params.g1_runs_dir / run_id / "results.json").is_file():
            raise RunPreflightError(
                f"G1 run {run_id} has no results.json under {params.g1_runs_dir}"
            )
    return manifest


# --------------------------------------------------------------------------------------------
# Derivation table
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LevelRow:
    game_id: str
    stem: str
    level: int
    official: int
    derived: int | None
    per_participant_best_counts_sorted: tuple[int, ...]

    @property
    def exact_agreement(self) -> bool | None:
        return None if self.derived is None else self.derived == self.official

    @property
    def relative_difference(self) -> Fraction | None:
        if self.derived is None:
            return None
        return hr.relative_difference(self.derived, self.official)

    def record(self) -> dict[str, Any]:
        rel = self.relative_difference
        return {
            "level": self.level,
            "official_baseline_actions": self.official,
            "derived_baseline_actions": self.derived,
            "n_participants_with_completion": len(self.per_participant_best_counts_sorted),
            "per_participant_best_counts_sorted": list(self.per_participant_best_counts_sorted),
            "exact_agreement": self.exact_agreement,
            "relative_difference": None if rel is None else float(rel),
        }

    def environment_row(self) -> dict[str, Any]:
        rel = self.relative_difference
        agree = self.exact_agreement
        return {
            "environment": self.game_id,
            "level": self.level,
            "official_baseline_actions": self.official,
            "derived_baseline_actions": self.derived,
            "n_participants_with_completion": len(self.per_participant_best_counts_sorted),
            "exact_agreement": None if agree is None else int(agree),
            "relative_difference": None if rel is None else float(rel),
        }


def match_sessions(
    sessions: Sequence[hr.ReplaySession], games: Sequence[OfficialGame]
) -> tuple[list[hr.ReplaySession], dict[str, list[str]], dict[str, int]]:
    """Re-key every session onto the official ``game_id`` of its stem.

    Returns the matched sessions, the replay game ids seen per stem (matched stems only, for
    the input manifest), and the count of sessions per unmatched replay game id.
    """
    by_stem = {g.stem: g for g in games}
    matched: list[hr.ReplaySession] = []
    seen: dict[str, set[str]] = {}
    unmatched: dict[str, int] = {}
    for session in sessions:
        game = by_stem.get(game_stem(session.game_id))
        if game is None:
            unmatched[session.game_id] = unmatched.get(session.game_id, 0) + 1
            continue
        seen.setdefault(game.stem, set()).add(session.game_id)
        matched.append(
            hr.ReplaySession(
                game_id=game.game_id,
                participant=session.participant,
                session_index=session.session_index,
                completion_counts=session.completion_counts,
                source_file=session.source_file,
                actions_total=session.actions_total,
                session_id=session.session_id,
                dataset_completion_counts=session.dataset_completion_counts,
                dataset_actions_total=session.dataset_actions_total,
            )
        )
    return matched, {s: sorted(v) for s, v in sorted(seen.items())}, dict(sorted(unmatched.items()))


def derive_table(
    sessions: Sequence[hr.ReplaySession], games: Sequence[OfficialGame]
) -> list[LevelRow]:
    """One ``LevelRow`` per official (game, level), in manifest order then level order."""
    levels_per_game = {g.game_id: g.levels for g in games}
    derived = hr.derive_level_baselines(sessions, levels_per_game)
    rows: list[LevelRow] = []
    for game in games:
        for level, official in enumerate(game.baseline_actions, start=1):
            record = derived[(game.game_id, level)]
            rows.append(
                LevelRow(
                    game.game_id,
                    game.stem,
                    level,
                    official,
                    record.derived,
                    record.per_participant_best_counts_sorted,
                )
            )
    return rows


def table_totals(rows: Sequence[LevelRow]) -> dict[str, Any]:
    derived_rows = [r for r in rows if r.derived is not None]
    total = len(rows)
    agreements = sum(1 for r in derived_rows if r.exact_agreement)
    abs_rel = [abs(float(r.relative_difference or 0)) for r in derived_rows]
    return {
        "public_levels_total": total,
        "derived_levels": len(derived_rows),
        "human_baseline_level_coverage": (len(derived_rows) / total) if total else 0.0,
        "exact_agreement_fraction": (agreements / len(derived_rows)) if derived_rows else None,
        "median_abs_relative_difference": statistics.median(abs_rel) if abs_rel else None,
    }


def human_baselines_document(
    rows: Sequence[LevelRow],
    games: Sequence[OfficialGame],
    *,
    dataset_manifest_sha256: str,
    replay_units_ingested: int,
    replay_parse_failures: int,
) -> dict[str, Any]:
    totals = table_totals(rows)
    by_game: dict[str, list[dict[str, Any]]] = {g.game_id: [] for g in games}
    for row in rows:
        by_game[row.game_id].append(row.record())
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "public_games_total": len(games),
        "public_levels_total": totals["public_levels_total"],
        "game_id_match_rule": GAME_ID_MATCH_RULE,
        "aggregation_rule": (
            "per (game, level): upper median v_(floor(N/2)+1) of the sorted per-participant "
            "best first-session attributed action counts; N = 0 -> null"
        ),
        "median_abs_relative_difference_definition": MEDIAN_ABS_RELATIVE_DIFFERENCE_DEFINITION,
        "games": [
            {"game_id": g.game_id, "stem": g.stem, "levels": by_game[g.game_id]} for g in games
        ],
        "totals": {
            "derived_levels": totals["derived_levels"],
            "human_baseline_level_coverage": totals["human_baseline_level_coverage"],
            "exact_agreement_fraction": totals["exact_agreement_fraction"],
            "median_abs_relative_difference": totals["median_abs_relative_difference"],
            "replay_units_ingested": replay_units_ingested,
            "replay_parse_failures": replay_parse_failures,
        },
    }


def _counts_json(counts: Mapping[int, tuple[int, ...]] | None) -> dict[str, list[int]] | None:
    """A level-keyed count mapping as JSON (string keys, level order); ``None`` stays ``None``."""
    if counts is None:
        return None
    return {str(level): list(counts[level]) for level in sorted(counts)}


def ingestion_log_records(ingested: hr.IngestionResult) -> list[dict[str, Any]]:
    """One ``replay_ingestion_log.jsonl`` line per raw file.

    Path P1 (the step log) is what the derivation consumes; path P2 (the toolkit scorecard's
    ``actions_by_level``) is carried next to it with the per-level agreement, as the G2
    pre-registration's ``ingestion_paths`` requires. ``dataset_agreement`` is ``None`` when
    the file supplied no P2, ``{}`` when neither path recorded a completion, otherwise one
    boolean per level seen in either path; ``dataset_agreement_all`` is ``all()`` of those
    values (``True`` for ``{}``) or ``None``. Nothing here feeds a derived number.
    """
    records: list[dict[str, Any]] = []
    for parsed in ingested.files:
        mapping = dict(parsed.field_mapping)
        order = mapping.pop("session_order_source", None)
        session = parsed.sessions[0] if parsed.sessions else None
        agreement = None if session is None else session.dataset_agreement
        records.append(
            {
                "path": parsed.source_file,
                "sha256": parsed.sha256,
                "bytes": parsed.bytes,
                "replay_units": len(parsed.sessions),
                "field_mapping": mapping,
                "session_order_source": order,
                "game_id": None if session is None else session.game_id,
                "participant_present": None if session is None else session.participant is not None,
                "session_index": None if session is None else session.session_index,
                "actions_total": None if session is None else session.actions_total,
                "levels_completed": None if session is None else len(session.completion_counts),
                "completion_counts": None
                if session is None
                else _counts_json(session.completion_counts),
                "dataset_completion_counts": (
                    None if session is None else _counts_json(session.dataset_completion_counts)
                ),
                "dataset_actions_total": None if session is None else session.dataset_actions_total,
                "dataset_agreement": (
                    None
                    if agreement is None
                    else {str(level): agree for level, agree in agreement.items()}
                ),
                "dataset_agreement_all": None if agreement is None else all(agreement.values()),
                "failure": None if parsed.failure is None else parsed.failure.reason,
            }
        )
    return records


def dataset_agreement_summary(ingested: hr.IngestionResult) -> dict[str, Any]:
    """The P1/P2 agreement totals over every parsed file, for ``input_manifest.json``.

    Counted so the referee can see the agreement without re-reading the raw directory:
    ``files_all_levels_agree`` (P2 present, every level agrees, including files where neither
    path recorded a completion, counted again under ``files_no_completion_either_path``),
    ``files_with_disagreement`` (at least one level differs), ``files_p2_unavailable`` (no
    scorecard pairs), ``files_failed`` (parse failures, no session) and the level totals
    ``levels_agree`` / ``levels_disagree`` over the files with P2. Observed only; the G2
    pre-registration thresholds none of these (``official_agreement_report``).
    """
    files_agree = files_disagree = files_unavailable = files_failed = files_empty = 0
    levels_agree = levels_disagree = 0
    disagreeing_files: list[str] = []
    for parsed in ingested.files:
        if not parsed.sessions:
            files_failed += 1
            continue
        agreement = parsed.sessions[0].dataset_agreement
        if agreement is None:
            files_unavailable += 1
            continue
        agree_here = sum(1 for v in agreement.values() if v)
        levels_agree += agree_here
        levels_disagree += len(agreement) - agree_here
        if all(agreement.values()):
            files_agree += 1
            if not agreement:
                files_empty += 1
        else:
            files_disagree += 1
            disagreeing_files.append(parsed.source_file)
    return {
        "definition": (
            "per file, path P1 (step log) versus path P2 (scorecard actions_by_level) per level; "
            "observed only, not thresholded"
        ),
        "files_total": len(ingested.files),
        "files_all_levels_agree": files_agree,
        "files_no_completion_either_path": files_empty,
        "files_with_disagreement": files_disagree,
        "files_p2_unavailable": files_unavailable,
        "files_failed": files_failed,
        "levels_agree": levels_agree,
        "levels_disagree": levels_disagree,
        "disagreeing_files": sorted(disagreeing_files),
    }


def session_order_summary(ingested: hr.IngestionResult) -> str:
    sources = {
        str(f.field_mapping.get("session_order_source"))
        for f in ingested.files
        if f.failure is None and f.field_mapping.get("session_order_source") is not None
    }
    if not sources:
        return "none"
    return sources.pop() if len(sources) == 1 else "mixed"


def g1_diagnostic(
    params: DerivationParams, games: Sequence[OfficialGame]
) -> tuple[dict[str, Any], dict[str, str]]:
    """``g1_termination_vs_budget.json`` and the digests of the G1 results files it read."""
    runs: list[dict[str, Any]] = []
    digests: dict[str, str] = {}
    per_game: dict[str, list[dict[str, Any]]] = {g.stem: [] for g in games}
    for run_id in params.g1_run_ids:
        path = params.g1_runs_dir / run_id / "results.json"
        digests[run_id] = hr.sha256_of(path)
        doc = _load_json(path)
        inner = doc.get("results", {}) if isinstance(doc, Mapping) else {}
        runs.append(
            {
                "run_id": run_id,
                "results_sha256": digests[run_id],
                "seed": doc.get("seed") if isinstance(doc, Mapping) else None,
                "completion_status": doc.get("completion_status")
                if isinstance(doc, Mapping)
                else None,
                "action_budget_per_game": inner.get("action_budget_per_game"),
            }
        )
        for rec in inner.get("games", []) or []:
            if not isinstance(rec, Mapping):
                continue
            stem = game_stem(str(rec.get("game_id", "")))
            if stem in per_game:
                per_game[stem].append(
                    {
                        "run_id": run_id,
                        "seed": rec.get("seed"),
                        "steps_taken": rec.get("steps_taken"),
                        "final_state": rec.get("final_state"),
                        "levels_completed": rec.get("levels_completed"),
                        "stop_reason": rec.get("stop_reason"),
                    }
                )
    m = params.action_budget_multiplier
    game_rows: list[dict[str, Any]] = []
    for g in games:
        budget_1 = m * g.baseline_actions[0]
        budget_all = m * sum(g.baseline_actions)
        entries = []
        for e in per_game[g.stem]:
            steps = e["steps_taken"]
            within_1 = within_all = None
            if isinstance(steps, int) and not isinstance(steps, bool):
                within_1, within_all = steps <= budget_1, steps <= budget_all
            entries.append(
                {**e, "within_level_1_budget": within_1, "within_all_levels_budget": within_all}
            )
        game_rows.append(
            {
                "stem": g.stem,
                "game_id": g.game_id,
                "levels": g.levels,
                "baseline_actions": list(g.baseline_actions),
                "budget_level_1": budget_1,
                "budget_all_levels": budget_all,
                "g1_runs": entries,
            }
        )
    doc = {
        "schema_version": SCHEMA_VERSION,
        "action_budget_multiplier": m,
        "definition": (
            "per game: steps_taken and final_state of each graded G1 run next to "
            "multiplier x baseline_actions[1] and multiplier x sum(baseline_actions); "
            "observed only, not thresholded (G2 human_baselines.diagnostics_not_thresholded)"
        ),
        "runs": runs,
        "games": game_rows,
    }
    return doc, digests


# --------------------------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------------------------


def _rel(path: Path, root: Path) -> str:
    resolved = path.resolve()
    base = root.resolve()
    return resolved.relative_to(base).as_posix() if resolved.is_relative_to(base) else str(resolved)


class HumanBaselineRunner:
    name = RUNNER_NAME
    environment_generator_version = ENVIRONMENT_GENERATOR_VERSION

    def __init__(self, root: Path = PROJECT_ROOT) -> None:
        self._root = root

    def preflight(self, config: ExperimentConfig) -> None:
        """Refuse, before any run directory exists, if an input is missing or the raw dir drifts."""
        try:
            params = DerivationParams.from_config(config, self._root)
        except RunnerConfigError as exc:
            raise RunPreflightError(str(exc)) from exc
        check_inputs(params)

    def run(
        self, config: ExperimentConfig, writer: RunArtifactWriter, deadline: Deadline
    ) -> RunOutcome:
        root = self._root
        params = DerivationParams.from_config(config, root)
        dataset_manifest = check_inputs(params)
        dataset_manifest_sha256 = hr.sha256_of(params.dataset_manifest)
        writer.log(
            f"{RUNNER_NAME} seed={config.seed} (recorded only) operation={OPERATION} "
            f"raw_replays_dir={_rel(params.raw_replays_dir, root)} "
            f"dataset_manifest={_rel(params.dataset_manifest, root)} "
            f"sha256={dataset_manifest_sha256}"
        )

        games = load_official_games(params.cache_manifest, params.environments_dir)
        levels_total = sum(g.levels for g in games)
        writer.log(f"official games={len(games)} levels={levels_total}")
        deadline.check()

        ingested = hr.ingest_directory(params.raw_replays_dir)
        parse_failures = len(ingested.parse_failures)
        writer.log(
            f"ingested files={len(ingested.files)} replay_units={ingested.replay_units_ingested} "
            f"parse_failures={parse_failures} participant_ids_available="
            f"{ingested.participant_ids_available}"
        )
        for failure in ingested.parse_failures:
            writer.log_error(f"parse failure {failure.source_file}: {failure.reason}")
        deadline.check()

        matched, ids_by_stem, unmatched = match_sessions(ingested.sessions, games)
        for game_id, count in unmatched.items():
            writer.log_error(f"{count} replay unit(s) on {game_id!r} match no cached game")
        rows = derive_table(matched, games)
        totals = table_totals(rows)
        deadline.check()
        writer.log(
            f"derived_levels={totals['derived_levels']}/{totals['public_levels_total']} "
            f"coverage={totals['human_baseline_level_coverage']:.4f} "
            f"exact_agreement_fraction={totals['exact_agreement_fraction']} "
            f"median_abs_relative_difference={totals['median_abs_relative_difference']}"
        )

        writer.write_extra_json(
            HUMAN_BASELINES_FILE,
            human_baselines_document(
                rows,
                games,
                dataset_manifest_sha256=dataset_manifest_sha256,
                replay_units_ingested=ingested.replay_units_ingested,
                replay_parse_failures=parse_failures,
            ),
        )
        writer.write_extra_jsonl(INGESTION_LOG_FILE, ingestion_log_records(ingested))
        agreement_summary = dataset_agreement_summary(ingested)
        writer.log(
            "P1/P2 agreement: files_all_levels_agree="
            f"{agreement_summary['files_all_levels_agree']} files_with_disagreement="
            f"{agreement_summary['files_with_disagreement']} files_p2_unavailable="
            f"{agreement_summary['files_p2_unavailable']} levels_agree="
            f"{agreement_summary['levels_agree']} levels_disagree="
            f"{agreement_summary['levels_disagree']}"
        )
        diagnostic, g1_digests = g1_diagnostic(params, games)
        writer.write_extra_json(G1_DIAGNOSTIC_FILE, diagnostic)
        writer.write_extra_json(
            INPUT_MANIFEST_FILE,
            {
                "schema_version": SCHEMA_VERSION,
                "dataset_manifest": {
                    "path": _rel(params.dataset_manifest, root),
                    "sha256": dataset_manifest_sha256,
                    "schema_version": dataset_manifest.get("schema_version"),
                    "generated_utc": dataset_manifest.get("generated_utc"),
                    "source_url": dataset_manifest.get("source_url"),
                    "retrieval_utc": dataset_manifest.get("retrieval_utc"),
                    "retrieval_method": dataset_manifest.get("retrieval_method"),
                    "revision": dataset_manifest.get("revision"),
                    "raw_dir": dataset_manifest.get("raw_dir"),
                },
                "raw_replays_dir": _rel(params.raw_replays_dir, root),
                "raw_files": ingested.file_digests,
                "raw_files_total": len(ingested.files),
                "cache_manifest": {
                    "path": _rel(params.cache_manifest, root),
                    "sha256": hr.sha256_of(params.cache_manifest),
                },
                "metadata_files": {_rel(g.metadata_path, root): g.metadata_sha256 for g in games},
                "g1_results": {
                    run_id: {
                        "path": _rel(params.g1_runs_dir / run_id / "results.json", root),
                        "sha256": digest,
                    }
                    for run_id, digest in g1_digests.items()
                },
                "game_id_match_rule": GAME_ID_MATCH_RULE,
                "replay_game_ids_by_stem": ids_by_stem,
                "unmatched_replay_game_ids": unmatched,
                "dataset_agreement_summary": agreement_summary,
            },
        )

        metrics: list[dict[str, Any]] = [
            {"metric": "replay_units_ingested", "value": ingested.replay_units_ingested},
            {"metric": "replay_parse_failures", "value": parse_failures},
            {"metric": "replay_units_matched", "value": len(matched)},
            {"metric": "replay_units_unmatched", "value": sum(unmatched.values())},
            {"metric": "public_games_total", "value": len(games)},
            {"metric": "public_levels_total_from_metadata", "value": levels_total},
            {"metric": "derived_levels", "value": totals["derived_levels"]},
            {
                "metric": "human_baseline_level_coverage",
                "value": totals["human_baseline_level_coverage"],
            },
            {"metric": "exact_agreement_fraction", "value": totals["exact_agreement_fraction"]},
            {
                "metric": "median_abs_relative_difference",
                "value": totals["median_abs_relative_difference"],
            },
        ]
        for row in rows:
            key = f"[{row.game_id}][{row.level}]"
            metrics.append({"metric": f"official_baseline_actions{key}", "value": row.official})
            metrics.append({"metric": f"derived_baseline_actions{key}", "value": row.derived})

        results: dict[str, Any] = {
            "environment_generator_version": ENVIRONMENT_GENERATOR_VERSION,
            "operation": OPERATION,
            "network_guard": NetworkGuard.__name__,
            "dataset_manifest_sha256": dataset_manifest_sha256,
            "replay_units_ingested": ingested.replay_units_ingested,
            "replay_parse_failures": parse_failures,
            "replay_units_matched": len(matched),
            "replay_units_unmatched": sum(unmatched.values()),
            "participant_ids_available": ingested.participant_ids_available,
            "session_order_source": session_order_summary(ingested),
            "game_id_match_rule": GAME_ID_MATCH_RULE,
            "public_games_total": len(games),
            "public_levels_total_from_metadata": levels_total,
            "derived_levels": totals["derived_levels"],
            "human_baseline_level_coverage": totals["human_baseline_level_coverage"],
            "exact_agreement_fraction": totals["exact_agreement_fraction"],
            "median_abs_relative_difference": totals["median_abs_relative_difference"],
        }
        return RunOutcome(
            results=results,
            metrics=metrics,
            environment_results=[r.environment_row() for r in rows],
            environment_columns=ENVIRONMENT_COLUMNS,
            model_calls=0,
        )


register_runner(RUNNER_NAME, HumanBaselineRunner)
