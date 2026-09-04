"""A synthetic G2 world in a temporary directory, laid out exactly as the pre-registration's
``experiment.inputs`` name the real one, so the E020 runner and the G2 verifier can be
exercised end to end without the released dataset.

Every count is read from the real ``preregistration/G2.yaml`` (games, levels, replay-unit
floor), never copied, so the synthetic world tracks the hash-locked thresholds. The replays
are written in the documented recorder format (one JSON event per issued action) and their
per-level counts are chosen so that the derived upper median equals the official baseline for
every completed level: participant ``p`` completes level ``l`` in ``official + (p mod 3) - 1``
actions. One level of one game is completed by nobody (derived ``None``), and one participant
has a faster second session that the first-run rule must exclude.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arc_plasticity.evaluation import human_replays as hr

G1_RUN_IDS = ("g1_fixed_a", "g1_fixed_b", "g1_contrast")
UNCOMPLETED_STEM_INDEX = 3  # this game's last level is completed by nobody
SECOND_SESSION_PARTICIPANT = 2  # has a faster second session on game 0 (excluded by rule)


@dataclass
class SyntheticWorld:
    root: Path
    inputs: dict[str, str]
    stems: list[str] = field(default_factory=list)
    game_ids: dict[str, str] = field(default_factory=dict)
    baselines: dict[str, list[int]] = field(default_factory=dict)
    participants_per_game: int = 0
    replay_files: int = 0
    expected_derived_levels: int = 0
    levels_total: int = 0

    @property
    def raw_dir(self) -> Path:
        return self.root / self.inputs["raw_replays_dir"]

    @property
    def dataset_manifest(self) -> Path:
        return self.root / self.inputs["dataset_manifest"]

    @property
    def cache_manifest(self) -> Path:
        return self.root / self.inputs["cache_manifest"]

    @property
    def environments_dir(self) -> Path:
        return self.root / self.inputs["environments_dir"]

    @property
    def g1_runs_dir(self) -> Path:
        return self.root / "artifacts" / "E100_arc_interface"

    def runner_params(self) -> dict[str, Any]:
        """Absolute-path runner params for a config that runs against this world."""
        return {
            "raw_replays_dir": str(self.raw_dir),
            "dataset_manifest": str(self.dataset_manifest),
            "environments_dir": str(self.environments_dir),
            "cache_manifest": str(self.cache_manifest),
            "g1_runs_dir": str(self.g1_runs_dir),
            "g1_run_ids": list(G1_RUN_IDS),
            "action_budget_multiplier": 5,
            "extra_artifacts": [
                "human_baselines.json",
                "replay_ingestion_log.jsonl",
                "input_manifest.json",
                "g1_termination_vs_budget.json",
            ],
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _events(
    game_id: str, participant: str, counts: list[int], start_ts: int
) -> list[dict[str, Any]]:
    """A recording in the released shape: opening frame, one record per action, scorecard.

    Record 1 is the play-start RESET frame (action id 0, not an issued action); the scorecard's
    ``actions_by_level`` carries the toolkit's ``(level, actions_so_far)`` pairs so path P2
    agrees with the step log by construction.
    """
    cumulative: list[int] = []
    total = 0
    for c in counts:
        total += c
        cumulative.append(total)
    guid = f"{participant}-{game_id}-{start_ts}"
    events: list[dict[str, Any]] = []
    for i in range(total + 1):
        completed = sum(1 for c in cumulative if c <= i)
        events.append(
            {
                "timestamp": start_ts + i,
                "participant_id": participant,
                "guid": guid,
                "data": {
                    "game_id": game_id,
                    "levels_completed": completed,
                    "state": "WIN" if completed == len(counts) and counts else "NOT_FINISHED",
                    "action_input": {"id": 0 if i == 0 else 1},
                },
            }
        )
    events.append(
        {
            "timestamp": start_ts + total + 1,
            "data": {
                "won": int(bool(counts)),
                "played": 1,
                "total_actions": total,
                "levels_completed": len(counts),
                "cards": {
                    game_id: {
                        "game_id": game_id,
                        "total_plays": 1,
                        "guids": [guid],
                        "levels_completed": [len(counts)],
                        "states": ["WIN" if counts else "NOT_FINISHED"],
                        "actions": [total],
                        "actions_by_level": [
                            [[level, c] for level, c in enumerate(cumulative, start=1)]
                        ],
                        "resets": [0],
                        "total_actions": total,
                    }
                },
            },
        }
    )
    return events


def build_world(root: Path, prereg: dict[str, Any]) -> SyntheticWorld:
    """Create the whole synthetic world under ``root`` and commit it (git) with a LICENSE."""
    thresholds = prereg["thresholds"]
    games_total = int(thresholds["public_games_total"])
    levels_total = int(thresholds["public_levels_total"])
    units_min = int(thresholds["replay_units_min"])
    inputs = {k: str(v) for k, v in prereg["experiment"]["inputs"].items()}
    world = SyntheticWorld(root=root, inputs=inputs, levels_total=levels_total)

    base, extra = divmod(levels_total, games_total)
    env_dir = world.environments_dir
    manifest_games: list[dict[str, Any]] = []
    for i in range(games_total):
        stem = f"s{i:03d}"
        game_id = f"{stem}-deadbeef"
        n_levels = base + (1 if i < extra else 0)
        baselines = [10 + i + level for level in range(1, n_levels + 1)]
        game_dir = env_dir / stem / "deadbeef"
        game_dir.mkdir(parents=True)
        (game_dir / f"{stem}.py").write_text(f"# synthetic {stem}\n")
        meta = {"game_id": game_id, "title": stem.upper(), "baseline_actions": baselines}
        (game_dir / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
        files = {f"{stem}/deadbeef/{p.name}": _sha256(p) for p in sorted(game_dir.iterdir())}
        manifest_games.append(
            {
                "stem": stem,
                "game_id": game_id,
                "local_dir": f"{inputs['environments_dir']}/{stem}/deadbeef",
                "date_downloaded": "2026-09-04T00:00:00Z",
                "baseline_actions_count": n_levels,
                "files": files,
            }
        )
        world.stems.append(stem)
        world.game_ids[stem] = game_id
        world.baselines[stem] = baselines
    world.cache_manifest.parent.mkdir(parents=True, exist_ok=True)
    world.cache_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_utc": "2026-09-04T00:00:00Z",
                "environments_dir": inputs["environments_dir"],
                "totals": {"games": games_total, "files": 2 * games_total},
                "games": manifest_games,
            },
            indent=2,
        )
        + "\n"
    )

    # Replays: enough participants per game to exceed the replay-unit floor.
    per_game = -(-units_min // games_total) + 1
    world.participants_per_game = per_game
    raw = world.raw_dir
    raw.mkdir(parents=True)
    n_files = 0
    for i, stem in enumerate(world.stems):
        game_id = world.game_ids[stem]
        baselines = world.baselines[stem]
        for p in range(1, per_game + 1):
            counts = [b + (p % 3) - 1 for b in baselines]
            if i == UNCOMPLETED_STEM_INDEX:
                counts = counts[:-1]  # nobody completes the last level of this game
            events = _events(game_id, f"P{p:03d}", counts, start_ts=1_000_000 * p)
            path = raw / stem / f"{stem}_P{p:03d}_s1.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(json.dumps(e) + "\n" for e in events))
            n_files += 1
            if i == 0 and p == SECOND_SESSION_PARTICIPANT:
                faster = [max(1, c - 5) for c in counts]
                events = _events(game_id, f"P{p:03d}", faster, start_ts=1_000_000 * p + 500_000)
                (raw / stem / f"{stem}_P{p:03d}_s2.jsonl").write_text(
                    "".join(json.dumps(e) + "\n" for e in events)
                )
                n_files += 1
    world.replay_files = n_files
    world.expected_derived_levels = levels_total - 1

    # Dataset manifest via the project's own builder.
    import importlib.util
    import sys

    project_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "build_human_replays_manifest", project_root / "scripts" / "build_human_replays_manifest.py"
    )
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("build_human_replays_manifest", builder)
    spec.loader.exec_module(builder)
    manifest = builder.build_manifest(
        root,
        raw,
        source_url="https://example.invalid/synthetic",
        retrieval_method="human_placed",
        retrieval_utc=datetime(2026, 9, 4, tzinfo=UTC),
        revision="synthetic-1",
    )
    builder.write_manifest(manifest, world.dataset_manifest)

    # Three synthetic G1 runs with per-game termination records.
    for k, run_id in enumerate(G1_RUN_IDS):
        seed = 12345 if k < 2 else 12346
        run_dir = world.g1_runs_dir / run_id
        run_dir.mkdir(parents=True)
        games = [
            {
                "game_id": world.game_ids[stem],
                "seed": seed,
                "steps_taken": 40 + 3 * j + k,
                "final_state": "GAME_OVER",
                "levels_completed": 0,
                "stop_reason": "terminal",
            }
            for j, stem in enumerate(world.stems)
        ]
        (run_dir / "results.json").write_text(
            json.dumps(
                {
                    "seed": seed,
                    "completion_status": "completed",
                    "results": {"action_budget_per_game": 5000, "games": games},
                },
                indent=2,
            )
            + "\n"
        )

    # The G0 exclusion list the G2 determinism protocol names, at the path it names.
    src = str(prereg["determinism_protocol"]["excluded_fields_source"])
    (root / src).parent.mkdir(parents=True, exist_ok=True)
    (root / src).write_bytes((project_root / src).read_bytes())

    (root / "LICENSE").write_text(f"{thresholds['licence_required_text']}\n\nSynthetic.\n")
    (root / ".gitignore").write_text("artifacts/E020_human_baselines/\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], cwd=root, check=True)
    subprocess.run([*git, "add", "-A"], cwd=root, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "synthetic G2 world"], cwd=root, check=True)
    return world


def ingestion_counts(world: SyntheticWorld) -> tuple[int, int]:
    """(replay units, parse failures) the loader sees in the world's raw directory."""
    result = hr.ingest_directory(world.raw_dir)
    return result.replay_units_ingested, len(result.parse_failures)
