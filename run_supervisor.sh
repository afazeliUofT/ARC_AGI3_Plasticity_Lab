#!/usr/bin/env bash
# Start the supervisor fully detached from any terminal.
#   setsid  - new session, so a closing window's SIGHUP cannot reach the tree
#   nohup   - belt and braces
#   -u      - unbuffered, so state/supervisor.out is live rather than blocked
#   >>      - append, so a restart never truncates a file an old process holds
set -Eeuo pipefail
cd "$(dirname "$(readlink -f "$0")")"
if pgrep -f "scripts/supervisor.py" >/dev/null; then
  echo "already running:"; pgrep -af "scripts/supervisor.py"; exit 0
fi
setsid nohup python3 -u scripts/supervisor.py >> state/supervisor.out 2>&1 < /dev/null &
sleep 2
echo "started:"; pgrep -af "scripts/supervisor.py" || echo "  FAILED - see state/supervisor.out"
