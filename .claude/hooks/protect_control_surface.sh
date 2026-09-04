#!/usr/bin/env bash
# Protects the control surface. Two distinct rules:
#   FROZEN - never writable by the agent, by any tool, at any time.
#   PREREG - WRITE ONCE. C1 requires authoring it before results exist; it may
#            never be amended afterwards.
payload="$(cat)"

deny() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' "$1"
  exit 2
}

# The boundary class deliberately PERMITS "/" so absolute paths match too:
# /home/x/lab/preregistration/G0.yaml must be caught, not only the relative form.
FROZEN='(^|[^A-Za-z0-9_.-])(scripts/verify_run\.py|scripts/supervisor\.py|state/PINNED_HASHES\.json|\.claude/|docs/EVIDENCE_)'
PREREG='(^|[^A-Za-z0-9_.-])preregistration/'
WRITES='(>|>>|\btee\b|\bsed\b[^|]*-i|\btruncate\b|\bdd\b|\bcp\b|\bmv\b|\bpython3?\b[^|]*-c|\bgit\b[^|]*\bcheckout\b[^|]*--|\brm\b|\bchmod\b)'

tool="$(printf '%s' "$payload" | grep -oP '"tool_name"\s*:\s*"\K[^"]+' | head -1)"

case "$tool" in
  Write|Edit|MultiEdit|NotebookEdit)
    path="$(printf '%s' "$payload" | grep -oP '"file_path"\s*:\s*"\K[^"]+' | head -1)"
    if printf '%s' "$path" | grep -qE "$FROZEN"; then
      deny "Control surface is frozen. Escalate (constitution section 6 item 13) instead of editing ${path}."
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
      deny "Control surface is frozen and this shell command would write to it. Escalate instead."
    fi
    if printf '%s' "$cmd" | grep -qE "$PREREG" && printf '%s' "$cmd" | grep -qE "$WRITES"; then
      deny "Write pre-registrations with the Write tool, not the shell, so the write-once rule can be enforced."
    fi
    ;;
esac
exit 0
