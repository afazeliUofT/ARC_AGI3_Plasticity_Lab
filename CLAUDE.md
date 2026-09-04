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

Edit `preregistration/**`, `scripts/verify_run.py`, `scripts/supervisor.py`,
`state/PINNED_HASHES.json`, `.claude/**`, or `docs/EVIDENCE_*.md`. Those are the control
surface. If one needs to change, escalate (constitution §6 item 13).
