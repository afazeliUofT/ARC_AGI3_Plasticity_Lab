# G3b graded set: the run recipe

Written 2026-09-05 (G3.6b step 17). This is the operating procedure for the 25-game graded
set pre-registered in the G3b pre-registration (`thresholds.experiment_id` E304_ref, sha256
99a01908... at authoring; the verifier prints both digests in its
`successor_preregistration_overlay` check). Every number below is either read from that
pre-registration at run time by the scripts named here or is a bookkeeping choice the
pre-registration fixes in words. Nothing here moves a threshold.

## Step-to-script map (audit of 2026-09-05, G3.6b step 20)

Every step below is performed either by a named script (every threshold it applies is read
from the G3b pre-registration through `load_preregistration`) or by the turn's own hand,
which means a ledger entry, a state-file update, `state/ESCALATION.md`, or a commit. No
step is performed by the model reasoning about numbers: the hand-written items only copy
what a script printed.

| Step | Section | Performed by | Exit codes |
|---|---|---|---|
| Earliest-start check | When | `scripts/g3_next_job.py` (refuses before `earliest_start_local`) | 2 = refused |
| Pause on a usage-limit signal | When | the supervisor (no job is queued while it sleeps); the turn writes a `decision` ledger entry "waiting for the reset" by hand | - |
| Choose the next game in order | Order | `scripts/g3_next_job.py` (first stem without a completed E304_ref run) | 2 = none or refused |
| Attempt numbering and the rerun allowance | Order | `scripts/g3_next_job.py` (`failed_reruns_per_game_max`) | 2 = allowance spent |
| Config digest check before queueing | One job per turn | `scripts/g3_next_job.py` (`graded_config_sha256`) | 2 = mismatch |
| Write `state/job_request.json` | One job per turn | `scripts/g3_next_job.py` (`--dry-run` writes nothing) | 0 = written |
| Ledger `attempt` entry for the queue | One job per turn | hand-written, citing the script's printed lines | - |
| Read the job result and locate the run | After every run, item 1 | `scripts/g3_record_run.py` | 1 = no result |
| Verify the run independently of its summary | After every run, item 2 | `scripts/g3_record_run.py` (19 checks) | 0 = pass, 2 = failed run |
| Cumulative accounting and the escalate flag | After every run, item 3 | `scripts/g3_graded_set_accounting.py` (rewrites `state/BUDGET.json` `g3_graded_set`) | 0, 3 = escalate |
| Ledger `success`/`failure` entry, state update, commit | After every run, item 4 | hand-written, citing the two scripts' printed digests and numbers | - |
| Queue the next game | After every run, item 5 | `scripts/g3_next_job.py`, in a new turn | as above |
| Escalation under section 6 item 10 | Escalation rule | hand-written `state/ESCALATION.md`, `blocked_on`, `human_escalation` ledger entry, from the accounting script's printed numbers | - |
| Run-set manifest | Grading, item 1 | `scripts/build_e300_run_set.py --artifacts-root artifacts/E304_ref --output experiments/E304_ref_run_set.json` | 0 |
| Commit the manifest | Grading, item 2 | hand-written commit | - |
| Gate predicate | Grading, item 3 | `scripts/verify_run.py --gate G3` (read-only) | 0 = PASS |
| C5 arguments and the referee dispatch | Grading, item 4 | hand-written ledger entry, then the `referee` subagent | - |

Rehearsed read-only on 2026-09-05 before any E304_ref run exists (ledger success at
G3.6b step 20): `g3_record_run.py --job-id g36d-wa30-1` exit 2 with the same five
E303-vs-E304 failures as at step 19 and 14 passes (report sha256 a20dcca8...);
`g3_graded_set_accounting.py --dry-run` exit 0 with 0 runs and 25 remaining, escalate
False; `build_e300_run_set.py --artifacts-root artifacts/E304_ref --output /tmp/...` exit 0
with `runs_total` 0, `sets` empty and all 25 `stems_required` listed, so the builder accepts
the absent root and the graded set will fill it in order.

## When

- **Earliest start:** Friday 2026-09-11 17:00 local, the weekly allowance reset
  (`thresholds.earliest_start_local`; human budget directive, ledger 2026-09-05T19:19:50Z).
  No E304_ref job is queued before then. Until then all work is model-free.
- **Pause rule:** on a supervisor usage-limit signal (session or weekly) or a throttle
  refusal the set pauses. No job is queued until the window resets, no run is discarded, no
  partial set is graded. The set resumes with the next game in order under the same
  configuration; completed runs are never re-run (`graded_set.pause_rule`).

## Order

The alphabetical order of the `environment_files/` stems, which is also
`graded_set.games` in the pre-registration and the config's own order. Fixed in advance so
that no game can be chosen first after early scores are seen.

| # | stem | job id | # | stem | job id |
|---|---|---|---|---|---|
| 1 | ar25 | g37-ar25-1 | 14 | re86 | g37-re86-1 |
| 2 | bp35 | g37-bp35-1 | 15 | s5i5 | g37-s5i5-1 |
| 3 | cd82 | g37-cd82-1 | 16 | sb26 | g37-sb26-1 |
| 4 | cn04 | g37-cn04-1 | 17 | sc25 | g37-sc25-1 |
| 5 | dc22 | g37-dc22-1 | 18 | sk48 | g37-sk48-1 |
| 6 | ft09 | g37-ft09-1 | 19 | sp80 | g37-sp80-1 |
| 7 | g50t | g37-g50t-1 | 20 | su15 | g37-su15-1 |
| 8 | ka59 | g37-ka59-1 | 21 | tn36 | g37-tn36-1 |
| 9 | lf52 | g37-lf52-1 | 22 | tr87 | g37-tr87-1 |
| 10 | lp85 | g37-lp85-1 | 23 | tu93 | g37-tu93-1 |
| 11 | ls20 | g37-ls20-1 | 24 | vc33 | g37-vc33-1 |
| 12 | m0r0 | g37-m0r0-1 | 25 | wa30 | g37-wa30-1 |
| 13 | r11l | g37-r11l-1 | | | |

Job ids are `g37-<stem>-<attempt>`. Attempt 1 is the graded run. A second attempt for a
game is allowed only under `thresholds.failed_reruns_per_game_max` (1) for a run whose
`completion_status` is not `completed` (runner crash, supervisor kill), never for a completed
run with a poor score; record the reason in the ledger before queueing it.

## One job per turn

The launch route is the supervisor job (state/escalations/20260905T024724Z.md option A).
A turn never runs a game inside itself. The turn that queues a job writes the gitignored
`state/job_request.json`:

```json
{
  "id": "g37-ar25-1",
  "runner": "run_experiment",
  "config": "configs/experiments/E304_ref.yaml",
  "game": "ar25",
  "wallclock_limit_s": 10800
}
```

- `config` is E304_ref.yaml, whose sha256 must equal `thresholds.graded_config_sha256`
  (fd4ea9f5...); `scripts/g3_next_job.py` checks it before every queue and prints it; the
  hand-written ledger `attempt` entry records the printed digest.
- `wallclock_limit_s` is `thresholds.job_wallclock_limit_seconds` (10800). The config's own
  runner limit is `thresholds.wallclock_per_invocation_seconds` (9900), leaving the
  pre-registered 900 s margin for trace writing and SHA256SUMS
  (`thresholds.job_margin_over_runner_limit_seconds_min`; the E303 wa30 job overran a 300 s
  margin by 147 s).
- Exactly one job in flight (concurrency 1). The next job is queued only after the previous
  job's `state/jobs/<id>/result.json` has been read and its run recorded in the ledger.

The ledger `attempt` entry for a queue records: job id, game, config digest, the limit, the
UTC time read from `date -u`, and the cumulative accounting state at that moment.

### The mechanised queue step (G3.6b step 18)

`scripts/g3_next_job.py` performs this section by script. It reads the games list, the
experiment id, the graded config digest, the two wall-clock limits and their margin, the
rerun allowance and the earliest local start from the G3b pre-registration through
`load_preregistration`, chooses the first game in order without a completed run under
`artifacts/E304_ref/` (attempt number 1 + earlier runs for that game, capped by
`failed_reruns_per_game_max`), and refuses with exit 2 and a printed reason when the local
time is before `earliest_start_local` (both times printed), the config digest differs, the
runner limit plus margin exceeds the job limit, a request is already pending, a job is in
flight, or the job id already has a directory under `state/jobs/`. Otherwise it writes the
request above.

```bash
uv run python scripts/g3_next_job.py --dry-run   # print the request, write nothing
uv run python scripts/g3_next_job.py             # write state/job_request.json
```

The ledger `attempt` entry still has to be written by the turn that queues; the script's
printed lines (pre-registration digest, config digest, local time, runs seen) are what it
cites.

## After every run: record, then account

1. Read `state/jobs/<id>/result.json` (rc, timed_out, wallclock_s, model_seconds_charged,
   model_seconds_source) and the run under `artifacts/E304_ref/<run_id>/`.
2. Verify the run independently of its own summary: `sha256sum -c SHA256SUMS` inside the run
   directory, `results.json` `config_file_sha256` equals the graded config digest, the
   manifest's `prompt_hash` equals `thresholds.prompt_hash`, `stderr.log` empty or explained,
   `completion_status` completed.
   ### The mechanised record step (G3.6b step 19)

   `scripts/g3_record_run.py` performs items 1 and 2 by script. Given a job id (default:
   the newest `state/jobs/<id>/` with a `result.json`), it reads the job result, locates the
   run directory from `model_seconds_source` (or `stdout_tail`), and checks, with every
   threshold read from the G3b pre-registration through `load_preregistration`: return code
   0 and no time-out, the job's `wallclock_s` within `job_wallclock_limit_seconds`, the
   request naming the graded config, every `SHA256SUMS` entry recomputed with hashlib,
   `config_file_sha256` equal to `graded_config_sha256`, `experiment_id`, `prompt_hash` in
   both manifest and results, the manifest's `wallclock_limit_seconds` equal to
   `wallclock_per_invocation_seconds`, `completion_status` completed, `stderr.log` empty
   (else its first lines are printed), `model_wallclock_seconds_total` at most
   `model_wallclock_per_run_seconds` plus the config's `model_client.call_wallclock_seconds`,
   `model_calls` at most `calls_per_run_max`, `resumptions` at most `resumptions_used_max`,
   the pre-registered seed and the game in `graded_set.games`. It prints one line per check,
   the run summary (run id, game, stop reason, levels, RHAE, calls, model seconds) and the
   `results.json` and `SHA256SUMS` digests, and exits 0 when every check passes, 2 when any
   fails (the run is then labelled `failed` in the ledger and `g3_next_job.py` offers
   attempt 2), 1 on a usage error such as a job without a result.

   ```bash
   uv run python scripts/g3_record_run.py --job-id g37-ar25-1 --json /tmp/g3_record_run.json
   ```

   Validated on the E303 wa30 job before any E304 run existed: it failed exactly the five
   checks that distinguish an E303 run from an E304 one (job overrun, config path, config
   digest, experiment id, runner limit) and passed the other fourteen.

3. Run the accounting script. It reads every deciding parameter from the G3b pre-registration
   through `load_preregistration`, reuses the E303 per-run reader, and rewrites the
   `g3_graded_set` key of `state/BUDGET.json` while keeping every other key:

   ```bash
   uv run python scripts/g3_graded_set_accounting.py
   ```

   It prints the per-set summary and exits 0, or **3 when the escalate flag is set**. Use
   `--dry-run` to look without writing. The section it writes carries, per run: run id, game,
   stop_reason, model_wallclock_seconds_total, model_calls, the supervisor's charged seconds,
   tokens by kind, the USD equivalent at the G3 pre-flight prices (10 / 50 / 0.25 / 12.50 USD
   per million input / output / cache-read / cache-creation tokens), the results.json and
   SHA256SUMS digests; and for the set: cumulative totals, the linear projection to 25 runs,
   the games remaining, and the two flags.
4. **Hand-written.** Write the ledger `success` (or `failure`, when `g3_record_run.py`
   exited 2) entry citing the run directory, its results.json digest, the job result and
   the accounting numbers, all copied from the two scripts' printed lines. Update
   `state/PROJECT_STATE.json`. Commit with the staging recipe
   `git add -A && git reset -q -- state/ "fix_job_runner.sh:Zone.Identifier" && git add state/LEDGER.jsonl state/PROJECT_STATE.json state/BUDGET.json`
   (the job files under `state/jobs/` are gitignored and stay on disk; the stray
   `Zone.Identifier` file is a Windows download marker, never committed).
5. Only then queue the next game in order (a new turn, `scripts/g3_next_job.py`).

## Escalation rule

`graded_set.cost_accounting`: if the cumulative model time (the sum of the runs'
`model_wallclock_seconds_total`) exceeds `thresholds.set_model_seconds_escalate_above`
(60000 s) before the set is complete, escalate under constitution section 6 item 10 before
any further job. **Hand-written:** write `state/ESCALATION.md` with the accounting
section's numbers (copied from `state/BUDGET.json` `g3_graded_set` as the script wrote
it), set `blocked_on`, append a `human_escalation` ledger entry, and stop. The script's exit code 3
and its `escalate: True` line are the trigger; `hard_bound_exceeded` (90000 s) is the
pre-registered ceiling the set may never pass. The set does not stop by itself for a low
score: a complete set below the RHAE threshold is the pre-registered finding, and an
incomplete set is nothing.

## Grading

When all 25 games have a completed attempt:

1. Build the run-set manifest the pre-registration requires
   (`graded_experiment.run_set_manifest`, file `experiments/E304_ref_run_set.json`). The
   builder lists every directory under the root mechanically, so no run can be chosen or
   dropped by hand; its rule is unchanged from G3.yaml and the experiment id defaults to the
   root's name, so no `--experiment-id` is passed:

   ```bash
   uv run python scripts/build_e300_run_set.py --artifacts-root artifacts/E304_ref --output experiments/E304_ref_run_set.json
   ```

   It prints `runs=<n> sets=[...] complete_sets=[...]` to stderr; the set is gradable only
   when `complete_sets` names a set with exactly one graded run per stem for all 25 stems.
2. **Hand-written.** Commit `experiments/E304_ref_run_set.json` (with the ledger and state)
   *before* the verifier is invoked; the verifier's `run_set_manifest` check recomputes the
   manifest from the directories and compares it with the committed file.
3. Run the verifier read-only:

   ```bash
   uv run python scripts/verify_run.py --gate G3
   ```

   Its artifacts root defaults to `artifacts/E304_ref/` and it grades the highest-numbered
   complete set.
4. **Hand-written.** Apply C5 (the three strongest artifact arguments in the ledger, the
   strongest tested), set `gate_status` to `awaiting_verdict`, and dispatch the referee.

The diagnostic runs under E300 to E303 are excluded from grading
(`thresholds.diagnostic_runs_excluded` 11) and are never moved or deleted.
