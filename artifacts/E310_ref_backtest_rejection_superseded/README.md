# Superseded E310 runs (not graded)

Three complete E310_ref_backtest_rejection runs made on 2026-09-04 between 17:16:44Z and
17:18:14Z from commit 935b616 (runner `src/arc_plasticity/evaluation/backtest_rejection.py`
as committed there), moved out of `artifacts/E310_ref_backtest_rejection/` at
2026-09-04T17:22:53Z and preserved unchanged as the evidence for the ledger failure entry
of task G3.3.

Why they cannot be graded: `results.json["results"]["history_source"]["run_id"]` names the
G1 history run, but `run_id` is an excluded field (`configs/nondeterministic_fields.yaml`)
and the hash-locked G1 `exclusion_nesting_rule` (thresholds `excluded_key_max_depth` 1,
`excluded_key_container_values_allowed` false, restated in the G3 pre-registration) allows an
excluded name only at the top level of `results.json`. The G3 verifier's `exclusion_nesting`
check therefore fails on every one of these runs (depth 3). The values themselves are
deterministic; the rule is mechanical, and the runner was patched (key renamed to
`history_run_id`) rather than the rule bent.

Everything else about these runs reproduced the /tmp dry run recorded in the ledger: 25/25
replay identity, 250 wrong-model trials, 0 vacuous, 250 rejected, 25/25 controls accepted.

No verifier scans this directory. Do not add runs here.
