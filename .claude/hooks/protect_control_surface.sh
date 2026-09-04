#!/usr/bin/env bash
# Denies any write to the control surface, whether attempted through Write/Edit
# or smuggled through Bash. Matching only the edit tools would leave sed -i,
# tee, shell redirection and python -c wide open, which is the whole point.
payload="$(cat)"
protected='(^|[^A-Za-z0-9_./-])(preregistration/|scripts/verify_run\.py|scripts/supervisor\.py|state/PINNED_HASHES\.json|\.claude/|docs/EVIDENCE_)'
writes='(>|>>|\btee\b|\bsed\b[^|]*-i|\btruncate\b|\bdd\b|\bcp\b|\bmv\b|\bpython3?\b[^|]*-c|\bgit\b[^|]*\bcheckout\b[^|]*--|\brm\b|\bchmod\b)'

deny() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' "$1"
  exit 2
}

tool="$(printf '%s' "$payload" | grep -oP '"tool_name"\s*:\s*"\K[^"]+' | head -1)"
case "$tool" in
  Write|Edit|MultiEdit)
    path="$(printf '%s' "$payload" | grep -oP '"file_path"\s*:\s*"\K[^"]+' | head -1)"
    if printf '%s' "$path" | grep -qE "$protected"; then
      deny "Control surface is protected. AGENT_CONSTITUTION section 6 item 13: escalate instead of editing ${path}."
    fi
    ;;
  Bash)
    cmd="$(printf '%s' "$payload" | grep -oP '"command"\s*:\s*"\K([^"\\]|\\.)*' | head -1)"
    if printf '%s' "$cmd" | grep -qE "$protected" && printf '%s' "$cmd" | grep -qE "$writes"; then
      deny "Control surface is protected and this shell command would write to it. Escalate instead."
    fi
    ;;
esac
exit 0
