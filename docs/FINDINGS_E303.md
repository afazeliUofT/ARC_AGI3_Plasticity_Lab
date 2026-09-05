# Finding: what the E303_ref diagnostic set established (G3.6b, 2026-09-05)

**Status.** Diagnostic finding, never graded. The ten runs below (E300_ref pre-flight, E301_ref
diagnostic set, E302_ref F1 validation, E303_ref F2/F3 validation) are preserved under
`artifacts/` and listed here; none of them is part of any G3 run set and no gate predicate
has been evaluated on them. Written under the human budget directive of 2026-09-05T19:19:50Z
(ledger `decision`, item 2) before `preregistration/G3b.yaml` is authored and before the graded
25-game set, which starts after the weekly reset on Friday 2026-09-11 17:00 local.

**Method.** Every number in this document is derived from the run artifacts by
`scripts/g36b_e303_summary.py` (sha256
`a17a3b957f5042f090235d49957fa6eb88253ca470dbd01fc72d7b09903e68cc`), whose full JSON report is
committed as `docs/FINDINGS_E303_summary.json` (sha256
`a98339d533a0fa6399c51940a77bc693b670aaf03257e3bbc5c494e73efab9be`). Section 7 lists the SHA-256
of every cited file per run (C4). The prices behind the USD-equivalent figures are the
pre-registered list prices in `scripts/g36_preflight_totals.py` (input 10, output 50,
cache read 0.25, cache creation 12.5 USD per million tokens); the "CLI" column is the sum of
`total_cost_usd` reported by the headless client per call. Reproduce with:

```bash
uv run python scripts/g36b_e303_summary.py --out /tmp/g36b_e303_summary.json
```

## 1. The four configurations, one variable apart at each step

| config | sha256 (prefix) | prompt_hash | differs from its predecessor by |
|---|---|---|---|
| `configs/experiments/E300_ref.yaml` | `4624ea0d` | `1df76ae2` | pre-flight configuration (model cap 1200 s, runner wall-clock 7200 s) |
| `configs/experiments/E301_ref.yaml` | `fe7f3319` | `1df76ae2` | model cap 2400 s, runner wall-clock 10500 s, planner instrumentation on |
| `configs/experiments/E302_ref.yaml` | `da84c695` | `ddeb01c5` | F1: the prompt requires an explicit, implemented level-completion conjecture (`# GOAL:` line plus code) |
| `configs/experiments/E303_ref.yaml` | `7d1506ce` | `ddeb01c5` | F2: `planner.click_grid_step` 16 -> 6 (16 -> 121 click points); F3: `planner.max_depth` 8 -> 16 |

The planner and world-model sources were unchanged across E301 to E303 (ledger success
entries of 2026-09-05T17:43:25Z, 18:41:37Z and 22:27:19Z re-verify `ref_planner` `90ebe3c9`,
`ref_world_model` `92a1086f`, `run_experiment` `106e3023`, `backtest` `7e09fefd`,
`interface` `97624aa1`, `history_encoding` `cb9a80fa` by `sha256sum` at each job's HEAD).
Every run used model `claude-fable-5-1`, effort `high`, seed 12345, `OperationMode.OFFLINE`.

## 2. Run table

Numbers from each run's `results.json`, `plans.jsonl` and `model_calls.jsonl` (digests in section 7).

| exp | game | run_id | stop_reason | levels | RHAE env | searches | found | plan actions | mismatches / compared | model s | run wall s | USD eq | USD CLI |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E300 | cd82 | `20260905T025114Z_seed12345_8fd63a5a` | model_budget_exhausted | 0/6 | 0.00 | 96 | 0 | 0 | 5 / 96 | 1200 | 1567 | 6.06 | 7.06 |
| E300 | s5i5 | `20260905T032217Z_seed12345_ee3b847e` | level_budget_exhausted | 0/8 | 0.00 | 95 | 0 | 0 | 4 / 96 | 282 | 427 | 1.96 | 2.42 |
| E300 | wa30 | `20260905T033303Z_seed12345_fd9e79ad` | wallclock | 0/9 | 0.00 | 322 | 0 | 0 | 9 / 323 | 621 | 7091 | 6.92 | 9.70 |
| E301 | cd82 | `20260905T083428Z_seed12345_68ed39d4` | level_budget_exhausted | 0/6 | 0.00 | 269 | 0 | 0 | 6 / 271 | 1438 | 6176 | 12.33 | 16.32 |
| E301 | s5i5 | `20260905T102715Z_seed12345_64491fb6` | level_budget_exhausted | 0/8 | 0.00 | 95 | 0 | 0 | 4 / 96 | 225 | 295 | 1.55 | 1.94 |
| E301 | wa30 | `20260905T103513Z_seed12345_1b898667` | level_budget_exhausted | 0/9 | 0.00 | 350 | 0 | 0 | 10 / 351 | 676 | 7990 | 7.40 | 10.36 |
| E302 | s5i5 | `20260905T131531Z_seed12345_d915c5ae` | level_budget_exhausted | 0/8 | 0.00 | 95 | 0 | 0 | 2 / 96 | 214 | 298 | 1.31 | 1.55 |
| E303 | s5i5 | `20260905T154536Z_seed12345_7b8f2b62` | level_budget_exhausted | 1/8 | 1.02 | 459 | 3 | 16 | 8 / 35 | 1418 | 6647 | 7.77 | 8.83 |
| E303 | cd82 | `20260905T174628Z_seed12345_460bd1b1` | model_budget_exhausted | 1/6 | 4.76 | 10 | 7 | 20 | 9 / 23 | 2400 | 3058 | 12.88 | 15.39 |
| E303 | wa30 | `20260905T191952Z_seed12345_4c6032fd` | wallclock | 0/9 | 0.00 | 29 | 1 | 5 | 5 / 32 | 968 | 10502 | 5.14 | 5.81 |

Totals (report keys `totals_before_e303` and `totals_by_experiment.E303_ref`):

| set | runs | searches | found | plan actions | levels | mismatches / compared | model s | USD eq | USD CLI |
|---|---|---|---|---|---|---|---|---|---|
| E300 + E301 + E302 | 7 | 1322 | 0 | 0 | 0 of 54 | 40 / 1329 (3.0 %) | 4655.9 | 37.54 | 49.35 |
| E303 | 3 | 498 | 11 | 41 | 2 of 23 | 22 / 90 (24.4 %) | 4785.7 | 25.79 | 30.03 |

## 3. Finding 1: an accurate but unplannable world model became a less accurate but planning one

**Before E303, no search ever found a plan.** Across the seven E300/E301/E302 runs, 1322 of
1322 plan searches returned `not_found` (`plans.jsonl` of each run; `plans_found 0` in the
report), 0 plan actions were issued, and 0 of 54 levels were completed. Yet the certified
programs predicted the next frame well: 40 mismatches in 1329 compared predictions
(`prediction_mismatches` / `predictions_compared` in each `results.json`). The G3.6b diagnosis of
2026-09-05T13:07:39Z (ledger `decision` kind `plan_diagnosis`, `docs/DECISION_LOG.md`) explains
why: every certified program copied `levels_completed` from its input, so the planner's goal
was unsatisfiable by construction. F1 (E302) made the programs carry a level-completion
conjecture; the s5i5 E302 run still found no plan because of two planner configuration defects,
F2 and F3 (ledger `failure` 2026-09-05T15:38:58Z, `docs/DECISION_LOG.md` same timestamp).

**Under E303, plans are found on all three games, executed, and refuted or confirmed on the
real game.** 11 of 498 searches found a plan, 11 plans were executed (41 planned actions), and
12 `decertified` records in the three `hypotheses.jsonl` files carry a `plan_index`, i.e. a
conjecture refuted by a prediction mismatch on a planned action with the observed frame as
counterexample (one of the 12, wa30 h007 at plan 28, is a shutdown artifact, see section 6).
Two levels were completed, both by a planned action: s5i5 level 1 at action index 33 (official
baseline 20, `rhae_level_score` 36.73, `level_accounting.json` `completion_action_indices [33]`)
and cd82 level 1 at action index 27 (official baseline 55, `rhae_level_score` 115.0, the
toolkit cap; `completion_action_indices [27]`). In both cases the completing action was the
last step of a found plan whose predicted frame did not match the real next frame (the real
frame is the next level's layout), so the completing conjecture was decertified at the
completing step: the F1 conjecture-refutation path, which is the intended mechanics.

**The price is prediction accuracy.** Per game, mismatches over compared predictions:

| game | E300 | E301 | E302 | E303 |
|---|---|---|---|---|
| cd82 | 5 / 96 (5.2 %) | 6 / 271 (2.2 %) | not run | 9 / 23 (39.1 %) |
| s5i5 | 4 / 96 (4.2 %) | 4 / 96 (4.2 %) | 2 / 96 (2.1 %) | 8 / 35 (22.9 %) |
| wa30 | 9 / 323 (2.8 %) | 10 / 351 (2.8 %) | not run | 5 / 32 (15.6 %) |

The denominators are not comparable in kind: before E303 the agent explored with the model
idle for most of the game (E301 cd82: 273 exploration actions out of 275), so most compared
predictions were on cheap, repeated exploration steps; under E303 the agent acts on plans and
each refuted plan ends a conjecture after a few actions, so the compared predictions are the
hard ones. The correct reading is not "the model got worse" but "the earlier accuracy was
measured on a goal-free model that never had to commit to a mechanism".

**Correction to the human directive's figures.** The directive of 2026-09-05T19:19:50Z quotes
"2 mismatches in 96" for the earlier model and "9 in 23" for E303 cd82. The 9 / 23 figure is
cd82 E303 (`results.json` `0bea7956...`). The 2 / 96 figure is the **s5i5 E302** run
(`results.json` `3d9dcb08...`), not a cd82 run; cd82's earlier runs read 5 / 96 (E300) and
6 / 271 (E301). The qualitative claim (accurate but unplannable, then less accurate but
planning) stands on all three games; the specific pair of numbers was cross-game.

**Generalisation of F2/F3 (directive item 1).** The fix produces executable plans on 3 of 3
games and level completions on 2 of 3. On wa30 the single found plan came from the first
conjecture (h001, depth 5, 53 nodes), was refuted at its fifth action, and every later search
(27 of 29) hit the 20000-node cap; wa30 offers only ACTION1-5, so F2 (the click lattice) is
inert there and F3 alone converted E301's depth-capped searches (350 searches, max 484 nodes)
into node-capped ones (27 searches at 20000 nodes, about 100000 sandbox steps each). The
level-completion effect is therefore not universal; per-search planner cost is the next
binding constraint on that class of game.

## 4. Finding 2: the three games bind on three different limits

From `results.json` (`stop_reason`, `model_budget_binding`, `model_wallclock_seconds_total`,
`simulation_budget`), `manifest.json` (`wallclock_limit_seconds`) and `plans.jsonl`
(`nodes_expanded`), E303_ref runs:

| game | stop_reason | binding limit | model s / cap | sim steps / 5M | run wall s / 10500 | max nodes / 20000 | actions used / budget |
|---|---|---|---|---|---|---|---|
| s5i5 | level_budget_exhausted | simulation budget (5M steps) | 1418 / 2400 | 5000000 / 5000000 | 6647 | 11769 | 478 (level 1: 33 of 100; level 2: 445 of 445) |
| cd82 | model_budget_exhausted | per-run model cap (2400 s) | 2400 / 2400 | 247011 / 5000000 | 3058 | 995 | 27 / 855 |
| wa30 | wallclock | runner wall-clock (10500 s) | 968 / 2400 | 2772595 / 5000000 | 10502 | 20000 | 37 / 9215 |

- **s5i5:** after level 1 the seven level-2 searches consumed 4.58M of the 5M simulation steps
  (all `not_found`, predicted level never 2); the budget ran out inside plan 22, the remaining
  436 searches were refused with zero steps (`plan_outcomes.simulation_budget_exhausted 437`),
  and the agent explored randomly for 438 actions with the model idle and the certified
  program h010 never refuted. The model spent 1418 of 2400 s.
- **cd82:** the whole 2400 s of model time bought level 1 (nine conjectures, seven found
  plans, six refuted before h009 held for four steps and completed the level at its fifth).
  The tenth call (a revise at history 27) received the cap's remaining 243.66 s as its
  per-request wall-clock, timed out (`model_calls.jsonl` call 10: `exit_code -1`,
  `program_returned false`), the budget read consumed, and the run stopped at action 27 of 855
  with level 2 never attempted. Per-call wall-clock ranged 60 to 666 s and grew with history
  (revise calls at history 17 to 27 cost 180 to 666 s each). **This is the binding constraint on
  the science:** the run was truncated while succeeding, and every later level scores 0 because
  `model_budget_exhausted` ends the game instead of falling back to exploration.
- **wa30:** 9533 s of the 10501 s run were planner time (2.77M sandbox steps, about 3.4 ms
  per step, about 340 s per node-capped search); the level-1 action budget was 90 % unused
  (37 of 355) and the model cap 60 % unused when the runner stopped itself.

None of the three caps was chosen with these regimes in mind; each was a pre-flight default.

## 5. Finding 3: cost per run and the job wall-clock overrun

From `model_calls.jsonl` (`tokens_by_kind`, `total_cost_usd`) and the supervisor's gitignored
`state/jobs/<id>/result.json`:

| game | calls | calls without program | tokens (cache_creation / cache_read / input / output) | USD eq | USD CLI | job wall s | job limit s | charged model s |
|---|---|---|---|---|---|---|---|---|
| s5i5 | 10 | 0 | 128944 / 0 / 20 / 123220 | 7.77 | 8.83 | 6923 | 10800 | 1417 |
| cd82 | 10 | 1 | 299643 / 0 / 18 / 182716 | 12.88 | 15.39 | 3193 | 10800 | 2400 |
| wa30 | 7 | 0 | 82706 / 0 / 14 / 82106 | 5.14 | 5.81 | 10947 | 10800 | 968 |

- `cache_read` is 0 on all 27 calls of the set, as on the 24 pre-flight calls: no prompt
  caching is taking effect through the headless client, so every call pays cache-creation
  price on its full history prompt (prompts up to 19 KB on wa30, 208 KB on E301 cd82).
- The wa30 job ran 147 s **over** its `wallclock_limit_s` of 10800 without being killed: the
  runner stopped itself at 10501.5 s and then wrote 200261 `plan_traces.jsonl` records and
  `SHA256SUMS`. A G3b job request needs a margin well above 300 s over the runner's own limit,
  or a smaller trace sample, or both.
- Three-run total: 4785.7 s of model time, 25.79 USD equivalent (30.03 USD CLI). The human's
  directive states the weekly allowance was 64 % consumed at 13 % elapsed when wa30 started;
  no denominator exists for a fraction (`state/BUDGET.json` `g3_preflight.denominator_source`).

## 6. Notes for the referee and for the G3b pre-registration

What `preregistration/G3b.yaml` must fix knowingly, because each decided a run's outcome here:

1. **Per-run model cap** (`spend_control.model_wallclock_per_run_seconds`, 2400 s): binding on
   cd82 while levels were being completed. Whether `model_budget_exhausted` ends the game or
   falls back to exploration is a pre-registration choice, not a patch; both semantics are
   defensible and the choice changes the RHAE of every later level.
2. **Per-game simulation budget** (5M steps) and the absence of a **per-search** step cap:
   binding on s5i5, where seven searches consumed 92 % of the budget and the rest of the game
   was refused planning.
3. **Node cap** (20000) and per-search cost: on wa30 a capped search costs about 340 s, and
   27 of them consumed the runner's wall-clock. A per-search time or step cap, or object-centred
   click candidates (the L1 alternative named in `docs/DECISION_LOG.md` 2026-09-05T15:38:58Z),
   are the options; neither is taken by this document.
4. **Runner wall-clock** (10500 s) and the **job margin**: see section 5.
5. **Stop-reason semantics** and the level-accounting rule under each stop reason must be stated
   in the pre-registration so the referee can check them against `results.json`.

Observations the referee should see without re-deriving them:

- The wa30 `hypotheses.jsonl` carries a `decertified` record for h007 with `plan_index 28` whose
  reason is `WallclockExceededError` from the shutdown of the last search, not a prediction
  mismatch. The script counts it among the 12 decertifications on planned actions; the honest
  count of refutations by counterexample is 11.
- `manifest.json` records `git_dirty true` on every supervisor-job run because the supervisor
  rewrites `state/PROJECT_STATE.json` (trailing newline) while a job runs, and on later runs
  the human's stray `fix_job_runner.sh:Zone.Identifier` file is present; each run's
  `git_state.txt` lists exactly those paths.
- E302 and E303 share `prompt_hash` `ddeb01c5`; E303 differs from E302 by the three config
  lines named in section 1 and nothing else (verified by diff at step 8, ledger attempt
  2026-09-05T15:45:00Z).
- cd82's `rhae_environment_score` 4.76 with a level-1 score of 115.0 is the toolkit's
  behaviour, not an accounting error: `arc_agi.scorecard.EnvironmentScoreCalculator.to_score`
  caps the weighted mean at `max_weights / total_weights * 100`, i.e. 1/21 * 100 = 4.76 for one
  of six levels with weights `w_l = l`. The project does not reimplement RHAE.
- Single seed (12345), one run per game per configuration, one model: none of the differences
  above carries a variance estimate. The E303 set is a diagnostic existence result (plans are
  found and executed; levels complete on two games), not an effect size.
- The level completions were achieved by conjectures that were wrong about the completing
  transition (both decertified at the completing step). The mechanism completes levels by
  acting on a good-enough model, not by predicting the level change correctly.

## 7. Cited files and digests

`sha256sum` at the time of writing (report `docs/FINDINGS_E303_summary.json`, key `runs[].sha256`).

**`artifacts/E300_ref/20260905T025114Z_seed12345_8fd63a5a`** (E300_ref, cd82, config `4624ea0d`, prompt `1df76ae2`, git `ba4d14d` dirty True)

| file | sha256 |
|---|---|
| results.json | `b2ac683b3657d04d61521ee048091ab9b92db84ca5636a7e8889dea4a9d6e7d7` |
| manifest.json | `c244eefbcb6d5f51cc47ef8ab0c2058b27c31c5dda9eac5b7c545931ed56dee2` |
| plans.jsonl | `d6584389bb1fa0b224fc7b4cd375c4f5ee33c4112f47cf52f19024706705664b` |
| hypotheses.jsonl | `20cef811ecfa3a90b5dbdc3e52480849940b8df24dc9b2ac3c96d5b796d577b0` |
| transitions.jsonl | `15f3d342c496baa6f91113de6b44a508a784d13a89480fa732ba093b96b5e3ea` |
| model_calls.jsonl | `8d00d031fac479a042c92ac7758085190e3be977565f3252bb9b8d5c95c9472e` |
| level_accounting.json | `cd8f97882a254ac01512ab86343bf6bec067550512832257727ac210be15526d` |
| rhae.json | `5a45cd5848b16af1bcdcc928a3f600902ffa1c4f9cafb1e14e9a84f76d142768` |
| SHA256SUMS | `dfd5e2247ff1ffe13630efe05dcb14d046e78a8e6b9058b4eab5f45063fa40bf` |

**`artifacts/E300_ref/20260905T032217Z_seed12345_ee3b847e`** (E300_ref, s5i5, config `4624ea0d`, prompt `1df76ae2`, git `a06c1a9` dirty True)

| file | sha256 |
|---|---|
| results.json | `937787880a2f9be33ac50a96cc3b9c571969224bf0d9c305d7653efd4421b1a3` |
| manifest.json | `4278de0bbeaa7c960ff68328d31df4fab2283308b2eead10c597b8298bf5b419` |
| plans.jsonl | `a8fa81ba44b87735d6055a373324711be50db07b52ce024f27054435fb9e0a40` |
| hypotheses.jsonl | `01b26cc905ea9650013df2b15b237835e3c25c4a68989111fa9d4c8dbf1fc607` |
| transitions.jsonl | `874836b69d2518fe2034bd1fa07c28efe40e21972d4ebb796e16f52ffe9ccdff` |
| model_calls.jsonl | `f215a3fb3e5d3e3c17445550d952b2d5bbc31df20512c98265fe5c2d02c8db87` |
| level_accounting.json | `d813f6f74055feff6aeee19d74f80ee2697acb71508bfeaee474dd85d985ffea` |
| rhae.json | `2fd8ca96a10733f01342725997bc0d21c2fd483a9565dab9ca828cbbdb5eb404` |
| SHA256SUMS | `663d8b528a9e56d5377a35e55bbbf97565fbb31619aa174b81d0c8a418d4af98` |

**`artifacts/E300_ref/20260905T033303Z_seed12345_fd9e79ad`** (E300_ref, wa30, config `4624ea0d`, prompt `1df76ae2`, git `54d3bd0` dirty True)

| file | sha256 |
|---|---|
| results.json | `0d7c14d60d909e7c43cf44854ac4efda36795ba5fceffdd94ec37aeaac175193` |
| manifest.json | `9c7a8351f210a8a53407421beff74e2b6f29974dbad134ed58e83b91795992ee` |
| plans.jsonl | `03990070bab4a1a650210a71d203debeed4ab8395e62a13f8b3b4becab6c038d` |
| hypotheses.jsonl | `a80b72e9a88422d4a7e83804994d504039b64064fb1151e1905c900bae27ec7b` |
| transitions.jsonl | `4ebf7cece0cea91f4269d225146d93cc6941d49216666ffb66ff0c2e5a489857` |
| model_calls.jsonl | `1f466ec6ffe1aff67f0ab950c998bf095867407cbd4ea38328c3553212360eb2` |
| level_accounting.json | `be8a1922550613bde586900ebdce6c869493a5efc6b2bacba54d60b4bbc3ac83` |
| rhae.json | `07ac3b1b0ccf2ae0100da1c38a033ddceb0d2e89266c8f9b8946b62963ec598f` |
| SHA256SUMS | `b182fd67d87fee7820bc45022f0895be7e7bee4f1e2d34d92423306f69c59de2` |

**`artifacts/E301_ref/20260905T083428Z_seed12345_68ed39d4`** (E301_ref, cd82, config `fe7f3319`, prompt `1df76ae2`, git `fc774b4` dirty True)

| file | sha256 |
|---|---|
| results.json | `672a4f2edb9fdb41d9865613e27447ffee2a709a27639df514687526de52ad81` |
| manifest.json | `5bf7518d6db52c097e79b06e1e95334d827c080831647f1d57ca0538b6d2834c` |
| plans.jsonl | `1b32e80bec53baa54018b1fc926b79ea3b31eff5fb367958e34d807e4c5f583c` |
| hypotheses.jsonl | `a514494eb2e6ee9e4ca68c34f13c6be26ef694067a8ee4b3928129ad04b7a6d2` |
| transitions.jsonl | `a836f6bc2aab192ce4c6624ade66d46332db8e844754a599eaca64d533d8708b` |
| model_calls.jsonl | `a7b962101786cf59e44123616e8d17a1c856e28acf22a364f00fc47042e8f409` |
| level_accounting.json | `3d392177931b86198dbf54f3e6042b09cde093ecf0d30c8cabdeeda63ac3369f` |
| rhae.json | `d8e692941fb873792764898b267a6e10ac96e30260d4caed8c341f5064447eeb` |
| SHA256SUMS | `2ce0f307178ee9a4763a909a0a6d1f4a77a090b6c18f6f84f50aae8f9e229e38` |

**`artifacts/E301_ref/20260905T102715Z_seed12345_64491fb6`** (E301_ref, s5i5, config `fe7f3319`, prompt `1df76ae2`, git `979649d` dirty True)

| file | sha256 |
|---|---|
| results.json | `28bc68b97ff665d5a488615b6c38a4182900cc83be6c7eda079f71f6565b4a47` |
| manifest.json | `a6a5758e2bd722e27f084e8b7d4a7975cce6bd3ace09d9049f90dbf97fbc550a` |
| plans.jsonl | `b37b83b9b5647f53d867df309a5a30fbe4166ef59079734e60b1d7b2d259bbe9` |
| hypotheses.jsonl | `6809793d9f1a8c5372d5f159ade4d77a07c12f6d5a55042e538bf0490d583ab9` |
| transitions.jsonl | `decb928e93b9b67b4a6d0d0e36aecbcc1d1fcb5f63c88808c3fd18e8a9f8b464` |
| model_calls.jsonl | `f45dea2cff26767e024050acfcda275271ccfe3dbbb6b734cb8aed3be8e468aa` |
| level_accounting.json | `d813f6f74055feff6aeee19d74f80ee2697acb71508bfeaee474dd85d985ffea` |
| rhae.json | `2fd8ca96a10733f01342725997bc0d21c2fd483a9565dab9ca828cbbdb5eb404` |
| SHA256SUMS | `f54ccd408c889c5c800212087c982c59aae7125141ebf56319f2f0c7c0c1c2dc` |

**`artifacts/E301_ref/20260905T103513Z_seed12345_1b898667`** (E301_ref, wa30, config `fe7f3319`, prompt `1df76ae2`, git `2959d55` dirty True)

| file | sha256 |
|---|---|
| results.json | `42e9bd53c97eca26755333d80ccb8c4adba21439db6d359f9a11b6cf73b34e2e` |
| manifest.json | `7a075bc395c86f85900b9ab13705c8dfc1a67e94610da2590ea4f2439dce5efd` |
| plans.jsonl | `483be67e188a0235f73470f39eb07f11607363394add3d91fa2023c6386c1827` |
| hypotheses.jsonl | `ab163012c9f3c4978f8eb06d7058c8ccfbf0a6ab6ebaabed3551b8302525e7c1` |
| transitions.jsonl | `dba9a995f44ad5deb1a93a3df51f38275cf1e5676a4bb62048202a06f1a42225` |
| model_calls.jsonl | `dc82aa05ee1637f160da947639343582c54ec6339c3e8d9e40f3dff92268e2e9` |
| level_accounting.json | `fa8ab4024dade33637b07c5d696834944c87280e23fc1070d3e73c91fe0d0bb7` |
| rhae.json | `18734ec130d6137d80f633e35b00d0d1c1bd863e9778535654671ccafc1c7eeb` |
| SHA256SUMS | `043c1865de566dd1b28c30830cf8fda46c83894e2d3d4c081650c06fc7eff1e0` |

**`artifacts/E302_ref/20260905T131531Z_seed12345_d915c5ae`** (E302_ref, s5i5, config `da84c695`, prompt `ddeb01c5`, git `0ce3e59` dirty True)

| file | sha256 |
|---|---|
| results.json | `3d9dcb08dbb87d3afd4d6afc1fa411bafd33126839166b1454d002f3679964fe` |
| manifest.json | `8c88771e5caba59640681713420cf7dc3f7275f38954fc9d5c6505a9d8f0b6b6` |
| plans.jsonl | `39888b734909831ae202f686fac8fbc4b1a6e5b5079e27558afe2d6a1e24e8c0` |
| hypotheses.jsonl | `58c2bbcfcdf55a96817eccc16211db6a2614f697297825ae2e3d095560b2ad76` |
| transitions.jsonl | `9eeafdf9be5ce05b88b169ef3de46a6ee038f31b6aef45a19c9fb01b8d8a3e04` |
| model_calls.jsonl | `e5aa885965b6dd9c2f8936ca802abc6b56013558dfb7394ac778c8718f60b197` |
| level_accounting.json | `d813f6f74055feff6aeee19d74f80ee2697acb71508bfeaee474dd85d985ffea` |
| rhae.json | `2fd8ca96a10733f01342725997bc0d21c2fd483a9565dab9ca828cbbdb5eb404` |
| SHA256SUMS | `286ac0789e7e1feb95cd10605621d2e5b668abb44a1d91e1e908929c857df174` |

**`artifacts/E303_ref/20260905T154536Z_seed12345_7b8f2b62`** (E303_ref, s5i5, config `7d1506ce`, prompt `ddeb01c5`, git `7e61961` dirty True)

| file | sha256 |
|---|---|
| results.json | `6d23f81e843d32817be5b74b6ebaa7c630cdba22f5927dde6f71997c918ee7cf` |
| manifest.json | `7790b6624bc46344f95f129adc7fab57e759a1263ea231bb7a6740ade4f79b09` |
| plans.jsonl | `669b92e3d510a0bd6f20465f51824a38a1c5e75ae875f999ad4df12611a2b7fb` |
| hypotheses.jsonl | `ec49fee8382f92647df8ee59845409a181d5b831c4bfebb60b72df9087c2b4bb` |
| transitions.jsonl | `e8cedd17dc6eb02f9e568eb6253affb53edf2e50253dee5fd00e0a37992260d7` |
| model_calls.jsonl | `7020d76e3b670560222605f70f3cc44c4381721da11da489c84306a04268b0e8` |
| level_accounting.json | `51e67febfc6a1d8f2af00856dde6655af8126f4a0c75652d757b34dd03a2b313` |
| rhae.json | `ef33e5a6944815e7bc3ea0632240d07f901d63511f38b38f55193412e97c8d6b` |
| SHA256SUMS | `4a51db1ca993da4aba7a4e60e3a8488c199f7712e71adb444c4f5dd3de341646` |

**`artifacts/E303_ref/20260905T174628Z_seed12345_460bd1b1`** (E303_ref, cd82, config `7d1506ce`, prompt `ddeb01c5`, git `de34d66` dirty True)

| file | sha256 |
|---|---|
| results.json | `0bea7956b615934e12007eca26b73f8a8482caf800c4be1bb836c4cf76b72f39` |
| manifest.json | `6c444ce51b6ee85ebcd271acbce4200f8d23c56aca691d0a4093653bbc3bd359` |
| plans.jsonl | `27fe8d22aeaffad0b167d96f2cb35846c08a910b90e70504ff1bd9f4d44989af` |
| hypotheses.jsonl | `e0f083967b2fd47ce12da658bd2d2edf9c06b432a74fa9791a1f62ba929d16dd` |
| transitions.jsonl | `1308e76043cc4ca396cfae4e91db30910a84f9914dab87290bb4a89c8f3367f8` |
| model_calls.jsonl | `cc23f5e5d4ee27a19f97d8430d9af97e475e9cd91c601735abc2801b614b47ae` |
| level_accounting.json | `b3327219cdb61f41fadc36e3d13bdca4a8db639091810dc0addb521562dd39c0` |
| rhae.json | `08dfecb646b4b36c9c0fb363d7b2e31eb8856900b2ada2f1b36f7a391034d96d` |
| SHA256SUMS | `9752f9a8bad02082d2a8d8bd6c5df1c4537353990d2f52bfa00fa7c7b0faf3e2` |

**`artifacts/E303_ref/20260905T191952Z_seed12345_4c6032fd`** (E303_ref, wa30, config `7d1506ce`, prompt `ddeb01c5`, git `cdd8976` dirty True)

| file | sha256 |
|---|---|
| results.json | `7725376f9849ef0704014bc4f54d1e2a36a7ff9e84913bc821c5625c833b5d46` |
| manifest.json | `c209f1c89497ffdde80def9aa81546e9cd7df0d3a0a97c359c82a38ef01d5d71` |
| plans.jsonl | `fd17ed3c82bb9319c5fd3cf1472e3ad66cebab55dfaaebd6cdda7c557e1e185a` |
| hypotheses.jsonl | `faeede65fc5e3b6231800ba717285040ca8ccacf93befe8492457f451fc5ab35` |
| transitions.jsonl | `c70ece5086a1092ebab17c57ceb4899b9d0b3f9798ebb681a0636f0dd56babea` |
| model_calls.jsonl | `8f82a471df2c141d5440d9e86dbadd0885adf7bbb27cfd993960370290a10645` |
| level_accounting.json | `de5f04e2709634149bac81f1de5002bede52eb787e927bc6260de18b3c53c9cb` |
| rhae.json | `0ba04fd8a29638f685be35915a84500f6edd24eb223c96e69f0cce2d2250791a` |
| SHA256SUMS | `44d6ff11f842244fe34ad41ab5e37d6b5a6e99461a1fc2adb46f42201d32c617` |

Configs: `configs/experiments/E300_ref.yaml`
`4624ea0d995745df362bf3d30e3dd2d16e0293dc8d1429380069585f9ca3d1d4`, `E301_ref.yaml`
`fe7f33197cbc913e5b82e2eab8fe959ee615dbe49352c9497da94cf38de73115`, `E302_ref.yaml`
`da84c695f65d0e96a8004177bc6bca8553f8b1d5462c38bbb4fb3ef661cf5cc9`, `E303_ref.yaml`
`7d1506ce076eadfefb2336e967155a30bcd69770cdbdf598d7d918fda82ff9ae`. Supervisor job results
(gitignored, digests not reproducible from a clone): `state/jobs/g36d-s5i5-1/result.json`,
`state/jobs/g36d-cd82-1/result.json`, `state/jobs/g36d-wa30-1/result.json`.
