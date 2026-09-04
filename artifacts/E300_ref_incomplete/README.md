# Incomplete E300_ref runs (not graded)

One E300_ref game-run directory, `20260904T215745Z_seed12345_32580a64` (game cd82, seed 12345,
commit 3f68598, config_file_sha256 4624ea0d), moved out of `artifacts/E300_ref/` at
2026-09-04T22:01:26Z and preserved unchanged as the evidence for the ledger failure entry of
task G3.6 (kind `process_killed_at_turn_end`).

What happened: the previous supervisor turn launched the run as a background process of its
Bash tool at 21:57:45Z and ended at 21:58:34Z (state/supervisor.jsonl, turn elapsed 79 s,
committed false). The run wrote its resolved config, git state, environment info, the reset
line and four exploration transitions within one second of starting (last write to
`transitions.jsonl` 21:57:45.99Z), reached `induction_min_history` 4 and started its first
headless model call; that call was in flight when the turn's process tree was torn down. No
`manifest.json`, `results.json`, `metrics.csv`, `SHA256SUMS`, `model_calls.jsonl` or
`model_calls/` row exists because the runner writes those on completion, and `stderr.log` is
empty because the process was killed by a signal, not by an exception.

This settles the open question carried since G3.1: **a background process does not survive
the end of a supervisor turn.** An experiment launched from inside a turn must be waited on
by that turn until `run_experiment.py` exits.

Why it cannot be graded: no manifest, no results, no digests; `completion_status` was never
written. Its `config_file_sha256` is the graded set's value, so it must not sit under
`artifacts/E300_ref/`, which the G3.8 run-set evaluator scans.

Digests at the move (sha256): stdout.log 1170571f9b33a98ac191419af7f3f90b643638722f247b5f44dc73fcd965dfde,
transitions.jsonl fb4441222cfe1a8b9310f9825c815d8fa1cfbbb4532519ef948b2c001d2f9ddf,
resolved_config.yaml e4fc6c25c8c427cb391cdec5130d1a65db64164bf8d2b633f5efe2c994ffed74,
git_state.txt 8f2b23e37d8946749a70ed95447716ccd42cc73a3cd99b96c1c6c98c2c06cca8,
environment_info.json f220000d457b60e9516f165950e1c245d48e0259dffe86f8f9c767557e186d62.

No verifier scans this directory. Do not add runs here.
