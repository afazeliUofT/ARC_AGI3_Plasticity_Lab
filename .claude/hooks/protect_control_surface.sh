#!/usr/bin/env bash
# Three rules, deliberately narrow. A control that forbids required work is a
# deadlock, so this protects only what the agent never legitimately needs to
# write. The real guarantees live elsewhere: thresholds in the write-once
# pre-registration, verdicts with the referee, and git history throughout.
#
#   FROZEN - never writable, by any tool, at any time.
#   PREREG - write once. C1 requires authoring it; nothing may amend it.
#   (evidence documents are writable here; the supervisor enforces append-only)
payload="$(cat)"

deny() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' "$1"
  exit 2
}

# The boundary class deliberately PERMITS "/" so absolute paths match too.
FROZEN='(^|[^A-Za-z0-9_.-])(scripts/supervisor\.py|state/PINNED_HASHES\.json|\.claude/|AGENT_CONSTITUTION\.md|PROPOSAL_v2\.md)'
PREREG='(^|[^A-Za-z0-9_.-])preregistration/'
WRITES='(>|>>|\btee\b|\bsed\b[^|]*-i|\btruncate\b|\bdd\b|\bcp\b|\bmv\b|\bpython3?\b[^|]*-c|\bgit\b[^|]*\bcheckout\b[^|]*--|\brm\b|\bchmod\b)'

tool="$(printf '%s' "$payload" | grep -oP '"tool_name"\s*:\s*"\K[^"]+' | head -1)"

case "$tool" in
  Write|Edit|MultiEdit|NotebookEdit)
    path="$(printf '%s' "$payload" | grep -oP '"file_path"\s*:\s*"\K[^"]+' | head -1)"
    if printf '%s' "$path" | grep -qE "$FROZEN"; then
      deny "Frozen: ${path}. Escalate (constitution section 6 item 13) rather than editing the control surface."
    fi
    if printf '%s' "$path" | grep -qE "$PREREG"; then
      if [ -e "$path" ]; then
        deny "Pre-registration ${path} exists and is frozen. C1 permits authoring it once, before results; never amending it. Record the objection in the ledger, or kill the gate."
      fi
      exit 0
    fi
    ;;
  Bash)
    cmd="$(printf '%s' "$payload" | grep -oP '"command"\s*:\s*"\K([^"\\]|\\.)*' | head -1)"
    if printf '%s' "$cmd" | grep -qE "$FROZEN" && printf '%s' "$cmd" | grep -qE "$WRITES"; then
      deny "Frozen control surface, and this shell command would write to it. Escalate instead."
    fi
    if printf '%s' "$cmd" | grep -qE "$PREREG" && printf '%s' "$cmd" | grep -qE "$WRITES"; then
      deny "Write pre-registrations with the Write tool, not the shell, so the write-once rule can be enforced."
    fi
    ;;
esac
exit 0
