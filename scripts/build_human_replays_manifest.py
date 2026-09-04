"""Write or verify ``experiments/human_replays_manifest.json`` from ``data/human_replays/raw/``.

Usage::

    uv run python scripts/build_human_replays_manifest.py --source-url URL \
        --retrieval-method {human_placed,agent_download} [--retrieval-utc ISO] \
        [--revision TEXT] [--raw-dir PATH] [--output PATH]
    uv run python scripts/build_human_replays_manifest.py --check [--raw-dir PATH] [--output PATH]

The manifest is the integrity record of the gitignored raw directory (G2 pre-registration,
``dataset_acquisition`` step 3): ``source_url``, ``retrieval_utc``, ``retrieval_method``,
optional ``revision``, ``files`` (relative path -> ``{sha256, bytes, replay_units,
parse_failure}``) and ``totals``. The script refuses to run when the raw directory is absent
or empty, and it never creates anything under ``artifacts/``: artifacts are produced only by
``scripts/run_experiment.py``. ``--check`` compares the raw directory with the committed
manifest and exits non-zero on any drift in either direction.
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

from arc_plasticity.evaluation import human_replays

SCHEMA_VERSION = 1
DEFAULT_RAW_DIR = "data/human_replays/raw"
DEFAULT_OUTPUT = "experiments/human_replays_manifest.json"
RETRIEVAL_METHODS = ("human_placed", "agent_download")


class RawLayoutError(RuntimeError):
    """The raw directory is absent, empty, or not where the manifest expects it."""


def build_manifest(
    root: Path,
    raw_dir: Path,
    *,
    source_url: str,
    retrieval_method: str,
    retrieval_utc: datetime,
    revision: str | None,
) -> dict[str, Any]:
    """The manifest as a plain dict. ``raw_dir`` must be inside ``root`` and non-empty."""
    if not raw_dir.is_dir():
        raise RawLayoutError(f"{raw_dir} is not a directory; place the dataset there first")
    if not human_replays.raw_files(raw_dir):
        raise RawLayoutError(f"{raw_dir} holds no files; place the dataset there first")
    if retrieval_method not in RETRIEVAL_METHODS:
        raise RawLayoutError(f"retrieval_method must be one of {RETRIEVAL_METHODS}")
    if not source_url:
        raise RawLayoutError("source_url must be non-empty")
    raw_rel = raw_dir.resolve().relative_to(root.resolve()).as_posix()

    ingested = human_replays.ingest_directory(raw_dir)
    files: dict[str, dict[str, Any]] = {}
    for parsed in ingested.files:
        files[parsed.source_file] = {
            "sha256": parsed.sha256,
            "bytes": parsed.bytes,
            "replay_units": len(parsed.sessions),
            "parse_failure": None if parsed.failure is None else parsed.failure.reason,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": _iso(datetime.now(UTC)),
        "source_url": source_url,
        "retrieval_utc": _iso(retrieval_utc),
        "retrieval_method": retrieval_method,
        "revision": revision,
        "raw_dir": raw_rel,
        "files": files,
        "totals": {
            "files": len(files),
            "bytes": sum(f["bytes"] for f in files.values()),
            "replay_units": ingested.replay_units_ingested,
            "parse_failures": len(ingested.parse_failures),
            "participant_ids_available": ingested.participant_ids_available,
        },
    }


def drift(manifest: dict[str, Any], raw_dir: Path) -> list[str]:
    """Human-readable differences between the raw directory and ``manifest['files']``.

    Delegates to ``human_replays.manifest_drift`` so the builder, the E020 runner's preflight
    and the G2 verifier share one definition.
    """
    return human_replays.manifest_drift(manifest.get("files"), raw_dir)


def write_manifest(manifest: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _iso(when: datetime) -> str:
    return when.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(text: str) -> datetime:
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="directory the manifest's raw_dir is recorded relative to (default: the repository)",
    )
    ap.add_argument("--raw-dir", type=Path, default=ROOT / DEFAULT_RAW_DIR)
    ap.add_argument("--output", type=Path, default=ROOT / DEFAULT_OUTPUT)
    ap.add_argument(
        "--check", action="store_true", help="verify the raw directory against the manifest"
    )
    ap.add_argument("--source-url", default=None)
    ap.add_argument("--retrieval-method", choices=RETRIEVAL_METHODS, default=None)
    ap.add_argument("--retrieval-utc", default=None, help="ISO-8601; default: now")
    ap.add_argument("--revision", default=None, help="dataset revision/ETag/Last-Modified if known")
    args = ap.parse_args(argv)

    if args.output.resolve().is_relative_to((args.root / "artifacts").resolve()):
        print("FAIL: the manifest is never written under artifacts/", file=sys.stderr)
        return 2
    if args.check:
        if not args.output.is_file():
            print(f"FAIL: {args.output} does not exist", file=sys.stderr)
            return 1
        if not args.raw_dir.is_dir():
            print(f"FAIL: {args.raw_dir} is not a directory", file=sys.stderr)
            return 1
        manifest = json.loads(args.output.read_text(encoding="utf-8"))
        problems = drift(manifest, args.raw_dir)
        for problem in problems:
            print(f"DRIFT: {problem}", file=sys.stderr)
        print(json.dumps({"checked": len(manifest.get("files", {})), "drift": len(problems)}))
        return 1 if problems else 0

    if args.source_url is None or args.retrieval_method is None:
        print(
            "FAIL: --source-url and --retrieval-method are required (or use --check)",
            file=sys.stderr,
        )
        return 2
    try:
        retrieval_utc = _parse_utc(args.retrieval_utc) if args.retrieval_utc else datetime.now(UTC)
        manifest = build_manifest(
            args.root,
            args.raw_dir,
            source_url=args.source_url,
            retrieval_method=args.retrieval_method,
            retrieval_utc=retrieval_utc,
            revision=args.revision,
        )
    except (RawLayoutError, human_replays.HumanReplayError, ValueError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    write_manifest(manifest, args.output)
    rel = (
        args.output.relative_to(args.root) if args.output.is_relative_to(args.root) else args.output
    )
    print(json.dumps({"output": str(rel), **manifest["totals"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
