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

## 2026-09-05T13:07:39Z — G3.6b: diagnosis answered; F1 fix to be validated before any graded set

**Decided by:** the agent, applying the human's decision rule of 2026-09-05T08:20:01Z above.
Ledger `decision` entry (kind `plan_diagnosis`) at 2026-09-05T13:07:39Z; script
`scripts/g36b_plan_diagnosis.py` (sha256 `46218c01929e9412`), report
`/tmp/g36b_plan_diagnosis.json` (sha256 `2a3f98be359cb0b2`, every number below cites its source
file digest there).

**The question:** why did the plan searches return `not_found` while hypotheses were certified?

**The answer, over all six REF runs (three E300_ref pre-flight, three E301_ref diagnostic):**

| evidence | value |
|---|---|
| plan searches / `not_found` | 1227 / 1227 |
| instrumented searches with predicted `levels_completed` max 0 | 714 / 714 (plus 37909 trace records, all 0) |
| nodes expanded, max, against `max_nodes` 20000 | 583 |
| real transitions with `levels_completed` 0 | 1257 / 1257 (no level change ever observed) |
| proposed programs / certified | 46 / 43 |
| programs whose `predict` copies `levels_completed` from an input record | 45 (2 through a local name) |
| programs returning the literal 0 | 1 (s5i5 pre-flight h006, not certified) |
| programs computing a level change, or mentioning `WIN` | 0 |
| sandbox probe: predictions / programs ever exceeding their input's level | 1210 / 0 |
| deeper offline search, s5i5 h005, depth 24, 200000 nodes | 141 states, still 0 |

- **(a) node or depth budget:** refuted as the cause. The depth cap truncates the cd82 and wa30
  frontiers, but no depth reaches a goal region that is empty.
- **(b) goal unreachable under the certified model:** true, but derivative of (c) and (d).
- **(c) goal mis-specified:** yes, at the pipeline level. The planner's goal is stated on
  `levels_completed`; the induction prompt asks only that the history be reproduced, and the
  backtest can only constrain the field on a history in which it never changed. Nothing in REF
  asks for, rewards or can certify a hypothesis about what completes a level.
- **(d) true but useless:** yes. Every certified program is a valid retrodictive model of the
  frame dynamics with a constant level counter, so `predicted.levels_completed >= start + 1` is
  unsatisfiable at any depth by induction over the search tree.

**Root cause:** REF can only plan after random exploration has already completed level 1,
which it never did (0 levels in 1257 actions here; 1 in 75 game-runs in G1). A graded set of
REF as it stands would measure random exploration, not induction plus planning.

**The fix (F1):** a prompt-wording change, which the G3 pre-registration's
`reference_architecture.what_is_fixed_here` leaves changeable under the escalation ladder until
the first graded run of a set starts. Every program must state and implement an explicit
level-completion conjecture (a `# GOAL:` comment plus code that increments `levels_completed`
and sets the state when the conjectured condition is met, while still reproducing the history
exactly). Certification then carries a goal; the planner finds plans toward it;
predict-before-act refutes false conjectures on the real environment as prediction mismatches.
Testable prediction: `plans.jsonl` shows `found` with `plan_actions > 0` on the same three
games (currently 0 of 1227), and either a level completes or the conjectures are refuted with
counterexamples in `hypotheses.jsonl`.

**Decision rule applied:** prong 1 (a level completed) is not met: 0/6, 0/8, 0/9. Prong 2 (a
specific, testable defect with the change that fixes it) is met. **Default taken:** the graded
set is not queued on the unfixed REF, which would reproduce the zeros 25 times. F1 goes into a
successor `configs/experiments/E302_ref.yaml` (E301_ref stays byte-identical) and is validated
on the same three games as a second diagnostic set, s5i5 first (about 2 USD equivalent), then
cd82 and wa30 only if s5i5 shows a found plan. `preregistration/G3b.yaml` follows that
validation and precedes any graded run. If F1 yields no found plan on any of the three, the
rule's fall-back applies: `retrospective` (L4) and escalation of its recommendation.
## 2026-09-05T15:38:58Z — G3.6b step 7: F1 complied with, plan still not found; two planner defects (F2, F3) named and tested offline

**Run:** `artifacts/E302_ref/20260905T131531Z_seed12345_d915c5ae` (job g36c-s5i5-1, config `configs/experiments/E302_ref.yaml` da84c695,
manifest prompt_hash ddeb01c5, git 0ce3e59, `SHA256SUMS` 27/27 OK, stderr empty). Stop
`level_budget_exhausted` after 100 actions (99 exploration + 1 RESET, 0 plan actions), 3
calls all returning programs, 214.5 s of model time, 298.5 s wall-clock, 1.31 USD equivalent
(1.55 USD CLI total_cost_usd), levels 0/8, rhae 0.0.

**F1 (prompt) is complied with.** 3/3 programs begin with a `# GOAL:` line stating a
concrete condition (both piece heads on their diamond targets at (row 10, col 52) and
(row 52, col 10)), 3/3 implement it (`levels += 1` when `hx == H_TARGET and vy == V_TARGET`),
3/3 certified by the full-history backtest (0 mismatches at history 4 / 10 / 51). h001 and
h002 were decertified by predict-before-act (steps 10 and 51); h003 held for 49 searches.

**The found-plan test failed:** 95/95 searches `not_found`, `predicted_levels_completed_max`
0 in all, 84/95 reached depth 8 and dropped successors at the cap. Two planner defects
explain it, both read from the artifacts and both confirmed offline with
`scripts/g36b_plan_diagnosis.py --deep-search` over h003 from history prefix 51
(reports in /tmp, digests in the ledger):

| offline search over h003 (prefix 51) | click pitch | depth | outcome |
|---|---|---|---|
| planner's own limits | 16 (16 points) | 8 | not_found |
| deeper only | 16 | 16 | not_found (93 states) |
| denser only | 6 (121 points) | 8 | not_found, 70 dropped at cap |
| both | 6 | 16 | **found, 13 actions, predicted level 1**, 691 nodes, 83571 steps, 79 s |

- **F2, click lattice:** `click_points_for_step(16)` yields the 16 points (8+16i, 8+16j).
  Under all three programs' button geometry those points hit only the L button (40,24) and
  the U button (24,40), which move the heads toward their anchors and away from the targets;
  no point falls in the R (x 43-48, y 18-24) or D (x 21-27, y 42-47) regions. Pitch 6 hits all
  four buttons (pitch 8 misses D and U; pitch 12 misses all four).
- **F3, depth cap:** under the certified model the goal needs 7 R clicks (31 -> 52 in steps
  of 3) plus 6 D clicks (34 -> 52): 13 actions against `max_depth` 8. Every earlier run
  (cd82, wa30) also dropped successors at the cap.

Neither defect is prompt wording, so no E303 prompt revision. Neither is a hypothesis
failure: the induction side now produces certified, goal-bearing, planner-usable models.
Both are planner *configuration* values (`planner.click_grid_step`, `planner.max_depth`),
which the G3 pre-registration's `reference_architecture.what_is_fixed_here` leaves changeable
under the ladder until the first graded run of a set starts.

**Decision rule applied (docs/DECISION_LOG.md 2026-09-05T08:20:01Z):** prong 1 (a level
completed) not met: 0/8. Prong 2 (a specific testable defect and its fix) met, twice over,
with the fix already tested offline. **Default taken (L1, smallest corrective patch, no source
change):** a successor `configs/experiments/E303_ref.yaml` derived from E302_ref.yaml by
exactly three changes (experiment_id, `planner.max_depth` 8 -> 16, `planner.click_grid_step`
16 -> 6), validated on s5i5 first as job g36d-s5i5-1, then cd82 and wa30 only if s5i5 shows a
found plan. Testable prediction: `plans.jsonl` carries `found` records with `plan_actions > 0`
in results.json; then either level 1 completes on the real game or h00N is decertified by a
prediction mismatch on a planned action (a refuted conjecture, which F1 asks the model to
replace). Cost risk stated: 121 click points and depth 16 multiply the planner's branching
by 7.6 and its depth by 2; on open-state-space games (cd82, wa30) the node cap (20000), the
simulation budget (5M steps) or the runner's wall-clock limit (10500 s) will bind and that is
a measured result, not a defect. The principled alternative if the lattice fails there is
object-centred click candidates (connected components of the current frame), a planner source
change recorded here as the next rung, not taken now.

**Diagnosis-script limitation found:** the static classifier in
`scripts/g36b_plan_diagnosis.py` labels all three E302 programs
`copied_from_input_record` / `never computing levels` because they read
`history[-1]["levels_completed"]` into a local and then conditionally increment it; the
augmented assignment is not followed. The label is wrong for these programs (read directly:
`levels += 1` at h001.py:95, h002.py:98, h003.py:109). The sandbox probe is right (0
programs exceed their input's level on the *real* action history, whose clicks never
reached the targets). Fix candidate: a follow-up housekeeping step, not this turn.

---
