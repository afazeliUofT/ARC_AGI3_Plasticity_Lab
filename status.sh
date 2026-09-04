#!/usr/bin/env bash
cd "$(dirname "$(readlink -f "$0")")"
echo "supervisor : $(pgrep -f scripts/supervisor.py >/dev/null && echo RUNNING || echo STOPPED)"
echo "turn       : $(pgrep -f 'claude -p' >/dev/null && echo 'in flight' || echo idle)"
echo "escalation : $([ -s state/ESCALATION.md ] && echo '*** NEEDS YOU ***' || echo clear)"
python3 -c "import json;s=json.load(open('state/PROJECT_STATE.json'));print('gate       :',s['current_gate'],s['gate_status'],'| no-progress',s['consecutive_no_progress_turns'])"
echo "commits    : $(git rev-list --count HEAD) | ledger: $(wc -l < state/LEDGER.jsonl) entries | digests: $(ls reports/ 2>/dev/null | wc -l)"
echo "clean tree : $([ -z "$(git status --porcelain)" ] && echo yes || echo no)"
echo "--- last 3 supervisor events ---"; tail -3 state/supervisor.jsonl
echo "--- last ledger entry ---"; tail -1 state/LEDGER.jsonl | cut -c1-300
