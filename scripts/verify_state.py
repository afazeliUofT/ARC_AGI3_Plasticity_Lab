#!/usr/bin/env python3
"""Assert that PROJECT_STATE.json is well formed and agrees with the repository."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"schema_version","current_gate","gate_status","active_task","blocked_on",
            "next_action","mechanisms","consecutive_no_progress_turns","route_history"}
VALID_STATUS = {"not_started","in_progress","awaiting_verdict","passed","failed","blocked","skipped"}

def main() -> int:
    problems: list[str] = []
    sp = ROOT / "state" / "PROJECT_STATE.json"
    if not sp.exists():
        print("FAIL state/PROJECT_STATE.json is missing"); return 1
    try:
        st = json.loads(sp.read_text())
    except (OSError, ValueError) as e:
        print(f"FAIL PROJECT_STATE.json is not valid JSON: {e}"); return 1

    missing = REQUIRED - set(st)
    if missing:
        problems.append(f"missing keys: {sorted(missing)}")
    if st.get("gate_status") not in VALID_STATUS:
        problems.append(f"gate_status {st.get('gate_status')!r} is not one of {sorted(VALID_STATUS)}")
    if not str(st.get("next_action") or "").strip():
        problems.append("next_action is empty; a fresh session would have nothing to do")

    ledger = ROOT / "state" / "LEDGER.jsonl"
    if not ledger.exists():
        problems.append("state/LEDGER.jsonl is missing")
    else:
        for i, line in enumerate(ledger.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError as e:
                problems.append(f"LEDGER line {i} is not valid JSON: {e}"); continue
            for k in ("ts","gate","task","event","summary"):
                if k not in rec:
                    problems.append(f"LEDGER line {i} missing required field {k!r}")

    commit = st.get("last_verified_commit")
    if commit:
        r = subprocess.run(["git","cat-file","-e",f"{commit}^{{commit}}"],
                           cwd=ROOT, capture_output=True, check=False)
        if r.returncode != 0:
            problems.append(f"last_verified_commit {commit} does not exist in this repository")

    if problems:
        print("FAIL state verification")
        for p in problems:
            print("   -", p)
        return 1
    print(f"OK state consistent: gate={st['current_gate']} status={st['gate_status']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
