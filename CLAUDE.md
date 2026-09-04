# ARC-AGI-3 Plasticity Lab

You are running under a written constitution. Read it before anything else, every session.

@AGENT_CONSTITUTION.md

Governing science document: @PROPOSAL_v2.md
External ground truth, never overridden: @docs/EVIDENCE_ARC.md @docs/EVIDENCE_NEURO.md @docs/EVIDENCE_TOOLING.md

## The three things you get wrong if you skip the evidence base

1. `OperationMode.OFFLINE` **never downloads**. An `ARC_API_KEY` in `NORMAL` mode fills
   `environment_files/` once; after that the project is offline forever.
2. `Arcade.make()` returns **`None`** on failure, it does not raise. Assert `env is not None`
   at every call site.
3. Do **not** reimplement RHAE. `arc_agi.scorecard.EnvironmentScoreCalculator` is the reference
   implementation: `min(((baseline/actions)**2)*100, 115.0)`, level weight `w_l = l`.

## Every turn

Read `state/PROJECT_STATE.json`, the tail of `state/LEDGER.jsonl`, and `state/BUDGET.json`.
Do one verifiable thing. Append to the ledger. Update the state. Commit. Write `next_action`
so a session with no memory could continue.

## Never

Edit `scripts/supervisor.py`, `state/PINNED_HASHES.json`, `.claude/**`,
`AGENT_CONSTITUTION.md`, or `PROPOSAL_v2.md`. Those are frozen. If one needs to change,
escalate (constitution section 6 item 13).

## What you ARE required to write

- **`preregistration/<gate>.yaml`** - write-once. C1 requires authoring it before the first
  treatment run; nothing may amend it afterwards. Use the Write tool, not shell redirection.
- **`scripts/verify_run.py`** - G0 requires you to author the verifier. Every numeric
  threshold it applies must be read from the gate's hash-locked pre-registration, never
  hard-coded here. That is what makes an editable verifier safe.
- **`docs/EVIDENCE_*.md`** - the G0 predicate requires writing the VERIFY-ON-MACHINE results
  back. Additions only: every new claim carries a URL and a date, and you never delete or
  weaken an existing entry. The supervisor halts the run if an evidence document shrinks.
