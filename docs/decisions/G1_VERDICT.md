# G1 Verdict: ARC-AGI-3 interface, determinism, offline operation

Referee: independent referee subagent (Claude Fable 5.1, effort max), read-only tools plus
`Write(docs/decisions/**)`. Issued 2026-09-04 (the referee read `date -u` 07:59:21Z during
grading; the graded commit was made at 07:56:59Z).

**Graded commit:** `1435f81977d6f94e68d30f026117c803c45fcc71` (branch `main`).
`git status --porcelain` was empty before and after every command the referee ran.

Verdict: GO

---

## 1. Governing documents, as verified

| Item | Path | SHA-256 (computed by the referee with `sha256sum`) |
|---|---|---|
| Pre-registration | `preregistration/G1.yaml` | `abaa4e99a1caad630d19f77e9804939a008d8748e4425ef7d4897c670f1d59ca` |
| Same file as the blob in commit 773f1a2 (`git show 773f1a2:preregistration/G1.yaml`) | | `abaa4e99a1caad630d19f77e9804939a008d8748e4425ef7d4897c670f1d59ca` |
| Verifier | `scripts/verify_run.py` | `7877341122122a821aaf13d3e474ca3d950c2fa756fc6035e4f5bbdba8b5aad1` |
| Same file as the blob in commit 6738f7a (`git show 6738f7a:scripts/verify_run.py`) | | `7877341122122a821aaf13d3e474ca3d950c2fa756fc6035e4f5bbdba8b5aad1` |
| Builder's verifier report | `state/verify_G1.json` | `19870d345c1ae2296eaf64c34b01035d1f173af411d684ff7d256b811a0a57c1` |
| Referee's own verifier report (written outside the repository) | `/tmp/referee_verify_G1.json` | `90d78dd75be3db864eda135d6b09e89875d23fd27162a456bac6aecd1a999947` |
| Environment cache manifest | `experiments/environment_cache_manifest.json` | `023726479a3c201161a61ee0d310b20696988933adbf1826dc9d7bd524d960af` |
| Experiment config | `configs/experiments/E100_arc_interface.yaml` | `9548496ad0e05b0ea005af5ccbd856833fbccc067074dd80d4a4267d828d3265` |
| Exclusion list | `configs/nondeterministic_fields.yaml` | `cd412e291aaf8689555f0884fd6507e1888ef97989a0b4eda7eaf77f145d0983` |
| Ledger at grading | `state/LEDGER.jsonl` | `caff1f71184c79c93b8c2e5de42fa8dffd5ea7f5befa9a1739937e6ce2f09daf` |
| Evidence base at grading | `docs/EVIDENCE_ARC.md` | `2e669d1c872d4780e16aa192f7f18032250d39cf78a330e69fc8a7c459621d61` |
| Pin file | `state/PINNED_HASHES.json` | `a79e4694153f1340c627e6bcfdcb4fd34b629a7ef5e42ac2726f65e445d1b499` |
| Predecessor verdict | `docs/decisions/G0_VERDICT.md` | `37ffb13b00f691febebd1ba0aba035de4f62810333ed6dbedc1c81f6e97d3ede` |

**C1 timing, from git, not from the ledger.** Commit 773f1a2 (2026-09-04 07:28:55Z) contains
exactly one file, `preregistration/G1.yaml` (391 insertions). `git ls-tree -r 773f1a2` and
`git ls-tree -r 6738f7a` (the last change to `scripts/verify_run.py`, 07:41:00Z) contain no
path under `artifacts/E100_arc_interface/`. The three runs were created 07:49:39Z, 07:49:56Z
and 07:50:00Z (manifest `timestamp_utc`) and first committed at 621983e (07:50:16Z), before
the first verifier report was committed at e589b96 (07:51:10Z). The pre-registration and the
verifier were therefore both fixed before any result existed, and neither has changed since.

---

## 2. Original hypothesis and pre-registered prediction

`preregistration/G1.yaml` states that G1 carries no scientific hypothesis. The claim under
test is that the official toolkit (`arc-agi` 0.9.9, `arcengine` 0.9.3) is pinned, the 25 public
games are cached with recorded hashes, a seeded run through the canonical entry point
completes offline under a socket guard, at least one game reaches a terminal state, every
recorded trajectory replays in a fresh process to an identical final frame, and the engine
sustains at least 500 frames per second on this machine.

Pre-registered thresholds that govern (26, all read by the verifier from the hash-locked
file): `arc_agi_locked_version "0.9.9"`, `cached_games_required 25`,
`cache_manifest_drift_files_max 0`, `network_calls_allowed 0`, `network_attempts_max 0`,
`model_calls_allowed 0`, `games_attempted_min 25`, `terminal_games_min 1`,
`step_failures_max 0`, `replay_final_frame_identity_min 1.0`, `replay_divergent_games_max 0`,
`throughput_fps_min 500.0`, `throughput_min_steps_measured 1000`,
`determinism_identity_min 1.0`, `contrast_seed_must_differ true`, `excluded_key_max_depth 1`,
`excluded_key_container_values_allowed false`, `sha256sums_verified_fraction_min 1.0`,
`sha256sums_must_list_every_artifact_file true`, `uv_sync_exit_code 0`, `pytest_exit_code 0`,
`pytest_min_tests_collected 1`, `ruff_exit_code 0`, `mypy_exit_code 0`,
`git_status_porcelain_lines_max 0`, `licence_required_text "MIT No Attribution"`.
Primary metric: `replay_final_frame_identity`, pass value 1.0 over every attempted game.
Mandated baselines: none. Revision limit: 0.

---

## 3. Experiments completed

Three runs of `E100_arc_interface` through
`uv run python scripts/run_experiment.py --config configs/experiments/E100_arc_interface.yaml`
(runner `arc_random_walk`, seeded uniform-random policy over `available_actions`, 5000
actions per game, 25 games, `OperationMode.OFFLINE`, `NetworkGuard(allowed_calls=0)`, zero
model calls, 1800 s limit): seed 12345 twice and seed 12346 once, per the G0 determinism
protocol carried into G1.

---

## 4. Raw artifacts, digests computed by the referee

`sha256sum -c SHA256SUMS` returned `OK` for all 13 listed files in each run directory (39/39).
Every directory holds exactly the 13 listed files plus `SHA256SUMS`; nothing is unlisted.

### Run A: `artifacts/E100_arc_interface/20260904T074939Z_seed12345_8383cad8/`

| File | SHA-256 |
|---|---|
| `SHA256SUMS` | `6db258830174e76b032943689552631a7b458ffe0f3fad97429af8e1b75e5190` |
| `results.json` | `2700036d38e78412a63030d4ef1979fc8396a0e18f2aadce9c872e0670ac05d0` |
| `transitions.jsonl` | `b09cde6f7168f573cd2f36b77d34cec02d149162658782258aa83a8d503fa1b3` |
| `metrics.csv` | `891f66ba706ddb1bb6d77edd7e3f6372d68b90ee4df06beaa5ee27c0d5eea439` |
| `throughput.json` | `73eb760268dd975a76ed208c7d7d15977c3bf5ec1cd58b8b7aa34f6a3123c7e8` |
| `manifest.json` | `9c1ea8df033d6d130917d4253d8088658a7eb319cdbd661ef7facf6ed4cf8aa3` |
| `resolved_config.yaml` | `23bb300cda9b4e69a6f0b2a74ae978244dd49d26388bafa87df838ea2c6e88f8` |
| `stdout.log` | `df388bda2b50dbd78d4876c532fffc981829cda70cc6268fd71cc81f09b77d8e` |
| `stderr.log` (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `git_state.txt` | `adc88bd32cbe2ba1c03b5be77936cfcbcd3e3a37af50ac3c202b6237182c03e4` |
| `environment_info.json` | `0bac4d26a014e9071f461661c148d19c5d4e5f37e0f5242eded1ed340b21d05d` |
| `environment_results.csv` | `8b1a7df648d43284674876cb6537e26fcbff4d9ea12c8e6918281aa0eefa70ce` |
| `hypotheses.jsonl` (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `memory_operations.jsonl` (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

### Run B: `artifacts/E100_arc_interface/20260904T074956Z_seed12345_9e2317b0/`

| File | SHA-256 |
|---|---|
| `SHA256SUMS` | `1cdca620dfd0fd26553233a206ea50609cd2d122251d59bf92bbaa89614849dd` |
| `results.json` | `2bbe3e1f4544ad0578c9ec9c2a62fb6b27f44ce3ffd2f33b44d13213dabd32b8` |
| `transitions.jsonl` | `b09cde6f7168f573cd2f36b77d34cec02d149162658782258aa83a8d503fa1b3` (byte-identical to run A) |
| `metrics.csv` | `891f66ba706ddb1bb6d77edd7e3f6372d68b90ee4df06beaa5ee27c0d5eea439` (byte-identical to run A) |
| `throughput.json` | `d3ca13cbb4fa576f77427a2849f424dbc2818c637a8dc74549d27fb261ef01ad` |
| `manifest.json` | `884d3facf430164ed1ccf0192da20d691a79adde9ee8dee9ac128ea622602e7d` |
| `resolved_config.yaml` | `23bb300cda9b4e69a6f0b2a74ae978244dd49d26388bafa87df838ea2c6e88f8` (byte-identical to run A) |
| `stdout.log` | `35732041f64b0bc0f18b28bf52efc51f2357cedb74477ded4c949aedfd99f55b` |
| `stderr.log` (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `git_state.txt` | `fe80e97212adada4456d3bbdd794f76653a038e1c74e14a0cbb23d23ee5cc9a4` |
| `environment_info.json` | `7724de6a56aa8d031b8ff2a471f7f620fa9f25a25a956dfeef204d2c81f560c8` |
| `environment_results.csv` | `8b1a7df648d43284674876cb6537e26fcbff4d9ea12c8e6918281aa0eefa70ce` (byte-identical to run A) |
| `hypotheses.jsonl`, `memory_operations.jsonl` (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

### Run C: `artifacts/E100_arc_interface/20260904T075000Z_seed12346_b801dd9b/`

| File | SHA-256 |
|---|---|
| `SHA256SUMS` | `c8503416d8fd7e8103862a0a68e1299530991cbbab7d09459506cfc396c3d928` |
| `results.json` | `0775f27d1805ba652ff888904d6245a6009f5b125118b4b493a72aab66935606` |
| `transitions.jsonl` | `227c5a821ab06a4200f23fbd734522aff672f25e56364c5c9fca2c8e1d729eb0` |
| `metrics.csv` | `d8551b7b8cd1050c8e06f4808dd77f9e6a9be68eb00c63f2a3656b1a91be83f9` |
| `throughput.json` | `e85f26bd0dc11e7aa2708a37590d3ed063152f8cb829516ea1aa10a246bf30d6` |
| `manifest.json` | `4e9c617a8f5307d2ba53b4e9e32c8dccc78f63179c12d6a1befe035a4f8d7c18` |
| `resolved_config.yaml` | `2904fea804fbbaad544a7f5ac70d8c881f23e6c45008c25200862ff5028ef054` |
| `stdout.log` | `79d4bd2404acc94376ebfbfa329f765944ce06a213d2525d78d7664c82904829` |
| `stderr.log` (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `git_state.txt` | `fe80e97212adada4456d3bbdd794f76653a038e1c74e14a0cbb23d23ee5cc9a4` |
| `environment_info.json` | `35427d860218bfa9575e6aa1fcb9d1f8d6006765b02adba43ab9c8e0fa612d79` |
| `environment_results.csv` | `c203df36b376d203a0155157d445c0be65f478b6124cb0254027c8626ae787ba` |
| `hypotheses.jsonl`, `memory_operations.jsonl` (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

**Provenance.** Every `manifest.json` records `git_commit 802369e86f8c1ae09a94b75d7ec72c8c9d3c66cc`,
`git_dirty true`, `completion_status completed`, `network_attempts 0`, `model_calls 0`,
`wallclock_limit_seconds 1800`. Each `git_state.txt` lists the dirty paths: run A
`state/BUDGET.json`, `state/LEDGER.jsonl`; runs B and C the same two plus the untracked
`artifacts/E100_arc_interface/` that run A had just created. No source, config, lock or
environment file was dirty, so the code that produced the runs is exactly the tree at 802369e.
The dirty flag is the supervisor's counter edit, as `known_conflicts_at_authoring` predicted.

---

## 5. Verifier result as observed by the referee

Command: `uv run python scripts/verify_run.py --gate G1 --report /tmp/referee_verify_G1.json`,
run from the graded commit 1435f81 on a clean tree. Exit code 0. Final line:

```
PASS gate=G1 prereg_sha256=abaa4e99a1caad630d19f77e9804939a008d8748e4425ef7d4897c670f1d59ca checks=18/18 skipped=0
```

`diff state/verify_G1.json /tmp/referee_verify_G1.json` shows exactly two differing lines,
both timing strings inside `detail` (`uv sync` "0.23ms" vs "0.25ms"; pytest "161 passed in
10.01s" vs "11.25s"). Every `observed`, `threshold`, `passed` and `evidence` value is identical.

Observed values in the referee's run (each cross-checked against the raw file named):

| Check | Observed | Threshold | Raw source confirmed by the referee |
|---|---|---|---|
| arc_agi_version_pinned | uv.lock and installed `arc-agi` 0.9.9, `arcengine` 0.9.3 | 0.9.9 | `uv.lock` lines 15-16, 66-67 |
| environment_cache_manifest | 25 stems, 50 files listed, 50 on disk, drift 0, committed | 25 / drift 0 | referee re-hashed all 50 files under `environment_files/` against the manifest: 0 mismatches, 0 unlisted, 0 missing |
| run_artifact_completeness | 3 runs, 14 files each, all 19 manifest keys | contract + `throughput.json` | `ls` of each run directory |
| sha256sums_verify | 39/39, fraction 1.0 | 1.0, every file listed | `sha256sum -c` in each directory |
| offline_run | 0 attempts, 0 model calls, OFFLINE, NetworkGuard, all runs | 0 / 0 | `manifest.json`, `results.json` of each run; `tests/unit/test_guards.py::test_guard_blocks_connect_and_counts_attempts` shows `connect`, `getaddrinfo` and `create_connection` raise under the guard and are counted (3 attempts), so zero attempts is evidence of a live guard |
| games_attempted_and_terminal | 25 attempted, 25 terminal, 0 step failures, every run | 25 / 1 / 0 | `results.json` of each run; `stdout.log` line 28 of run A: `finished games=25 terminal=25 step_failures=0 total_steps=3306` |
| exclusion_nesting | 3 excluded keys per run (`created_utc`, `run_id`, `wallclock_seconds`), all depth 1, none a container | depth 1, no containers | referee parsed each `results.json`: top-level keys are exactly `completion_status, config_hash, created_utc, experiment_id, extra, results, run_id, seed, wallclock_seconds` |
| nondeterministic_fields_within_bounds | 15 excluded names, all in the four allowed categories | G0 categories | `configs/nondeterministic_fields.yaml` |
| determinism_identity | 1.0; contrast differs | 1.0 / must differ | referee: run A and run B `results.json` are equal as parsed objects after removing only `created_utc`, `run_id`, `wallclock_seconds`; `transitions.jsonl`, `metrics.csv`, `environment_results.csv`, `resolved_config.yaml` byte-identical (same digests above); run C `results.results` differs from run A |
| replay_final_frame_identity | 75/75 games, 0 divergent, 3306 + 3306 + 3820 steps replayed, 0 network attempts during replay | 1.0 / 0 divergent | referee: in every run and game, `transitions.jsonl` `step_index` runs 1..n, n equals `steps_taken`, and the last `frame_sha256` equals `final_frame_sha256` in `results.json` (75/75). Example, run A `sp80-589a99af`: 30 records, last `frame_sha256` `b71b1a2baf10495427b97d55f347fd849ad37a75df8a8e5ff3adb1528b4561aa` = `results.json` `final_frame_sha256` |
| throughput | 1589.6 / 1576.9 / 1639.9 fps over 3306 / 3306 / 3820 steps | 500.0 over >= 1000 | referee recomputed `steps / step_seconds` from `throughput.json` aggregate and from the sum of `per_game`: identical to stated |
| git_status_clean | 0 lines | 0 | `git status --porcelain` empty |
| licence_text | "MIT No Attribution" | same | `LICENSE` line 1 |
| uv_sync / pytest / pytest_min / ruff / mypy | 0 / 0 (161 passed) / 161 / 0 / 0 | 0 / 0 / 1 / 0 / 0 | verifier `detail` strings |

---

## 6. Primary results

- **Replay final-frame identity: 1.0 (75/75 game-runs, 0 divergent).** Recomputed by the
  verifier in its own process under `NetworkGuard(0)`, and cross-checked by the referee from
  the raw `transitions.jsonl` and `results.json` of every run.
- **Determinism identity: 1.0** across two seed-12345 invocations; contrast seed 12346 differs.
- **Throughput (pre-registered definition, step-only): 1589.6, 1576.9, 1639.9 fps** over
  3306, 3306, 3820 steps. All-in (steps / manifest `wallclock_seconds`): 786.7, 777.2, 822.9
  fps (3306/4.2025, 3306/4.2540, 3820/4.6421), recomputed by the referee; both above 500.
- **Offline: 0 network attempts** in every run and in every replay.
- **Terminal states: 25/25 games per run, all `GAME_OVER`; none `WIN`.** Exactly one level
  completed in 75 game-runs: run C `ft09-0d8bbf25`, `levels_completed 1` of `win_levels 6`,
  `steps_taken 742`, `final_state GAME_OVER` (`results.json` of run C; `metrics.csv`
  `levels_completed_total 1`). Runs A and B: `levels_completed_total 0`.

**Confidence intervals.** Not applicable in the statistical sense: every pre-registered
metric is an identity or a count over the whole population of 75 game-runs (no sampling), and
the fps figures are single-run wall-clock measurements whose spread across the three runs
(1576.9-1639.9 step-only, 777.2-822.9 all-in) is the only dispersion available. The margin to
the 500 floor is a factor of 3.2 step-only and 1.55 all-in.

---

## 7. Strongest baseline, ablations, compute comparison

- **Baseline:** none mandated (`mandated_baselines: []`). G1 has no treatment/control pair.
  The threat of a baseline implemented too weakly to lose (PROPOSAL_v2 section 11, T12 family)
  therefore cannot arise at this gate. Not applicable, stated rather than skipped.
- **Ablations:** none pre-registered. The only manipulation is the contrast seed, which
  changes the policy's action stream (run C: 3820 steps, `transitions.jsonl` digest differs)
  and shows the identity check is not passed by a policy that ignores its seed.
- **Compute comparison:** no treatment/baseline compute to balance (T10 family, compute
  imbalance: not applicable). Wall-clock per run 4.20 s, 4.25 s, 4.64 s against a 1800 s
  limit; the 5000-actions-per-game budget never binds (longest game 526 steps at seed 12345,
  742 at seed 12346; 3306-3820 of 125000 budgeted actions used).
- **In-context substitution for persistent state (T10):** not applicable. E100 makes zero
  model calls (`model_identifier null`, `model_calls 0`), has no persistent state
  (`persistent_state_size_cap 0`) and no learning; there is nothing a context window could
  substitute for.

---

## 8. Failure analysis and the C5 self-review, weighed

**No check failed.** The one FAIL in the gate's history (report committed at e589b96,
`git_status_clean` 17/18) was caused by the uncommitted ledger attempt line, was committed as
found, and was superseded on a clean tree at b69a19a; both reports survive in git history.

**C5 argument A1 (make() seed inert).** The ledger `c5_self_review` entry (07:56:51Z) reports
that replaying every action list of run A under `make(seed=7)` reproduces all 25 recorded final
digests. The referee re-tested this independently with its own script (kept at
`/tmp/referee_a1_check.py`, not in the repository) on five games (`ls20`, `ft09`, `sp80`,
`sb26`, `lp85`) under three seeds never used by any run (7, 99, 2147483647), comparing every
intermediate `frame_sha256` and the final digest, under `NetworkGuard(0)`: 15/15 replays,
0 intermediate mismatches, 0 final mismatches, 0 network attempts. A1 is confirmed as a
substrate fact.

Does A1 undermine what the pre-registration says the replay certifies? No. The
pre-registration anticipated it in `replay_protocol.seed_handling`: "If the toolkit ignores
the seed for a game, replay still succeeds only if the game is deterministic; that is precisely
what is being measured." The primary metric's stated purpose (G3 backtests hypotheses against
recorded trajectories; mechanism comparisons freeze environment instances) needs exactly what
was shown: the recorded action log reproduces the recorded frames in a fresh process. What A1
removes is any future claim that `make(seed)` supplies environment variation; that consequence
is now a dated, artifact-cited entry in `docs/EVIDENCE_ARC.md` section 3.1 and must be
respected by every later pre-registration (section 11 below).

**C5 argument A3 (identity rests on exclusions).** Refuted by the digests in section 4: the
non-timing artifacts of runs A and B are byte-identical, and the referee confirmed the parsed
`results.json` differ only in the three excluded scalars.

**C5 argument A2 (fps overstated).** Real and correctly recorded: all-in throughput is about
half the step-only figure (777-823 vs 1577-1640). The pre-registered definition is step-only
and both figures clear the floor. Recorded in `docs/EVIDENCE_ARC.md` section 3.1.

**Substrate observations (not failures).** Every public game ends in `GAME_OVER` under random
play; ten games stop at round counts (30, 42, 50, 100, 200, 300), consistent with per-game
action caps. The slowest single game is `sb26-7fbdac44` at 409.7 fps step-only in run A
(minimum per-game fps 408.4 and 404.7 in runs B and C), below the 500 aggregate floor;
`throughput.json` per-game values are pre-registered as observed, not thresholded, so this does
not bear on the predicate, but any later gate that steps `sb26` heavily should budget for it.

---

## 9. Discrepancies between the dispatch brief and what the referee found

1. The brief said naming the pre-registration directory in a shell command is denied by the
   hook and that the referee might have to fall back to the hash in `state/PROJECT_STATE.json`.
   In the referee's session `sha256sum preregistration/G1.yaml` succeeded and returned
   `abaa4e99...`, matching the state file, the ledger G1.1 entries, the verifier's
   `prereg_sha256` and the blob at 773f1a2. No fallback was needed.
2. The G1.4 `decision` ledger entry (07:52:51Z) states `levels_completed_total` is 0 in every
   run. It is 1 in run C (`ft09`). The C5 entry corrects this and the evidence entry carries
   the correction; the referee confirmed the raw value in run C `results.json` and `metrics.csv`.
   The ledger is append-only, so the wrong statement stands with its correction after it.
3. The A1 test cited in `docs/EVIDENCE_ARC.md` section 3.1 was run from a throwaway `/tmp`
   script whose output was not preserved as an artifact; the entry cites the ledger line, not
   a hashed output file. C4 is met only through the ledger file's digest
   (`caff1f71...` at grading). The referee's independent confirmation above stands in for
   the missing artifact for this verdict, but the pattern should not recur (section 11).
4. The pre-registration's `checks_in_order` names 17 items; the verifier reports 18 because
   `nondeterministic_fields_within_bounds` is carried from G0 and pytest is split into exit
   code and collected count. Every threshold the 18 checks apply is in the pre-registration.
5. Everything else in the brief (run ids, SHA256SUMS digests, report digest, verifier
   digest, commits 773f1a2 / 621983e / e589b96 / 1435f81, the 35-line additions-only evidence
   diff, `git diff b69a19a 9283d4a --numstat -- docs/EVIDENCE_ARC.md` = `35 0`) matched.

---

## 10. Novelty implications

None. G1 is infrastructure; no mechanism, claim or manuscript statement rests on it. The one
finding of general interest, that `Arcade.make()`'s seed has no observable effect on the 25
public games of `arc-agi` 0.9.9 / `arcengine` 0.9.3, is a toolkit observation recorded in
the evidence base with a date, not a contribution.

---

## 11. Decision, pass-rule evaluation, and the single permitted next action

All 26 pre-registered thresholds are met on the raw artifacts as re-derived by the referee,
with the pre-registration and the verifier provably fixed before the first result. G1 has no
mechanism and no pass rule beyond its exit predicate; the predicate evaluates true.

Verdict: GO

**Single permitted next action:** record this verdict (file and digest) in the ledger and
`state/PROJECT_STATE.json`, mark G1 passed at graded commit 1435f81, and begin G2.1: author
`preregistration/G2.yaml` from PROPOSAL_v2 section 9 row G2 before any G2 artifact exists.

**Items the G2 pre-registration must hash-lock rather than remember** (carried forward as
the G0 verdict did for G1):

1. `Arcade.make(seed)` is inert on the public games: no G2 or later check may treat the
   environment seed as a source of variation; environment variation comes from the policy
   seed or the game set, and the determinism contrast must name which.
2. Any project-produced number cited in an evidence document must be backed by a preserved
   artifact under `artifacts/` with a `SHA256SUMS` entry, not by a `/tmp` script's recollection
   in a ledger line (discrepancy 3 above).
3. If any later threshold depends on throughput, state whether it is step-only or all-in;
   the two differ by a factor of about two on this machine (section 6).
