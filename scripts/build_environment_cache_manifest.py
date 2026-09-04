#!/usr/bin/env python3
"""Write ``experiments/environment_cache_manifest.json`` from what is under ``environment_files/``.

``preregistration/G1.yaml`` ``cache_warming`` requires the committed record of the offline
cache to be a manifest produced by a script, not by the model. This is that script. It walks
the cache with the same ``iter_environment_files`` the verifier uses, so the two can only
disagree if the files on disk changed.

    uv run python scripts/build_environment_cache_manifest.py [--environments-dir DIR]
                                                              [--output PATH]

Layout of each ``games[]`` entry (the verifier's ``G1_CACHE_GAME_KEYS``): ``stem``,
``game_id`` (from ``metadata.json``), ``local_dir`` (relative to the repository),
``date_downloaded``, ``baseline_actions_count`` and ``files`` (``{path relative to
environments_dir: sha256}``). Derived bytecode is never listed.

Note for readers of the hashes: every ``metadata.json`` the toolkit writes carries the absolute
``local_dir`` of the machine that downloaded it, so the hash of ``metadata.json`` is specific
to that machine's path. That is a property of the toolkit's file format, recorded here so
nobody mistakes a fresh download on another path for cache corruption.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from arc_plasticity.environments import arc_interface

SCHEMA_VERSION = 1
DEFAULT_ENVIRONMENTS_DIR = "environment_files"
DEFAULT_OUTPUT = "experiments/environment_cache_manifest.json"


class CacheLayoutError(RuntimeError):
    """The cache does not have the ``<stem>/<version>/metadata.json`` layout the toolkit writes."""


def _game_dirs(environments_dir: Path) -> list[Path]:
    """Every directory holding a ``metadata.json``, sorted. One per cached game."""
    return sorted(p.parent for p in environments_dir.rglob("metadata.json") if p.is_file())


def build_manifest(root: Path, environments_dir: Path, now: datetime) -> dict[str, Any]:
    """The manifest as a plain dict. ``environments_dir`` must be inside ``root``."""
    if not environments_dir.is_dir():
        raise CacheLayoutError(f"{environments_dir} is not a directory")
    env_rel = environments_dir.resolve().relative_to(root.resolve()).as_posix()
    hashes = arc_interface.hash_environment_files(environments_dir)

    games: list[dict[str, Any]] = []
    seen_stems: set[str] = set()
    for game_dir in _game_dirs(environments_dir):
        meta = json.loads((game_dir / "metadata.json").read_text(encoding="utf-8"))
        game_id = str(meta.get("game_id") or "")
        if not game_id:
            raise CacheLayoutError(f"{game_dir}/metadata.json has no game_id")
        stem = arc_interface.game_stem(game_id)
        if stem in seen_stems:
            raise CacheLayoutError(f"stem {stem!r} cached more than once under {environments_dir}")
        seen_stems.add(stem)
        rel_dir = game_dir.relative_to(environments_dir).as_posix()
        files = {
            rel: digest for rel, digest in hashes.items()
            if rel == rel_dir or rel.startswith(rel_dir + "/")
        }
        if not files:
            raise CacheLayoutError(f"{game_dir} holds no hashable files")
        games.append(
            {
                "stem": stem,
                "game_id": game_id,
                "local_dir": f"{env_rel}/{rel_dir}",
                "date_downloaded": meta.get("date_downloaded"),
                "baseline_actions_count": len(meta.get("baseline_actions") or []),
                "files": files,
            }
        )
    games.sort(key=lambda g: str(g["stem"]))

    listed = sum(len(g["files"]) for g in games)
    if listed != len(hashes):
        stray = sorted(set(hashes) - {rel for g in games for rel in g["files"]})
        raise CacheLayoutError(f"files under {environments_dir} belong to no game: {stray}")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "environments_dir": env_rel,
        "games": games,
        "totals": {"games": len(games), "files": listed},
    }


def write_manifest(manifest: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--environments-dir", type=Path, default=ROOT / DEFAULT_ENVIRONMENTS_DIR)
    ap.add_argument("--output", type=Path, default=ROOT / DEFAULT_OUTPUT)
    args = ap.parse_args(argv)
    try:
        manifest = build_manifest(ROOT, args.environments_dir, datetime.now(UTC))
    except (CacheLayoutError, ValueError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    write_manifest(manifest, args.output)
    rel = args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output
    print(json.dumps({"output": str(rel), **manifest["totals"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
