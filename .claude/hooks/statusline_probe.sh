#!/usr/bin/env bash
# Dual purpose: renders a status line, and persists the rate-limit gauge so the
# supervisor can pause proactively. Whether this fires in headless -p mode is
# UNCONFIRMED (EVIDENCE_TOOLING section 7). If state/usage.json never appears,
# the supervisor falls back to detecting the rate-limit error directly, which
# costs one failed turn per window and nothing else.
payload="$(cat)"
printf '%s' "$payload" > "${CLAUDE_PROJECT_DIR:-.}/state/usage_raw.json" 2>/dev/null || true
python3 - "$payload" <<'PY' 2>/dev/null || echo "arc-lab"
import json, sys, os, pathlib
try:
    d = json.loads(sys.argv[1])
except Exception:
    print("arc-lab"); raise SystemExit
rl = d.get("rate_limits") or {}
out = {}
for k in ("five_hour", "seven_day"):
    w = rl.get(k) or {}
    if "used_percentage" in w:
        out[k] = {"used_percentage": w.get("used_percentage"), "resets_at": w.get("resets_at")}
if out:
    p = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / "state" / "usage.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out))
    print("arc-lab  5h {:.0f}%  7d {:.0f}%".format(
        out.get("five_hour", {}).get("used_percentage", 0) or 0,
        out.get("seven_day", {}).get("used_percentage", 0) or 0))
else:
    print("arc-lab  (usage gauge not yet reported)")
PY
