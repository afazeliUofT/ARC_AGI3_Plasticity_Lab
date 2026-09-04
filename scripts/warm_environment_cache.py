#!/usr/bin/env python3
"""Populate environment_files/ once, in NORMAL mode, using ARC_API_KEY.

OperationMode.OFFLINE never downloads - it only scans environment_files/ for
metadata.json. This script is the only thing that fills that directory. After it
succeeds the project runs offline forever with no key and no network.

    ARC_API_KEY=... uv run python scripts/warm_environment_cache.py
"""
from __future__ import annotations
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_DIR = ROOT / "environment_files"

PUBLIC_GAMES = [
    "ar25","bp35","cd82","cn04","dc22","ft09","g50t","ka59","lf52","lp85","ls20","m0r0",
    "r11l","re86","s5i5","sb26","sc25","sk48","sp80","su15","tn36","tr87","tu93","vc33","wa30",
]

def main() -> int:
    key = os.environ.get("ARC_API_KEY", "").strip()
    if not key:
        print("ARC_API_KEY is not set.\n"
              "Get one from https://arcprize.org and export it, then re-run:\n"
              "    export ARC_API_KEY=...\n"
              "Without a key only OperationMode.OFFLINE works, and it will find nothing.")
        return 2

    from arc_agi import Arcade, OperationMode

    ENV_DIR.mkdir(parents=True, exist_ok=True)
    arc = Arcade(arc_api_key=key, operation_mode=OperationMode.NORMAL,
                 environments_dir=str(ENV_DIR))

    ok, failed = [], []
    for gid in PUBLIC_GAMES:
        try:
            env = arc.make(gid)
        except Exception as e:                       # noqa: BLE001 - we want the id with it
            failed.append((gid, f"{type(e).__name__}: {e}")); continue
        # make() returns None on failure and does NOT raise. This assert is the point.
        if env is None:
            failed.append((gid, "make() returned None")); continue
        ok.append(gid)
        print(f"  cached {gid}")

    print(f"\ncached {len(ok)}/{len(PUBLIC_GAMES)} games into {ENV_DIR}")
    if failed:
        print("failed:")
        for gid, why in failed:
            print(f"  {gid}: {why}")

    offline = Arcade(operation_mode=OperationMode.OFFLINE, environments_dir=str(ENV_DIR))
    found = offline.get_environments()
    print(f"offline re-scan sees {len(found)} environments")
    for e in found[:3]:
        n = len(e.baseline_actions or [])
        print(f"  {e.game_id}: {n} per-level human baselines in metadata")
    return 0 if found else 1

if __name__ == "__main__":
    sys.exit(main())
