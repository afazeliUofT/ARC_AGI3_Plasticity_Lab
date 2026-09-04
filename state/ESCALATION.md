# ESCALATION — G3.5 (second), constitution section 6 item 1 and item 13

Written 2026-09-04T21:30Z at commit b0442cf plus this turn's work (the commit follows). Gate G3,
task G3.5. Your answer of 21:17Z (`state/escalations/20260904T211800Z.md`) is applied in full;
one premise of it turned out to be false on this machine, and one control-surface defect from
the previous turn needs your authorisation. Two asks.

**How to answer:** append a section to THIS file beginning with a line `## ANSWER` and commit
or leave it in the working tree. Nothing else counts (not a chat message, not an edit
elsewhere). The supervisor and the next turn check for that line; on finding it the file is
moved to `state/escalations/<timestamp>.md`, `blocked_on` is cleared, and work resumes.

## Ask 1 — the turn's shell does not carry `CLAUDE_CODE_OAUTH_TOKEN` (section 6 item 1)

Your answer said the turn inherits the supervisor's environment and that the adapter drops
the variable. The first half is true, the second is not, and there is a third process in
between. Measured this turn by comparing environment **key names** via `/proc/<pid>/environ`
(values never read):

| process | has `CLAUDE_CODE_OAUTH_TOKEN` |
|---|---|
| `python3 scripts/supervisor.py` (pid 1964325) | yes |
| the turn's `claude -p` process (pid 1974120, 2.1.260) | yes |
| the Bash tool's shell inside that turn (where `run_experiment.py` runs) | **no** — it is the only key missing |

So Claude Code strips the credential from its own tool subprocesses. The adapter already
forwarded the parent environment minus `ARC_*` and the two nested-session markers (it never
built a minimal environment; `test_headless_call_flags_cwd_stdin_env_and_usage` pins the
forwarding, now including the token). Nothing the supervisor or the adapter does with plain
inheritance can put the variable into a runner started from a turn.

Everything else in your answer is implemented and tested this turn (pytest 448 passed,
2 skipped, 1 failed; the failure is pre-existing at HEAD and explained in Ask 2):

- absent at call time → `CallRefused("authentication_unavailable")` **before any process
  starts**, no login attempt, the value never logged (unit test with a fake `claude`; a
  full synthetic game-run through the adapter is scanned file by file for `sk-ant-`);
- `token_file` refused for every config (declined route), the parameter kept only for the
  test that pins non-recording, documented as untested;
- spend control in `configs/experiments/E300_ref.yaml`: serial calls, at most 40 calls or
  1200 s cumulative nested wall-clock per run, whichever binds first, then the run completes
  model-free with partial results; the remaining cap bounds each call's own timeout;
  `results.json` records `model_wallclock_seconds_total`, `spend_control` and which limit
  bound (`model_budget_binding`); every `model_calls.jsonl` row carries wall-clock, `usage`
  verbatim, the model identifier sent and reported, and `program_returned`;
- `state/BUDGET.json g3_preflight` records `weekly_allowance_usd_equivalent: "unknown"`, the
  throttle currency and the provisional caps; no percentage-of-weekly figure will be computed;
- the probe was repeated through the adapter: refused before spawning, exit_code -2, 0.0 s.

Routes that would work, in the order I would take them. None was implemented, because each
needs your decision:

- **(a) A second variable name.** In `scripts/supervisor.py` (frozen, your edit) export the
  same value under a name the CLI does not strip, for example
  `PLASTICITY_LAB_OAUTH_TOKEN=$CLAUDE_CODE_OAUTH_TOKEN` (not an `ARC_*` name, which the
  adapter strips). The adapter then maps it to `CLAUDE_CODE_OAUTH_TOKEN` in the child only
  (three lines, unit-tested with the fake). The evidence that this works is the key
  comparison above: the CLI removes one specific key and passes twelve others through. It
  is verified by execution with the probe before any game-run. Same in-memory-only property
  as your route; no disk copy.
- **(b) Read the ancestor's environment.** Authorise the adapter to read
  `/proc/<ancestor claude pid>/environ` at call time when the variable is absent. Works
  today with no supervisor edit, stays in memory, but it deliberately circumvents the CLI's
  stripping, which is why I did not do it on my own authority.
- **(c) Run the game-runs outside a turn.** The supervisor itself starts
  `run_experiment.py` as a direct child (it has the variable), a larger frozen-file change.
- **(d) Token file** — declined by you; not proposed again.

If you answer (a), tell me the exact variable name. If (b), say so in one line. Either way
the probe is repeated and its usage logged before G3.6 starts.

## Ask 2 — the previous turn broke the G0 verifier's item count (section 6 item 13)

The G0 check `verify_on_machine_resolved` (`scripts/verify_run.py`, pre-registration
threshold `verify_on_machine_items_total: 8`) counts the numbered items of
`docs/EVIDENCE_TOOLING.md` section 11 and passes only on **exactly 8**. The previous turn
(commit b0442cf) appended the probe observation as a new numbered **item 9**, so at HEAD the
check reads 9 ≠ 8, `tests/unit/test_verify_run.py::test_verify_on_machine_check_reads_real_document`
fails, and `verify_run.py --gate G0` no longer passes on the current tree. That turn's
ledger entry reported 444 passed because its test run preceded the document edit; I found
it this turn and recorded it as a failure. This turn's own observation was appended
**inside** item 9 (an extension paragraph, count unchanged), not as item 10.

I cannot fix it: the evidence documents are additions-only (item 13) and the verifier is
the G0 ruler (C2). Options, your choice:

- **(i)** authorise a structural, content-preserving edit: turn the line `9. The headless
  CLI's failure shape …` into an unnumbered `**Addendum (2026-09-04) — …**` paragraph at the
  end of section 11, no words removed, count back to 8; or
- **(ii)** accept the discrepancy: the G0 verdict stands at its graded commit 72edbae, the
  unit test is changed to pin "9 at HEAD, 8 at grading" explicitly, and the referee is told.

Default if you answer Ask 1 without Ask 2: (ii), because it is the option that changes no
evidence entry.

## Defaults I am taking without asking (recorded in the ledger)

- The provisional caps (40 calls / 1200 s) stay for all three pre-flight game-runs so that
  the three share one config hash as `cost_preflight.measurement` requires. After the first
  complete run I report the observed per-call wall-clock distribution in the ledger. If you
  then change the caps, the new config starts a successor set under
  `cost_preflight.preflight_runs_are_graded`; runs already made stay preserved and listed.
- `model_wallclock_seconds_total` is in `results.json` (declared nondeterministic by the G3
  pre-registration's `model_calls.nondeterminism_protocol`) and not in `metrics.csv`.
- Model identifier stays `claude-fable-5-1`; no other identifier is probed until you name one.

Nothing under `artifacts/E300_ref/` exists and nothing will be created before this is answered.
