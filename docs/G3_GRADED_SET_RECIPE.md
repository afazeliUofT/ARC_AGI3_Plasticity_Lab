# G3b graded set: the run recipe

Written 2026-09-05 (G3.6b step 17). This is the operating procedure for the 25-game graded
set pre-registered in the G3b pre-registration (`thresholds.experiment_id` E304_ref, sha256
99a01908... at authoring; the verifier prints both digests in its
`successor_preregistration_overlay` check). Every number below is either read from that
pre-registration at run time by the scripts named here or is a bookkeeping choice the
pre-registration fixes in words. Nothing here moves a threshold.

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
  (fd4ea9f5...); check it with `sha256sum` before every queue and record the digest in the
  ledger `attempt` entry.
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
4. Write the ledger `success` (or `failure`) entry citing the run directory, its
   results.json digest, the job result and the accounting numbers. Update
   `state/PROJECT_STATE.json`. Commit with the staging recipe
   `git add -A && git reset -q -- state/ && git add state/LEDGER.jsonl state/PROJECT_STATE.json state/BUDGET.json`
   (the job files under `state/jobs/` are gitignored and stay on disk).
5. Only then queue the next game in order (a new turn).

## Escalation rule

`graded_set.cost_accounting`: if the cumulative model time (the sum of the runs'
`model_wallclock_seconds_total`) exceeds `thresholds.set_model_seconds_escalate_above`
(60000 s) before the set is complete, escalate under constitution section 6 item 10 before
any further job: write `state/ESCALATION.md` with the accounting section's numbers, set
`blocked_on`, append a `human_escalation` ledger entry, and stop. The script's exit code 3
and its `escalate: True` line are the trigger; `hard_bound_exceeded` (90000 s) is the
pre-registered ceiling the set may never pass. The set does not stop by itself for a low
score: a complete set below the RHAE threshold is the pre-registered finding, and an
incomplete set is nothing.

## Grading

When all 25 games have a completed attempt, run the verifier read-only:

```bash
uv run python scripts/verify_run.py --gate G3
```

Its artifacts root defaults to `artifacts/E304_ref/`. Then apply C5 (three strongest
artifact arguments in the ledger, the strongest tested) and dispatch the referee. The
diagnostic runs under E300 to E303 are excluded from grading
(`thresholds.diagnostic_runs_excluded` 11) and are never moved or deleted.
