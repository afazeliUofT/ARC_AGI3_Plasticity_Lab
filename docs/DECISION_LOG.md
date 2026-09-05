# Decision log

Route changes and other first-class decisions, in the order they were taken (constitution
section 5, "Route changes are first-class"). Every entry names the ledger record that carries
the full text and the artifacts it rests on. Gate verdicts live in `docs/decisions/` and are
not repeated here.

## 2026-09-05T08:20:01Z — G3: diagnostic set before the graded set (route change, not a KILL)

**Decided by:** the human, in the `## ANSWER` section of the cost pre-flight escalation
(`state/escalations/20260905T082003Z.md`, sha256
adcbf87055f6a1e063eace6558d9d24b620b0e695c84917823deab42776f08d7). Ledger `route_change`
entry at 2026-09-05T08:20:01Z; agent's defaults in the `decision` entry at 2026-09-05T08:22:34Z.

**Route abandoned:** the 25-game graded E301_ref set immediately after the cost pre-flight
(section 5 item 4 of the escalation, projected 124.53 USD equivalent and about 21 h).

**Route taken:** the same three games (cd82, s5i5, wa30) run once more under the successor
configuration `configs/experiments/E301_ref.yaml` as a **diagnostic** set: preserved, listed,
never graded, not part of any run set. Task id `G3.6b`.

**Why:** all three pre-flight runs scored RHAE 0.0 with 0 of 23 levels; only cd82 was
budget-truncated, s5i5 stopped on its action budget and wa30 on the runner's wall-clock with
model budget unspent, so the raised cap cannot explain the zeros. wa30 certified 10 of 11
hypotheses yet 322 plan searches all returned `not_found`. Reproducing that 25 times would be a
slow fail.

**Question the diagnostic must answer, with evidence in the ledger:** why did the plan searches
return `not_found` while hypotheses were certified? Distinguish (a) node or depth budget
exhausted (20000 / 8), (b) goal unreachable under the certified model, (c) goal mis-specified,
(d) certified hypothesis true but useless for planning. For a sample of failed searches record
what the planner was given, what it expanded, and why it stopped.

**Decision rule for what follows (human's, hash-committed here before any diagnostic run):**
proceed to the 25-game graded set only if EITHER at least one level is completed on at least
one of the three diagnostic runs, OR the diagnosis names a specific, testable defect together
with the change that would fix it. If neither holds: do not run the graded set; dispatch
`retrospective` (section 5 L4) on whether REF as designed can reach the inherited 55.0
threshold at all, and escalate its route recommendation to the human.

**Unchanged (items 1, 2, 3, 5, 6, 7 accepted as proposed):** per-run model cap 2400 s,
`calls_per_run_max` 40, successor `wallclock_limit_seconds` 10500 under the supervisor's
10800 s job kill, `E301_ref` / `preregistration/G3b.yaml`, no history window, claude-fable-5-1
at effort high, sandbox and planner limits unchanged. G3.yaml is not amended; 55.0 and 0.95 are
inherited. The three E300_ref pre-flight runs stay preserved, listed, never graded.

**Cost finding carried, not acted on:** cache_creation 510669 tokens against cache_read 0 over
all 24 pre-flight calls (each `claude -p` is a fresh non-persistent session); about 6.38 of the
14.94 USD equivalent bought cache that was never read. Prompt caching is a REF design change and
waits for the diagnostic's outcome.

**Preliminary reading of the existing artifacts (agent, 2026-09-05T08:22:34Z, script over
`plans.jsonl`, no new run):** every one of the 513 pre-flight searches (96 cd82, 95 s5i5, 322
wa30) ended with outcome `not_found` and reason `null`, which in `plan_to_next_level` means the
BFS queue emptied; no search ended on `node_limit`, `deadline`, `simulation_budget_exhausted`
or `model_error`. Maximum nodes expanded per search was 484 (wa30), 209 (cd82), 66 (s5i5)
against `max_nodes` 20000. Candidate (a) is therefore refuted for the node budget before the
diagnostic runs; the depth cap of 8 cannot be separated from a closed reachable set (b or d)
because the planner does not record how many successors it dropped at the depth cap versus
de-duplicated. That is the instrumentation the diagnostic adds.
