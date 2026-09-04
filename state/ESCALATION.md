# Escalation (turn 2): execution is still denied, and two more hook conflicts with G0

Gate: G0 · Task: G0.1 · Time: 2026-09-04T05:55:00Z · Turn: 2
Constitution grounds: section 6 item 13 (control surface change).

**How to reply: append a section to this file that begins with `## ANSWER`.** Nothing else
clears the block. The supervisor moves this file to `state/escalations/<timestamp>.md`, clears
`blocked_on`, and resumes. Item 1 alone unblocks execution and committing. Items 2 and 3 will
block G0 completion later, so answering them now saves a third escalation.

Thank you for the turn-1 fix. The hook's absolute-path matching and the write-once
pre-registration rule both work as described, and I authored `preregistration/G0.yaml` this
turn as you directed (SHA-256 `c91c197a0eab9764a67a2fbeeb0771825c95d8d294388c3eb6fe166f4f1f4620`,
uncommitted, see item 1).

---

## 1. Execution and git writes are still auto-denied (blocking)

The allowlist change did not resolve it, because the cause is the read block, not the
allowlist. This turn, all of the following were refused:

```
python3 scripts/verify_state.py
uv run pytest -q
uv --version
.venv/bin/python -m pytest -q
python3 -c "print(1)"
git add state/LEDGER.jsonl
```

The refusal for the inline-python form states the cause verbatim:

```
python3 runs inline code, which cannot be checked against the read block; under the read
block (permissions.blockReadsOutsideWorkingDirectories) a command the shell parser cannot
analyze asks the person
```

With `--permission-prompts none`, "asks the person" becomes an automatic denial. Interpreters,
`uv`, `pytest` and even `git add` fall into "cannot analyze". `.claude/settings.json` line 21
still has `"blockReadsOutsideWorkingDirectories": true`. Commands that do work: `sha256sum`,
`date`, `ls`, `cat`, `grep`, `jq`, `wc`, and read-only `git` (status, diff, log, show).

**Requested change.** Set `"blockReadsOutsideWorkingDirectories": false`. The
`Read(../**)`, `Edit(../**)`, `Write(../**)` deny rules still prevent the agent's own tools
from leaving the project directory. Then delete `state/PINNED_HASHES.json` so the supervisor
re-pins the new settings hash, or expect it to halt on the mismatch.

**Also please commit the working tree**, or leave it for me to commit once git works. It holds:
`preregistration/G0.yaml` (new), `state/PINNED_HASHES.json` (your fix commit removed it from
git; the supervisor re-created it on re-pin; it is untracked now and the repository contract
lists it as tracked), `state/escalations/20260904T055252Z.md` (new), and this turn's
`state/LEDGER.jsonl`, `state/PROJECT_STATE.json`, `state/ESCALATION.md`.

**What I do with each answer.** Fixed: next turn I commit the tree, run `verify_state.py`,
`pytest`, `ruff`, `mypy`, record outputs, and start the G0 items. Not fixed: I cannot proceed
and the run should be stopped.

## 2. The hook forbids creating `scripts/verify_run.py` (blocks G0 completion)

`scripts/verify_run.py` does not exist. Constitution section 7 says "you author the verifier
and the pre-registration in the first place", and `preregistration/G0.yaml` names it as the
reader of its thresholds. The hook's `FROZEN` pattern denies creating it by any tool.

**Options.**
- (a) Treat it exactly like `preregistration/`: creation permitted while absent, every later
  write denied, and the supervisor pins its hash once it exists (it is already in
  `CONTROL_SURFACE`, so pinning is automatic on the next supervisor loop).
- (b) You author it yourself.

**What I do.** (a): I write it once, with unit tests in `tests/unit/`, and never touch it
again; changes go through escalation as C2 requires. (b): I wait for it and build the
artifact contract to match whatever it reads.

## 3. The hook forbids the write-back to `docs/EVIDENCE_TOOLING.md` that G0 requires

G0's predicate: "every `[VERIFY-ON-MACHINE]` item in `docs/EVIDENCE_TOOLING.md` section 11 is
resolved and written back." Section 6 item 13 explicitly permits append-only additions to
evidence documents. The hook denies every write to `docs/EVIDENCE_*` regardless.

**Options.**
- (a) I write resolutions to a new file, `docs/TOOLING_VERIFICATION.md`, one dated entry per
  item with the command and artifact path that produced the observation, and you merge them
  into section 11 (or the referee reads both).
- (b) You provide an append-only path, for example a script outside my write reach that
  appends a block I pass to it, and the hook allows that script.
- (c) You resolve the eight items yourself.

**What I do.** (a) is my default if you say nothing else about it: it keeps the evidence
documents frozen and still produces the dated record the predicate asks for. `G0.yaml`'s
threshold `verify_on_machine_items_resolved_min: 8` counts entries in whichever file you
choose.

## Noted, no answer needed

- `preregistration/G0.yaml` carries `authored_utc: 2026-09-04T06:05:00Z`; the actual write was
  at 05:54:21Z. I mistyped it and the file is write-once, so it stays. The ledger timestamp is
  authoritative and the discrepancy is recorded there and in `open_questions`.
- The supervisor now pins five files; `preregistration/**` has no layer-2 hash protection
  beyond the write-once hook. Raised in turn 1 item 2; still open.
