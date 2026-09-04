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

Edit `scripts/verify_run.py`, `scripts/supervisor.py`, `state/PINNED_HASHES.json`,
`.claude/**`, or `docs/EVIDENCE_*.md`. Those are frozen. If one needs to change, escalate
(constitution section 6 item 13).

## Pre-registration is write-once, not forbidden

Constitution C1 **requires** you to author `preregistration/<gate>.yaml` before the first
treatment run of a gate. Creating one is allowed and expected. Amending one that already
exists is denied by the hook, permanently. If you believe a pre-registration is wrong,
record the objection in the ledger and proceed, or kill the gate. Do not work around it.

Write pre-registrations with the Write tool, not with shell redirection, so the write-once
rule can be enforced.
