# G2 Verdict: Human baseline (RHAE adapter, 342 human replays, per-level baselines)

Referee: independent referee subagent (Claude Fable 5.1, effort max), read-only tools plus
`Write(docs/decisions/**)`. Issued 2026-09-04 (the referee read `date -u` 16:03:49Z when its
verifier run finished and 16:12:16Z at its last command; the graded commit was made at
16:00:12Z).

**Graded commit:** `9e66b0d7e84d7087b54760c67a041b5e7e781f9c` (branch `main`, read from
`.git/HEAD` -> `refs/heads/main`). `git status --porcelain` was empty before the first and after
the last command the referee ran.

Verdict: GO

---

## 1. Governing documents, as verified

| Item | Path | SHA-256 (computed by the referee with `sha256sum`) |
|---|---|---|
| Pre-registration | `preregistration/G2.yaml` | `f6539aa1a1ddfad220651050d88f7d73e8a7fe3d0455318f65266117720b7344` |
| Same file as git blob `af8e00d0b55c1679875da5d87f95fb73b3f25b6f`, which is the blob at both commit 3fe3298 and HEAD (`git cat-file blob <id> \| sha256sum`; the control-surface hook denies shell lines that name the directory) | | `f6539aa1a1ddfad220651050d88f7d73e8a7fe3d0455318f65266117720b7344` |
| **Verifier that graded this gate** (required by the human's G2.5 answer and constitution section 7) | `scripts/verify_run.py` | `df560de6c90fe770c57deb0bf66491543ce7dbd7e9016a4d8b2814533623bd74` |
| Builder's verifier report | `state/verify_G2.json` | `4bfccdb578b1273f854b541af506fd669fd8a02723da0a2d8bfd0b5983831512` |
| Referee's own verifier report (outside the repository) | `/tmp/referee_verify_G2.json` | `8d7443becc99a188ba8ec2c91962a31b38652394c9487c71853fc4bbbe883f5f` |
| Human replay dataset manifest | `experiments/human_replays_manifest.json` | `08ea6ef9898dd0e493bd682131f25e257d61ef2b56a2710b37c25ba85c9bfd79` |
| Environment cache manifest | `experiments/environment_cache_manifest.json` | `023726479a3c201161a61ee0d310b20696988933adbf1826dc9d7bd524d960af` |
| Experiment config | `configs/experiments/E020_human_baselines.yaml` | `77a31e8f45c92f2d13a149bc65b926de8d4b40d0ec2dedc92592688fd12c9329` |
| Exclusion list | `configs/nondeterministic_fields.yaml` | `cd412e291aaf8689555f0884fd6507e1888ef97989a0b4eda7eaf77f145d0983` |
| RHAE adapter | `src/arc_plasticity/evaluation/rhae.py` | `41b10ff0169c0c6926d8f9448bf02055d665fcd9d8d5e479308f392e72b683c3` |
| Toolkit reference implementation (arc-agi 0.9.9) | `.venv/lib/python3.12/site-packages/arc_agi/scorecard.py` | `1cc830e48008bec60b8a98ae14d3e9312e8408f102a9878bad42744aa9e489b7` |
| Dependency lock (equals `dependency_lock_hash` in both run manifests) | `uv.lock` | `cc86c9444379162b5bdffbb9d88efd3415cc6398e62617b236e18c75edd84a22` |
| Ledger at grading | `state/LEDGER.jsonl` | `4800405d35f48b5a5b4a14b345942dd32a14906285d346f94a6fb744319f8a25` |
| State at grading | `state/PROJECT_STATE.json` | `0aeca27def185cc6b16c38e7f07037f1e9205ffa0dd40a6d366ca1500d2c29bf` |
| Evidence base at grading (unchanged since the G1 verdict recorded the same digest) | `docs/EVIDENCE_ARC.md` | `2e669d1c872d4780e16aa192f7f18032250d39cf78a330e69fc8a7c459621d61` |
| Licence | `LICENSE` | `9fcfafab9ac0559c961f9cc4c1e23f176fb35d58a546f6d2ed01164efa9fe346` |
| Predecessor verdicts | `docs/decisions/G1_VERDICT.md`, `docs/decisions/G0_VERDICT.md` | `9ba6a1cf139515550dfa8b3f4564297a609e73099afee6aa0a38a8db52884c45`, `37ffb13b00f691febebd1ba0aba035de4f62810333ed6dbedc1c81f6e97d3ede` |

**C1/C2 timing, from git commit times (UTC), not from the ledger.** The pre-registration was
committed alone at 3fe3298 (08:22:58Z) and is the only commit that has ever touched it. The
verifier was last changed at 1767414 (08:54:00Z, G2.4). The dataset was placed by the human at
14:59:05Z (`retrieval_utc`, the Drive export timestamp) and the answer clearing the block was
archived at 15:22:34Z. The loader extension for the released format was committed at a75e625
(15:41:41Z, G2.6) and the runner's P1/P2 logging at 8efe71c (15:44:54Z, G2.7). The two runs
were created at 15:45:31Z and 15:47:18Z (`timestamp_utc`) and first committed at 659fb69
(15:52:17Z); the verifier report at 2de14e7 (15:56:26Z); the graded commit at 16:00:12Z.
`git diff --stat 659fb69 9e66b0d -- artifacts/ experiments/ src/ configs/ scripts/` is empty
and `git diff --name-status 8efe71c 9e66b0d` lists only the 34 added artifact files,
`state/LEDGER.jsonl`, `state/PROJECT_STATE.json` and `state/verify_G2.json`, so the code at
HEAD is byte-identical to the code recorded as `git_commit` in both run manifests. Every
threshold and every hand-computed vector was therefore fixed six hours before any data existed,
and the only code written after the data was seen is the loader for the released file format,
whose reading is examined in section 9.

---

## 2. Original hypothesis and pre-registered prediction

`preregistration/G2.yaml` `hypothesis` carries one infrastructure claim and one falsifiable
sub-claim. Infrastructure: the project computes RHAE exactly as currently documented
(`min(1.15, (h/a)^2)` per level, `w_l = l` counted from 1, completion cap, plain mean over
environments) by delegating to `arc_agi.scorecard.EnvironmentScoreCalculator`, demonstrated on
hand-computed vectors that would fail under the superseded `min(1.0, h/a)^2`, under uniform or
zero-based weights, and without the completion cap; the 342 released replays are obtained with
recorded provenance and ingested without parse failure; and a per-level baseline is derived for
at least 80 percent of the 183 public levels. Scientific sub-claim: the official per-level
`baseline_actions` in every cached `metadata.json` are reproducible from the released replays
under the documented rule "upper-median of each participant's best first-run completion action
count". **Prediction, recorded before the data was seen:** if the 342 replays are the complete
set the platform aggregated, exact agreement should be close to 100 percent of derived levels;
a systematic shortfall would mean the platform aggregated sessions that were not released or
used a rule that differs from the documented one. Either outcome is a finding; neither changes
the gate, because the predicate thresholds coverage, not agreement.

Primary metric: `human_baseline_level_coverage`, pass value 0.80. Co-primary machine checks:
every embedded RHAE vector within `1.0e-9` and every derivation vector exact. The 38
pre-registered thresholds the verifier reads (all from the hash-locked file, none from prose):
`public_games_total 25`, `public_levels_total 183`,
`metadata_baseline_levels_must_equal_public_levels_total true`, `rhae_level_cap 1.15`,
`rhae_level_weight_rule "w_l = l ..."`, `rhae_synthetic_cases_min 6`, `rhae_synthetic_cases_max 8`,
`rhae_synthetic_abs_tolerance 1.0e-9`, five `rhae_synthetic_required_tags`,
`rhae_synthetic_all_cases_must_pass true`, `rhae_adapter_must_delegate_to_toolkit true`,
`derivation_vectors_min 6`, `derivation_vectors_all_must_pass true`, `replay_units_min 342`,
`replay_parse_failures_max 0`, `human_baseline_level_coverage_min 0.80`,
`derived_baselines_positive_integers true`, four `dataset_manifest_required_fields`,
`dataset_manifest_min_files 1`, `dataset_manifest_drift_files_max 0`,
`input_manifest_must_equal_dataset_manifest true`, `network_calls_allowed 0`,
`network_attempts_max 0`, `model_calls_allowed 0`, `determinism_identity_min 1.0`,
`contrast_runs_required 0`, `excluded_key_max_depth 1`,
`excluded_key_container_values_allowed false`, `sha256sums_verified_fraction_min 1.0`,
`sha256sums_must_list_every_artifact_file true`, `action_budget_multiplier_for_later_gates 5`
(not a G2 pass criterion), `uv_sync_exit_code 0`, `pytest_exit_code 0`,
`pytest_min_tests_collected 1`, `ruff_exit_code 0`, `mypy_exit_code 0`,
`git_status_porcelain_lines_max 0`, `licence_required_text "MIT No Attribution"`.
Mandated baselines: none. Revision limit: 0 (no mechanism).

---

## 3. Experiments completed

Two runs of `E020_human_baselines` through
`uv run python scripts/run_experiment.py --config configs/experiments/E020_human_baselines.yaml`
(runner `human_baseline_derivation`, seed 12345 from the config in both, no `--seed`
override, `NetworkGuard` with 0 calls allowed, 0 model calls, 600 s limit), over the 342
human-placed recordings under `data/human_replays/raw/` (gitignored; integrity record is the
committed manifest), the 25 cached `metadata.json` files and the three graded G1 `results.json`
files. Wall-clock 97.29 s and 98.29 s. Both `completion_status completed`, `stderr.log` empty.

---

## 4. Raw artifacts, digests computed by the referee

`sha256sum -c SHA256SUMS` returned `OK` for all 16 listed files in each run directory (32/32,
exit 0). Each directory holds exactly the 16 listed files plus `SHA256SUMS`; nothing is
unlisted. The referee's directly computed digests of every file:

### Run A: `artifacts/E020_human_baselines/20260904T154531Z_seed12345_2599f0a4/`

| File | SHA-256 |
|---|---|
| `SHA256SUMS` | `5a7c569312f9a43240680b724a0ccb7453cc6f5da48082c0e5bde68bbc1b8fac` |
| `results.json` | `20c8437952a5a1154191b6e0573b6d74c07c1c55ce00dcb831c6300fcaaf1aea` |
| `human_baselines.json` | `1e841bf53ba5450d506e8605cf168e6e4894520953171ae552e115a03b181185` |
| `metrics.csv` | `2686a8eb65954cbab04c41f9f0fa55e70c754e0a93a8a3114bb19150ee90db63` |
| `input_manifest.json` | `71aa97fb82869a874f671981896ba949d665639861856c3ac6d30c7d86c7a1bc` |
| `replay_ingestion_log.jsonl` | `3572a5bfe9336b1ad13c1b6a3a345d395dbe2700903ee9c755b71a0ef158c697` |
| `manifest.json` | `eefd9c7869f9eacbede9cf0b588da54b9d2e43c266f95932f1c2c6b5346e07ef` |
| `environment_results.csv` | `ede0732b986e38e8260e3c4cc3eb244ac7c37b53c0f153908b1f9089cc68cdc5` |
| `g1_termination_vs_budget.json` | `82c592f0ef357e337f7aefa62a9b297a86d39e15eaaef810a5d8c86b29095f5f` |
| `resolved_config.yaml` | `8cd907bf41ad4addfb3f76a3c9a5386fe80b45d9582407cc6c416feb7f57f41f` |
| `stdout.log` | `d13cdd1d496c01fb81c586f8fe12d7a7da4b980ea9bd1abc0255194a91c1e065` |
| `git_state.txt` | `f6087f95a9f6c865502d90e5117caf5f96dee67a98a8645d70e8b695f390b2b5` |
| `environment_info.json` | `ae73438715dbf4ee8c3d94b1ec48c328da9de531263de8188fbee84397fed0b4` |
| `stderr.log`, `hypotheses.jsonl`, `memory_operations.jsonl`, `transitions.jsonl` (all empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

### Run B: `artifacts/E020_human_baselines/20260904T154718Z_seed12345_bff74ab0/`

| File | SHA-256 |
|---|---|
| `SHA256SUMS` | `34c772691cfffa55dea675dc6b15c4c8b6f42a625fddbd14fa3533af6b75fb94` |
| `results.json` | `3cb04ebc4a20461e099288ea6f40c4950232fcae7f0bec9f9826424fb1bd1a65` |
| `human_baselines.json` | `1e841bf53ba5450d506e8605cf168e6e4894520953171ae552e115a03b181185` (byte-identical to run A) |
| `metrics.csv` | `2686a8eb65954cbab04c41f9f0fa55e70c754e0a93a8a3114bb19150ee90db63` (byte-identical to run A) |
| `input_manifest.json` | `71aa97fb82869a874f671981896ba949d665639861856c3ac6d30c7d86c7a1bc` (byte-identical to run A) |
| `replay_ingestion_log.jsonl` | `3572a5bfe9336b1ad13c1b6a3a345d395dbe2700903ee9c755b71a0ef158c697` (byte-identical to run A) |
| `manifest.json` | `cc2f08de211744aff6f85dbb084f5fd7a4307a6318b89d79173bb8b2f9cd93f1` |
| `environment_results.csv` | `ede0732b986e38e8260e3c4cc3eb244ac7c37b53c0f153908b1f9089cc68cdc5` (byte-identical to run A) |
| `g1_termination_vs_budget.json` | `82c592f0ef357e337f7aefa62a9b297a86d39e15eaaef810a5d8c86b29095f5f` (byte-identical to run A) |
| `resolved_config.yaml` | `8cd907bf41ad4addfb3f76a3c9a5386fe80b45d9582407cc6c416feb7f57f41f` (byte-identical to run A) |
| `stdout.log` | `c8e0ea3548d500a642252c3273d0130ead3e0aef1cc8340c090fa0ee6c63a57a` |
| `git_state.txt` | `65292a4c99ef3a6b27614d27d9973acaa87fd97cf793f9409d4ed9dc48c399f4` |
| `environment_info.json` | `541d3950783178e2de80702572972cbfcd5522e97cf639717b02ff9297e5035c` |
| `stderr.log`, `hypotheses.jsonl`, `memory_operations.jsonl`, `transitions.jsonl` (all empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

**Provenance.** Both manifests record `git_commit 8efe71c78e06a27e3d432c40b66581a59ba8c2c3`,
`git_dirty true`, `config_hash 6da25a72...`, `dependency_lock_hash cc86c944...` (equal to the
referee's digest of `uv.lock`), `network_attempts 0`, `model_calls 0`, `model_identifier null`,
`wallclock_limit_seconds 600`, `completion_status completed`. `git_state.txt` lists the dirty
paths: run A ` M state/PROJECT_STATE.json`; run B the same plus the untracked
`artifacts/E020_human_baselines/` that run A had just created. No source, config, lock,
environment or data file was dirty (section 9, risk c).

**Raw dataset.** The referee regenerated a checksum list from the committed manifest
(`/tmp/referee_raw_sums.txt`, `b23d20eb98d33033ffc8ba72aab1ec9a64a658fc637d438a8fa80f74eee234dc`)
and ran `sha256sum -c` in `data/human_replays/raw/`: 342 of 342 files `OK`, exit 0
(`/tmp/referee_raw_sums.out`, `3f02dc2bb39af6171d1bb2167e14001a81ee1544720ddc4e64450d2d01a9e879`).
`find` counts exactly 342 regular files (6.7 GiB) under the raw directory, so nothing is
unlisted. The manifest carries `source_url` (the Google Drive folder reached through
`https://dub.link/vfwCqvb`), `retrieval_utc 2026-09-04T14:59:05Z`,
`retrieval_method human_placed`, a `revision` string and 342 `files` entries, each with
`replay_units 1` and `parse_failure null`.

**Referee's independent re-derivation (outside the repository).** A parser written by the
referee that imports nothing from the project (`/tmp/referee_g2_rederivation.py`,
`e96aa6d1115c477549ffe3bf311b98159fb7b5c2620d1fffce29b2a9d863c829`) read all 342 raw files,
applied the pre-registered attribution and aggregation rules, and wrote
`/tmp/referee_g2_rederivation.out` (`5b60e41b083cdf579fa17af8b87ba3330ea0f371f25e500e37f9633a439978be`)
and `/tmp/referee_g2_rederivation.json` (`8c417ba0bb93c92d2cda577bdd1c318199c03871e586481c7dcf2f40a4d28377`).
As with the G1 referee's `/tmp` check, these are not repository artifacts; their digests are
recorded here so the verdict's numbers are traceable.

---

## 5. Verifier result as observed by the referee

Command: `uv run python scripts/verify_run.py --gate G2 --report /tmp/referee_verify_G2.json`,
run from the graded commit 9e66b0d on a clean tree, tooling checks included. Exit code 0.
Final line:

```
PASS gate=G2 prereg_sha256=f6539aa1a1ddfad220651050d88f7d73e8a7fe3d0455318f65266117720b7344 checks=19/19 skipped=0
```

`diff state/verify_G2.json /tmp/referee_verify_G2.json` shows exactly two differing lines, both
timing strings inside `detail` (`uv sync` "0.24ms" vs "0.29ms"; pytest "265 passed, 2 skipped
in 14.54s" vs "15.13s"). Every `observed`, `threshold`, `passed` and `evidence` value is
identical. The referee read the G2 section of the verifier (`evaluate_g2` and its twelve
check functions, lines 1343-1891): every numeric bound is obtained through
`threshold(prereg, ...)` or a pre-registration section; the only literals are the identity
values 0.0/1.0 and a 1e-12 float-comparison tolerance.

Observed values in the referee's run, each cross-checked against the raw file named:

| Check | Observed | Threshold | Raw source confirmed by the referee |
|---|---|---|---|
| public_level_count | 25 games, levels sum 183 (6-10 per game) | 25 / 183 / must equal | referee read `baseline_actions` in the four traced `metadata.json` files (ar25 8, lp85 8, vc33 7, wa30 9) and the cache manifest's `baseline_actions_count` |
| rhae_synthetic_vectors | 8 cases, 0 failing, 7 tags seen incl. all 5 required, delegates true | 6-8, 1e-9, all pass, delegate | referee re-derived all eight expected values and every `alternative_form_values` entry by hand from the formula in `rhae.definition` (C1 100; C2 100; C3 55 with 50 / 60.75 / 70 / 25; C4 641/12 = 53.4166 with 50 / 53.4166 / 67.625 / 25; C5 55 with 50 / 57 / 70 / 25; C6 62.5 with 75 / 50; C7 50 with 57.5 / 66.667; C8 [100, 0] mean 50 with 100 / 33.333): all correct. `rhae.py` calls `EnvironmentScoreCalculator.add_level(level_index=position+1, ...)` and `to_score().score`, and `total_score` is a plain mean; nothing is added to the formula. `scorecard.py` lines 146-206 implement `min((b/a)^2*100, 115.0)`, weight `level_index`, cap `max_weights/total_weights*100` |
| baseline_derivation_vectors | 9 cases, 0 failing | >= 6, all pass | verifier `per_case` expected values equal the pre-registration's (D1 5, D2 7, D3 8, D4 6, D5 7, D6 8, D6b 8, D7 null, D8 [3,3,4]); referee re-derived each by hand from the rules |
| dataset_manifest | 342 files, drift [], committed true, provenance fields present | >= 1 file, drift 0, 4 fields | referee's own `sha256sum -c`, 342/342 OK |
| run_artifact_completeness | 2 runs, 17 files each, 19 manifest keys | contract + 4 extras | `ls` of each run directory (section 4) |
| sha256sums_verify | 32/32, fraction 1.0 | 1.0, every file listed | `sha256sum -c` in each directory, 0 unlisted |
| offline_run | 0 network attempts, 0 model calls, `offline_local_files`, `NetworkGuard`, both runs | 0 / 0 | `manifest.json`, `results.json` of each run |
| replay_ingestion | 342 ingested, 0 parse failures, `participant_ids_available false`, `session_order_source file_order`, input manifest equals dataset manifest (342 digests) | >= 342, 0, equal | `results.json`, `input_manifest.json` `raw_files` (342 entries) against the committed manifest |
| human_baseline_coverage | 183/183 derived, coverage 1.0, all positive ints, `exact_agreement_fraction 0.9289617486338798` (170/183), `median_abs_relative_difference 0.0` | >= 0.80 | referee recount of `human_baselines.json` (section 6) and full re-derivation from raw bytes |
| exclusion_nesting | 3 excluded keys per run (`created_utc`, `run_id`, `wallclock_seconds`), all depth 1, none a container, in `results.json`; none in `human_baselines.json` | depth 1, no containers | referee parsed both `results.json` files: top-level keys `completion_status, config_hash, created_utc, experiment_id, extra, results, run_id, seed, wallclock_seconds` |
| nondeterministic_fields_within_bounds | 15 excluded names, bounds from `preregistration/G0.yaml` (`c91c197a...`) | G0 categories | `configs/nondeterministic_fields.yaml` (digest section 1) |
| determinism_identity | 1.0 over the two seed-12345 runs on `results.json`, `metrics.csv`, `human_baselines.json`; no other-seed run | 1.0 / 0 contrast | `human_baselines.json`, `metrics.csv`, `input_manifest.json`, `replay_ingestion_log.jsonl`, `environment_results.csv`, `g1_termination_vs_budget.json`, `resolved_config.yaml` byte-identical across runs (same digests, section 4); the two `results.json` differ only in the three excluded scalars |
| git_status_clean | 0 lines | 0 | `git status --porcelain` empty |
| licence_text | "MIT No Attribution" | same | `LICENSE` |
| uv_sync / pytest / pytest_min / ruff / mypy | 0 / 0 (265 passed, 2 skipped) / 265 / 0 / 0 (22 files) | 0 / 0 / 1 / 0 / 0 | verifier `detail` strings |

---

## 6. Primary results, confirmed in the raw data

- **Coverage: 1.0 (183/183 levels derived, threshold 0.80).** `results.json` of both runs
  (`derived_levels 183`, `human_baseline_level_coverage 1.0`), `metrics.csv` rows 8-9,
  `human_baselines.json` `totals`, and `stdout.log` line 5 of each run
  (`derived_levels=183/183 coverage=1.0000`). The referee's independent re-derivation from the
  raw recordings produced a derived value for all 183 levels and reproduced the builder's
  derived value on **183/183** levels and the builder's sorted per-participant list on
  **183/183** levels (`/tmp/referee_g2_rederivation.out` lines 29-30).
- **Replay units 342, parse failures 0, matched 342, unmatched 0** (`results.json`,
  `metrics.csv` rows 2-5, `stdout.log` line 4, `replay_ingestion_log.jsonl` 342 lines with
  `failure null`, manifest `files` 342).
- **Exact agreement with the official baselines: 170/183 = 0.9289617486338798;
  median absolute relative difference 0.0** (`results.json`, `human_baselines.json` `totals`,
  `environment_results.csv` `exact_agreement` column; referee recount 170). The 13 disagreeing
  levels lie in two games: lp85 levels 1, 2, 3, 4, 5, 7, 8 (derived 18, 39, 43, 23, 39, 57,
  131 against official 17, 38, 31, 16, 41, 26, 159) and vc33 levels 1, 3, 4, 5, 6, 7 (derived
  13, 119, 50, 120, 39, 155 against official 7, 44, 61, 131, 34, 152); `metrics.csv` rows
  142-157 and 346-359. The other 23 games agree on every level.
- **RHAE: 8/8 hand-computed vectors reproduced within 1e-9 through the toolkit delegate**
  (`state/verify_G2.json` and the referee's report, `per_case`).
- **Determinism identity 1.0** across two invocations.

**Three levels traced by the referee from raw recordings to the derived value**
(`preregistration/G2.yaml` `referee_inspects`; recording digests computed by the referee and
equal to the manifest entries). Rule applied: record 1 is the play-start frame, record k >= 2
is issued action k-1, level l is completed at the first record with `levels_completed >= l`,
attributed count = difference of successive completion indices, upper median = sorted value
at index floor(N/2)+1 (1-based).

1. **ar25 level 1 (official 32).** Ten recordings under `ar25/`: `00589449` (sha256
   `829d4f4eb978a37b2bb67facfbb1e0c6745f1d072722d273751463bd7a0b6b8c`, 1557 records,
   completion at record index 43) 43; `03665144` (`67674d02c0596a35652d00e92d2a705a63833388ed4196112bb0c51110ede94e`) 42;
   `0cf890a2` (`5ca614bbdb52e671a308227f06a667f0b2edb432da0683e4e8228834eb739a9d`) 51;
   `2a854897` (`cde161c230342cf0d8a59a741dcd5789f70ddea668c4b03cb14137190bd7936b`) 21;
   `2ef9c7c0` (`9112dd1af7e276fa142977d80b6b649c6578741982fc1b51413d355c755e3a19`) 38;
   `41285539` (`edcaf5f74c2b83d0136e90556873ca424d72428384cc45d0a4a2ed2acc3396a1`) 17;
   `b36f18b1` (`c7309da1c03ad9c8faefde48c1539fd68c660562c73b4adc241229d3ad348919`) 17;
   `e7f9a7d6` (`d11d5776ac72e30e5f1559b2712b58ead05ab773c59f8659d11d78d3e1fad42f`) 15;
   `f4698acc` (`1cb3d970cb8c34b82d7268d5e8312ee64fdff3c3e306ec434b2004b5c3a435bf`) 32;
   `e8c9d67c` (`7c5b4b0da9f5303d4078cc59d00abcec0936f3b1b23f8ce8befcd0259ad5c811`) no
   completion in 59 actions. Sorted [15, 17, 17, 21, 32, 38, 42, 43, 51], N = 9, index 5 ->
   **32** = `human_baselines.json` derived 32 = official 32.
2. **wa30 level 9 (official 415).** Five of fourteen recordings reach level 9: `0f88f0f8`
   (`fc26236cc2f16cb7886e4a8624f3a414c2737aa585229818c6dc1a59c82b26eb`) 1564-1432 = 132;
   `5fd30bfc` (`1a1a67ce92072038ede69185b0f33fc2bedcaafe6b9e88a8c51b92e025467385`) 1519-874 = 645;
   `e326447f` (`6a9d963e1c49bb1c845ae8fb07ed3ae540635fa2bfa291706b7feb7c0b94f2f8`) 2291-1876 = 415;
   `f73b1e1d` (`a021b5f60cdf2954fce99fa573750b633e9f37b14ae3221d08c139cfeec9c529`) 1719-1587 = 132;
   `fbd3f8c7` (`b69c5a5c8bf058a935bbc33e3d60e4fa27fd77019217f7cd3898096ca4dc2260`) 1616-1042 = 574.
   Sorted [132, 132, 415, 574, 645], N = 5, index 3 -> **415** = derived 415 = official 415.
3. **vc33 level 3, the level with the largest absolute relative difference (1.7045; official
   44).** Eight of ten recordings reach level 3: `1469cb95`
   (`998024cdac86ff42d5d899840770a532f346e5d1c29b348c8e8b8c27171efbfa`) 172-34 = 138;
   `374887fc` (`2eb8c4a60994d6af53e87c00115f76e4b0a94c1f1d97d5417db8a6a80574cbe8`) 232-30 = 202;
   `4cffe392` (`770706bd37b1f6564a6d562154a041eb77f02e5cdefd0c1039106635c87e5750`) 65-27 = 38;
   `74e0c891` (`c7ae36fac5703b0e0195cd843c0855b5e7d516d445a8ea0dae7c2c709c5ff992`) 175-56 = 119;
   `837812ad` (`f81f624de3306f3f458f202a08a0d7e9797c3fd5d4bcb1d23e8679e10f005e9d`) 58-22 = 36;
   `918430fb` (`6b052d457dc614752fe83212462b8e1fcdecbcf320638c44cb09950a7a35721b`) 215-61 = 154;
   `e31a16d6` (`fdca3692d60284df396215f37a7ca505bfdabbbcfab8400b7af9717b1cc8fbc6`) 79-41 = 38;
   `e60e880e` (`29e3d5613ec5abd2f8178cc9db535c6c0c285201e428d65c7ed24da6ad5a3cce`) 64-36 = 28.
   Sorted [28, 36, 38, 38, 119, 138, 154, 202], N = 8, index 5 -> **119** = derived 119. The
   official 44 is not among the eight released values and no order statistic of them yields it.

In every one of the 325 recordings whose closing toolkit scorecard carries `actions_by_level`
pairs, the referee's step-log attribution equals the pair-derived counts exactly (325/325, 0
differ); 16 recordings have a card without the key and one (`cn04/8150a401`, one action, no
completion) an empty list. The builder's P1/P2 summary (`input_manifest.json`
`dataset_agreement_summary`: 324 files all levels agree of which 24 vacuous, 2 disagreeing, 16
P2 unavailable, 1617 levels agree, 9 disagree) is consistent with this once the two "disagreeing"
files are read as in section 9(d).

---

## 7. Confidence intervals

Not applicable in the statistical sense. Every pre-registered quantity is a count or an
identity over the whole released population (no sampling), and each derived baseline is an
order statistic of the complete list of released first-session completions for that level,
preserved in full in `human_baselines.json` (`per_participant_best_counts_sorted`). The
population per level ranges from N = 2 (bp35 level 9, sp80 level 6, where the pre-registered
upper median is simply the larger value) to N = 40 (lp85 level 1); the referee's re-derivation
reproduced every N. The two-invocation identity is exact (byte-identical compared files), so
there is no run-to-run dispersion to report. Where a later gate needs an interval for a human
statistic it must compute it from the preserved lists and cite the digest
`1e841bf53ba5450d506e8605cf168e6e4894520953171ae552e115a03b181185`.

---

## 8. Strongest baseline, ablations, compute comparison, standing threats

- **Strongest comparator:** the official platform baselines in the 25 cached `metadata.json`
  files (pinned by the cache manifest `02372647...`). They are not an input to the derivation:
  `derive_table` calls `derive_level_baselines(sessions, levels_per_game)` on the replay
  sessions alone and joins the official value afterwards for the comparison columns, and the
  referee's independent parser never read them. The derived numbers match this comparator on
  170/183 levels. No mechanism baseline is mandated (`mandated_baselines: []`).
- **Ablations (referee-computed, not pre-registered):** (i) under the alternative reading that
  the opening record is an issued action, 0 of the 25 level-1 rows would equal the official
  value, against 23 under the applied reading; levels 2 and above are unaffected by that
  reading. (ii) Removing the two lp85 recordings that a two-play card marks as second plays
  (section 9(d)) leaves the lp85 level-1 upper median at 18 (N 40 -> 38). (iii) The RHAE
  vectors' `alternative_form_values` (superseded formula, min-then-square, uniform weights,
  zero-based weights, no completion cap, sum or level-weighted mean over environments) are all
  distinct from the expected values the toolkit reproduces, so a wrong ruler cannot pass by
  coincidence.
- **Compute comparison (PROPOSAL_v2 section 11, compute confound):** not applicable. There is
  no treatment/control pair; the two runs are identical invocations at 97.29 s and 98.29 s
  against a 600 s limit, with `action_budget 0`, `simulation_budget 0`, `token_budget 0`.
- **Baseline implemented too weakly to lose (T12 family):** the analogue at a data gate is a
  reproduction check that could pass trivially. It cannot: the verifier requires the digest set
  of every file read to equal the committed manifest, the nine hash-locked derivation vectors
  pin the rules before the data existed, and the referee re-derived all 183 values from the raw
  bytes with independent code. The one reading fixed after the data was seen (the opening
  record) is dictated by the toolkit source, not by the data: `arc_agi.scorecard.Card`
  (`scorecard.py` lines 692-722) opens a play at 0 actions in `inc_play_count` and adds 1 only
  in `inc_reset_count` and `inc_action_count`, so the play-start RESET frame is not an action.
- **In-context substitution for persistent state (T10):** not applicable. E020 makes zero model
  calls (`model_identifier null`, `model_calls 0`), has no persistent state and no learning.
- **Priors, not plasticity (T11):** not applicable to a data gate; noted that the derived human
  statistics are reference data, not an evaluation signal, as `docs/EVIDENCE_ARC.md` section
  1.4 already states.
- **Renamed existing method (T12):** not applicable; no mechanism exists at G2.

---

## 9. Failure analysis, the C5 self-review weighed, and the four open risks

**No check failed** in the gate's history: the first and only verifier report was PASS 19/19 on a
clean tree (2de14e7), reproduced by the referee.

**C5 argument A (opening-frame accounting fixed after the schema survey).** Refuted, and the
referee's refutation is stronger than the builder's: the toolkit source settles the accounting
independently of the data (above), the referee's attribution equals the toolkit's own
`actions_by_level` in 325/325 recordings, and the alternative reading would give 0/25 level-1
agreements. The lp85 and vc33 differences are not an offset: official minus derived across
lp85 levels 1-8 is -1, -1, -12, -7, +2, 0, -31, +28.

**C5 argument B (stem matching hides a version mismatch).** The builder's refutation is
**incomplete**. It compared the frame-level `data.game_id` with the cached `metadata.json`
`game_id` and found all 25 equal (`input_manifest.json` `replay_game_ids_by_stem`, confirmed by
the referee). But every recording also carries a client-side id in
`data.action_input.data.game_id`, and for **15 games** that id names a different version:
ar25 e3c63847, cn04 65d47d14, dc22 4c9bff3e, ka59 9f096b4a, m0r0 dadda488, r11l aa269680,
re86 4e57566e, s5i5 a48e4b1d, sc25 f9b21a2f, sk48 41055498, sp80 0ee2d095, su15 4c352900,
tn36 ab4f63cc, tu93 2b534c15, vc33 9851e02b (frame-side: 0c556536, 2fe56bfb, fdcac232,
38d34dbb, 492f87ba, 495a7899, 8af5384d, 18d95033, 635fd71a, d8078629, 589a99af, 1944f8ab,
ef4dde99, 0768757b, 5430563c). This is exactly the list of 15 games whose Hugging Face copy
(revision dated 2026-04-02) differs from the local cache (ledger G2.1 literature entry), and
the client-side ids are the Hugging Face ones. The recordings are dated 2025-11-10 (ar25) to
2026-03-20 (cn04, dc22, m0r0, tr87), all before that snapshot, so the humans' clients
requested the versions that were current at the time and the frame-side ids name versions
that appeared later. Whether the frames and `levels_completed` were regenerated on the newer
versions or only relabelled cannot be decided from the files. What can be said: 13 of the 15
affected games reproduce the official baselines exactly, vc33 does not, and lp85 (client and
frame ids both 305b61c3, not in the list) does not either. The ledger G2.8 decision (c) states
that both lp85 and vc33 are among the 15; lp85 is not.

**C5 argument C (P1/P2 accounting).** Confirmed; the two "disagreeing" files are read in (d).

**The four risks the C5 review left open:**

**(a) Official versus derived baselines for lp85 and vc33.** Confirmed as real by the referee's
independent re-derivation (identical numbers) and as not an artifact of accounting (above).
The pre-registered handling applies exactly as written: `official_agreement_report` makes
agreement observed, not thresholded; `canonical_scoring_baseline` keeps the official
`metadata.json` value as `h` in every RHAE computation from G2 onward; the derived table is the
reproduction check and the source of per-level distributions. The pre-registered prediction is
met for 23 games and falsified for 2, and the pre-registration's own alternative explanation is
the finding: the platform aggregated sessions that were not released, or a rule that differs
from the documented one. Two facts point to the population rather than the rule. lp85 has 54
released sessions recorded over two months (2025-12-03 to 2026-01-30) while every other game has
10-15 sessions inside a 1-5 day window and the study describes exactly ten members of the public
per environment; and for vc33 level 3 the official 44 is not among the eight released values.
For vc33 the version-field discrepancy above is an additional live candidate; for lp85 it is
not. Effect on the gate: none. Effect on later gates: section 12, items 1 and 3.

**(b) Participant identity absent.** True in every record, in the closing scorecard, and in
the only other released file (`extras/testing_feedback_ratings.csv`: 144 rows of
`session_id, game_id, fun, hard`, every `session_id` a recording uuid, no participant column).
The pre-registered default ("every replay unit is a distinct participant's first session",
`first_run_rule`) was applied as written and recorded (`participant_ids_available false`,
`participant_present false` on all 342 log lines). The only in-data ordering signal is the
scorecard's play list. Three recordings sit in a two-play card, and in all three the first play
has 0 actions and its guid is not a released recording: lp85 `17f1dce5` (card `actions [0, 32]`,
first-play guid `bf34b3dc...`), lp85 `ab38af90` (`actions [0, 368]`, no `guids` field), tn36
`0268d6a8` (`actions [0, 498]`, first-play guid `59e160e8...`). No released recording is
therefore demonstrably a non-first playthrough, and removing the two lp85 files changes no
derived value. The residual risk is stated plainly: if one person recorded several lp85
sessions on different days nothing in the release can detect it, and the lp85 population is
demonstrably not the study's.

**(c) `git_dirty true` in both run manifests.** `git_state.txt` in each run lists exactly
` M state/PROJECT_STATE.json` (plus, in run B, the untracked artifact directory run A had just
created). The referee confirmed `git diff --stat 8efe71c 9e66b0d -- src configs scripts tests
experiments pyproject.toml uv.lock` is empty, so the code at the graded commit is
byte-identical to the code that produced the runs; the dirty file is a state file no runner
reads; `git_status_clean` was measured at verification time on a clean tree; and
reproducibility is established by the cross-invocation identity, as
`known_conflicts_at_authoring` said it should be. The human's G2.5 answer moved the supervisor
counters to gitignored `state/counters.json`; the trailing-newline rewrite of
`state/PROJECT_STATE.json` is a residual supervisor behaviour outside the agent's reach. Not a
defect of the artifacts.

**(d) The P2 read of the two ragged lp85 cards.** Both cards report `total_plays 2` with one
`actions_by_level` list. `17f1dce5` (sha256 `352d588dd12f8b4ceda7c9fbf8953cbd9dfd9c57e45b1719318102870d6bdb5b`,
34 records, guid matches play index 1): pair list `[[1, 11]]`, referee step-log count for
level 1 = 11. `ab38af90` (sha256 `83ce2dc02d41bd1080043254f297478cc4a08bc8f0e849cb5c5a6bb07b883af5`,
370 records, chosen as last play): pair list `[[1,32],[2,54],[3,80],[4,98],[5,122],[6,175],[7,232],[8,368]]`,
referee counts 32, 22, 26, 18, 24, 53, 57, 136, equal to the pair differences. The loader
indexes the pair list by play as `EnvironmentScorecard._raw_scores_from_card` does (play 1 is
beyond the single list, so P2 reads as empty) and logs the disagreement without repairing it;
P2 feeds no derived number and the P1 values, which do, are confirmed. The builder's phrase
"nesting-depth read" is imprecise: the pair list is not nested deeper, the card simply has
fewer pair lists than plays, which `Card.inc_play_count` cannot produce on its own and which
therefore reflects server-side card handling outside the toolkit code path. Diagnostic only.

**Substrate observations (not failures).** The 23 older-format recordings (cn04 12, tr87 4,
m0r0 3, dc22 2, lf52 2) carry string action ids and label their opening record with a real
action; their per-level counts still equal the card pairs, and the card's action total exceeds
the step log by one at the end of the play, not the start. Two sb26 cards report three fewer
actions than the step log. Neither feeds a derived number. The release holds 342 recordings
and 1,626 first-reach level completions in 302 recordings with at least one completion (40
have none), against the report's 340 sessions and 1,614 completions; the two recordings in
`raw/` absent from the nested zip are `g50t/373cfc77` and `g50t/d2aef7cd`.

---

## 10. Discrepancies between the dispatch brief, the ledger, and what the referee found

1. C5 argument B is recorded as "refuted for every game"; it is refuted only for the frame-level
   id. The client-side id differs for 15 games (section 9). The conclusion the builder drew from
   it (the replays were recorded on exactly the cached versions) is not established.
2. Ledger G2.8 decision (c) places lp85 among the 15 version-drift games; it is not.
3. The C5 description of the ragged cards as a nesting-depth artefact is imprecise (section 9(d));
   the operative conclusion (diagnostic only, P1 confirmed) stands.
4. The additions-only `docs/EVIDENCE_ARC.md` entries that `carry_forward_from_g1_verdict` item 2
   pre-registers for this gate (sections 1.4, 2, 6 item 6, citing the E020 digests) have not
   been written: the file is unchanged since 3fe3298. They are not a threshold; the state file
   schedules them after the verdict. Section 12 makes them the next action.
5. The brief's C5 hand recount covered lp85 level 1 only; the referee's re-derivation covers all
   183 levels and all 342 files, and agrees with the builder on every one.
6. Everything else in the brief (run ids, every digest in section 1 and section 4, commits
   3fe3298 / 659fb69 / 2de14e7 / 9e66b0d, the verifier digest `df560de6...`, the report digest
   `4bfccdb5...`, the manifest digest `08ea6ef9...`) matched what the referee computed.

---

## 11. Novelty implications

None. G2 is infrastructure; no mechanism, claim or manuscript statement rests on it. Two findings
of general interest belong in the evidence base with dates and these digests, not in a
contribution list: the released human dataset does not reproduce the platform's official
baselines for lp85 (7 of 8 levels) and vc33 (6 of 7 levels) under the documented rule while
reproducing them exactly for the other 23 games; and the recordings name, for 15 games, a
client-side environment version that differs from the frame-side version and from the version
the project cached.

---

## 12. Decision, pass-rule evaluation, and the single permitted next action

All 38 pre-registered thresholds are met on the raw artifacts as re-derived by the referee, the
pre-registration and the verifier were fixed before any data or result existed, and the derived
table was reproduced value for value from the raw bytes by independent code. G2 has no
mechanism and no pass rule beyond its exit predicate (RHAE synthetic-vector test, baselines for
at least 80 percent of the 183 levels, the dataset obtained with provenance); the predicate
evaluates true.

Verdict: GO

**Single permitted next action:** record this verdict (file and digest) in the ledger and
`state/PROJECT_STATE.json`, mark G2 passed at graded commit 9e66b0d, and make the next advancing
commit the additions-only `docs/EVIDENCE_ARC.md` entries this gate pre-registered
(`carry_forward_from_g1_verdict` item 2: section 1.4 dataset location, counts and recorder
format; section 2 the 170/183 agreement and the lp85/vc33 values; section 6 item 6 resolved),
each citing the run A digests in section 4 and recording discrepancies 1-2 of section 10 with
the client-side version list. Only after that commit exists may G3.1 open by authoring
`preregistration/G3.yaml` from PROPOSAL_v2 section 9 row G3.

**Items the G3 pre-registration must hash-lock rather than remember:**

1. Every RHAE computation uses the official `metadata.json` `baseline_actions` as `h`
   (`canonical_scoring_baseline`), read from the cache pinned by
   `experiments/environment_cache_manifest.json` (`023726479a3c201161a61ee0d310b20696988933adbf1826dc9d7bd524d960af`);
   the derived table `human_baselines.json` (`1e841bf53ba5450d506e8605cf168e6e4894520953171ae552e115a03b181185`)
   is cited by that digest wherever a per-level human distribution is used, and any use of its
   lp85 or vc33 rows must carry the section 9(a) caveat.
2. The per-level action budget is 5 times the official `baseline_actions[l]`
   (`action_budget_multiplier_for_later_gates 5`), and the budget design must read
   `g1_termination_vs_budget.json` (`82c592f0ef357e337f7aefa62a9b297a86d39e15eaaef810a5d8c86b29095f5f`)
   rather than re-measure it.
3. G3 runs the cached environment versions and must name them; it may not cite the human
   replays as evidence about a version other than the frame-side one, and must record that for
   15 games the replays' client-side version differs (section 9, argument B).
4. Participant identity is absent from the release; any per-participant claim drawn from the
   replays is per-session, and lp85's 54 sessions are not the study's ten-participant population.
5. Any G3 threshold that depends on throughput states step-only or all-in (G1 verdict item 3,
   carried unchanged: 1577-1640 versus 777-823 fps on this machine).
6. Any project-produced number cited in an evidence document is backed by a preserved artifact
   under `artifacts/` with a `SHA256SUMS` entry (G1 verdict item 2, carried unchanged); the
   referee's own `/tmp` re-derivation is cited here by digest and is not a substitute for that.
