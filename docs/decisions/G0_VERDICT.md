# Verdict: Gate G0 (Bootstrap)

**Verdict: GO**

Issued by the referee subagent (read-only tools; `Write` limited to `docs/decisions/**`) on
2026-09-04 against repository commit `72edbaeea2cdfccaf1e64efbeeeb51ccda0dedba`, working tree
clean (`git status --porcelain` empty, observed by the referee). Every digest below was computed
by the referee with `sha256sum`; the builder's `SHA256SUMS` files were compared against those
digests, not trusted. Every number produced by this project that appears here carries the path
and digest of the file it was read from (constitution C4).

---

## 1. Governing pre-registration

`preregistration/G0.yaml`
SHA-256 `c91c197a0eab9764a67a2fbeeb0771825c95d8d294388c3eb6fe166f4f1f4620`

Thresholds applied (all read from that file; none from prose):

| threshold | value |
|---|---|
| `uv_sync_exit_code` | 0 |
| `pytest_exit_code` | 0 |
| `pytest_min_tests_collected` | 1 |
| `ruff_exit_code` | 0 |
| `mypy_exit_code` | 0 |
| `determinism_identity_min` | 1.0 |
| `contrast_seed_must_differ` | true |
| `sha256sums_verified_fraction_min` | 1.0 |
| `sha256sums_must_list_every_artifact_file` | true |
| `git_status_porcelain_lines_max` | 0 |
| `licence_required_text` | "MIT No Attribution" |
| `verify_on_machine_items_total` / `_resolved_min` | 8 / 8 |

Determinism protocol: seed 12345 twice identical, seed 12346 once and must differ; exclusions
sourced from `configs/nondeterministic_fields.yaml` and bounded to four categories (run
identifiers, timestamps, durations, host/hardware descriptors), with metrics, results, seed,
hashes, commit and record streams forbidden from exclusion.

**Timing of the pre-registration (C1).** The file's `authored_utc` reads `2026-09-04T06:05:00Z`;
the ledger entry that records writing it is stamped `05:54:21Z`
(`state/LEDGER.jsonl` line 11, file SHA-256
`0c46b86b4ed70d9096538ca67197426d8d6feda769a2d1869327ca01bb8a3887`). Neither timestamp is
machine-stamped: both were typed by the agent. The machine-stamped facts are these. The file has
exactly one commit in its git history, `4796945` at `2026-09-04T02:04:30-04:00` (= 06:04:30Z),
made by the human. The working tree is clean, so the file on disk is that committed blob, and
its digest equals the digest the ledger recorded at authoring. The first G0 artifact was
created at `06:59:56Z` (`artifacts/E000_bootstrap/20260904T065956Z_seed12345_60af959c/manifest.json`,
SHA-256 `e4aaa55ed20390cc63219f69aac5c6084bae6389f56aa953b0bd61f87267fca5`, field
`timestamp_utc`). The verifier's digest was recorded in the ledger at `06:44:21Z` (line 23) and
the exclusion config's at `06:06:49Z` (line 18), both after the pre-registration's commit and
before any artifact. `authored_utc` is therefore a clerical error (it post-dates the commit by
30 s, which is impossible for a write time) and it is immaterial to C1: on machine-stamped
evidence alone the honest window closed at least 55 minutes before the first result existed.
Judgement: does not matter for this verdict; recorded in section 9 as a provenance defect in
how the agent stamps time.

---

## 2. Original hypothesis

G0 carries no scientific hypothesis (`preregistration/G0.yaml`, `hypothesis`; `mechanism: none`;
`mandated_baselines: []`; `revision_limit: 0`). The claim under test: the laboratory is
reproducible and self-checking. A seed-fixed experiment run through the single canonical entry
point yields `results.json` and `metrics.csv` that are byte-identical across invocations once the
pre-declared nondeterministic fields are excluded, a different seed yields different results,
every artifact is hash-verifiable, and the code base passes lint, type and unit checks from a
clean tree. Governing predicate: `PROPOSAL_v2.md` section 9, row G0.

## 3. Pre-registered prediction

`determinism_identity` = 1.0 over `results.json` and `metrics.csv` for two invocations of
`E000_bootstrap` at seed 12345 after excluding exactly the fields in
`configs/nondeterministic_fields.yaml`; the seed-12346 run differs; every SHA256SUMS entry
verifies and every file is listed; `uv sync`, `pytest` (>= 1 test), `ruff`, `mypy` all exit 0;
`git status --porcelain` empty; LICENSE contains "MIT No Attribution"; all 8
`[VERIFY-ON-MACHINE]` items in `docs/EVIDENCE_TOOLING.md` section 11 resolved, where resolved
means an observed value with date and source, or a dated explicit statement that the value could
not be observed and why.

---

## 4. Experiments completed

Three runs of `configs/experiments/E000_bootstrap.yaml`
(SHA-256 `d1458f0797b22ced2b8ac534f1f9fe9b315d23102c618587b8e5568d0afecb09`; runner
`smoke_toy_grid`, `wallclock_limit_seconds: 600`, `network_calls_allowed: 0`,
`model_calls_allowed: 0`, `action_budget: 64`) through `scripts/run_experiment.py`. Every
manifest records `git_commit ab89404fd32e79cd96b6831a3be8bff4bb46b117`, `git_dirty true`,
`network_attempts 0`, `model_calls 0`, `model_identifier null`, `prompt_hash null`,
`python_version 3.12.13`, `dependency_lock_hash cc86c9444379162b5bdffbb9d88efd3415cc6398e62617b236e18c75edd84a22`
(referee-computed `sha256sum uv.lock` = the same value), `completion_status completed`.

## 5. Raw artifact paths and referee-computed digests

All paths relative to `/home/afazeli2006/ARC_AGI3_Plasticity_Lab/`. 39 artifact files are
tracked in git (`git ls-files artifacts/E000_bootstrap | wc -l` = 39). `sha256sum -c SHA256SUMS`
in each run directory: every line `OK`; no file present that is not listed.

### Run 1: `artifacts/E000_bootstrap/20260904T065956Z_seed12345_60af959c/` (seed 12345)

| file | SHA-256 |
|---|---|
| SHA256SUMS | `22a039ab232610ec215d2c7ff425fbf2a94408269fa030ab9a43d940f83bc824` |
| results.json | `2b513c30017458555bf1df0ba6680ef5faa1b723bedfdcf7c55d760ed2951e9d` |
| metrics.csv | `ea74d4c8bc6c560a615097bc57dadc3a77cf60830c7e3636740d2885b23b8081` |
| manifest.json | `e4aaa55ed20390cc63219f69aac5c6084bae6389f56aa953b0bd61f87267fca5` |
| resolved_config.yaml | `3f2d0f3353fcad2422a2d6ae4dc63d4e4c72a36955c5ea030ed90d152ab5cb87` |
| environment_results.csv | `192c3ce63b600c23c1dfd8ef63390357a3fc17d5251af8cf98021089e90c79e4` |
| transitions.jsonl | `52f497cf7c1fa1107ff68d9fadbb1497f5a626938e058b34256295a2d6c103d4` |
| stdout.log | `26d36e7524d0416ead744ad06edc8dbf35e3c8c84663d98c07838142665f1b2e` |
| stderr.log (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| git_state.txt | `7a3f7b41b4401060b11023357832f4cf6c9e6fc3ee5955872b09edb47c53fecc` |
| environment_info.json | `74638d412a3a60ba666d0434d1f5c3deb2551f25bf691fa4f9026adf91f8bd06` |
| hypotheses.jsonl (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| memory_operations.jsonl (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

### Run 2: `artifacts/E000_bootstrap/20260904T065957Z_seed12345_47bf07b9/` (seed 12345)

| file | SHA-256 |
|---|---|
| SHA256SUMS | `3b7f9be2dde210a0508846d6bcc292cd6f7d861fb97ba832f0e673a267b2b94b` |
| results.json | `6dda912a8874d4c7c25ab9c47ade5e266083d2f0d0cda96975b7fa4a0eb1cbe0` |
| metrics.csv | `ea74d4c8bc6c560a615097bc57dadc3a77cf60830c7e3636740d2885b23b8081` (identical to run 1) |
| manifest.json | `d3e023562e1688d4cadba7348e91a8447131ce7c68f993363d3bfacdb2160629` |
| resolved_config.yaml | `3f2d0f3353fcad2422a2d6ae4dc63d4e4c72a36955c5ea030ed90d152ab5cb87` (identical to run 1) |
| environment_results.csv | `192c3ce63b600c23c1dfd8ef63390357a3fc17d5251af8cf98021089e90c79e4` (identical to run 1) |
| transitions.jsonl | `52f497cf7c1fa1107ff68d9fadbb1497f5a626938e058b34256295a2d6c103d4` (identical to run 1) |
| stdout.log | `c974705f55615a789fae23acadaa11b03fc8da5498957c2c7205964ed4401ebc` |
| stderr.log (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| git_state.txt | `0d6b5083c660ecee7fd51ec4fed21dce3642c3bf43aad4715d3fb90ad251d972` |
| environment_info.json | `6e28b86e20ec1aac50f2a6195b8253ba101f5afde4a24e9e609d29156a7ec635` |
| hypotheses.jsonl, memory_operations.jsonl (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

### Run 3: `artifacts/E000_bootstrap/20260904T065957Z_seed12346_ba50299f/` (contrast seed 12346)

| file | SHA-256 |
|---|---|
| SHA256SUMS | `77a869fd43659b9c9eca427696a87a013933f96bcd30ee83b899ebf512cfb6ca` |
| results.json | `d39ca158f24230fde0cd24d10b260dc5b9b530942479539a3970ea3e51ab0d62` |
| metrics.csv | `328b94fbce704f838e3dda1f2acbe4ab3a495f04b8d9e25191392725cdcc3523` |
| manifest.json | `7c3eb6332d1649dfb586caaee72c31bd3f83804df263b9408eb3e27f125e0a65` |
| resolved_config.yaml | `ce51104856b9e54a4e85e15bbc269fbb0576cae9d0b597f6acb497e012262b1e` |
| environment_results.csv | `7a8ba41d3c23f515ab6147f2ecc529f53fe839a047d3f232a331d33aa1ed0271` |
| transitions.jsonl | `9a2513dbe58d7dccc47f0ef73c8bd254950d78b94a9a7e50e4deb55fec831130` |
| stdout.log | `0270ee1a7b735da6fbe07941471bd8913989923c73cbbf1be0bccd7846b4858f` |
| stderr.log (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| git_state.txt | `0d6b5083c660ecee7fd51ec4fed21dce3642c3bf43aad4715d3fb90ad251d972` |
| environment_info.json | `408746cfd086afeb792b0b12d482b9a26857b9b1b6ef067956ff0b32b5405cdf` |
| hypotheses.jsonl, memory_operations.jsonl (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

### Control-surface, config, code and derived files

| file | SHA-256 | note |
|---|---|---|
| `preregistration/G0.yaml` | `c91c197a0eab9764a67a2fbeeb0771825c95d8d294388c3eb6fe166f4f1f4620` | governs |
| `scripts/verify_run.py` | `07fe047d046748634450e9140e6f834675b4b8f0993cd8204ce520fb51865466` | equals the digest the ledger recorded at 06:44:21Z, before any artifact |
| `configs/nondeterministic_fields.yaml` | `cd412e291aaf8689555f0884fd6507e1888ef97989a0b4eda7eaf77f145d0983` | |
| `configs/experiments/E000_bootstrap.yaml` | `d1458f0797b22ced2b8ac534f1f9fe9b315d23102c618587b8e5568d0afecb09` | |
| `state/verify_G0.json` | `7bacb38c7cf0c8faea18fbe0fa59db84c7fb3522fc297add0f5e5d0c58fb3e05` | derived; builder's report, not relied on |
| `state/c5_probe_G0.json` | `76388087e3a88a404abde137ed2550425f4c5b63fb01021dfd773994513f5459` | derived; builder's report, not relied on |
| `scripts/c5_probe_G0.py` | `2bee8327bcb852844761c41027aaf2129f6a0d15c40e6b9d84b6649758936294` | |
| `tests/regression/test_c5_g0_exclusion_nesting.py` | `e1547f1b7b607346ab0717e3035439cae3c337b96a7855f7822d8c66ef60ad4d` | |
| `tests/unit/test_verify_run.py` | `a9c59b9d616c700cd0fd27306269e2b041a4c06f323a91a8934db27cb2107de4` | |
| `tests/integration/test_control_surface_hook.py` | `bac67b22831eb32fa2731c23dc1612885f205e3ef65353ccb4b2378e1bc7d7a0` | matches the digest cited in section 11 item 5 |
| `scripts/run_experiment.py` | (unchanged since ab89404; see section 8, argument B) | |
| `src/arc_plasticity/environments/toy.py` | `91a8bf50ef1634d6787c63c6c9c1fd22dc779fe3f16758fef0de7bf77c540c43` | |
| `src/arc_plasticity/core/config.py` | `0074b2e57d0845a4d9a8fa5c28be07f60707ee6109a92f501e7071c680dc7379` | |
| `src/arc_plasticity/core/guards.py` | `f11c81d06d69b2b7cb11fd830590340906518cfeea366683c290b7d20fe2d3e9` | |
| `uv.lock` | `cc86c9444379162b5bdffbb9d88efd3415cc6398e62617b236e18c75edd84a22` | equals every manifest's `dependency_lock_hash` |
| `LICENSE` | `9fcfafab9ac0559c961f9cc4c1e23f176fb35d58a546f6d2ed01164efa9fe346` | first line "MIT No Attribution" |
| `docs/EVIDENCE_TOOLING.md` | `879cb79792450696e3c778d04bf6b2a953849d73bdb9751c451e1dcd98de6e7e` | 20728 bytes |
| `.claude/hooks/protect_control_surface.sh` | `98d97a591e5b4dd2b36e34f0fea74d5f459d7a7f6ae122a53248f8936ab48986` | equals the pin in `state/PINNED_HASHES.json` |
| `state/PINNED_HASHES.json` | `a79e4694153f1340c627e6bcfdcb4fd34b629a7ef5e42ac2726f65e445d1b499` | gitignored, local only |
| `state/LEDGER.jsonl` | `0c46b86b4ed70d9096538ca67197426d8d6feda769a2d1869327ca01bb8a3887` | 33 lines |
| `state/PROJECT_STATE.json` | `092f443235d5681a37c413430e7db1ade611534301c777d49ab615589480aca8` | |
| `.gitignore` | `7f9ddc4de789170c66456c8a7c6fde6df83f20ab63c31fe180782a01f3f762bb` | |
| `status.sh` | `8e303b2b51be8fb09d6abd5bb923b4a569e5b152fee17505e3af21cd757ccc70` | |

Untracked (gitignored) telemetry that section 11 items 2 to 4 cite, digested by the referee at
verdict time so this file is the durable record of what was observed:

| file | SHA-256 |
|---|---|
| `state/supervisor.jsonl` | `e542af1581a0f71ec9c9eeebd95d1e17f2224864ad0459106cb0a0c2f5196dab` |
| `state/supervisor.out` | `d1a9cfc78264779f0aa31e5183643b6bddf5f3263f99d90c0fbd0489b4f1c03f` |
| `state/tool_errors.jsonl` | `7d677f5e90745289639f8c90e28407de7971d0508362e39ebb2993035f6938e5` |
| `state/escalations/20260904T055252Z.md` | `ab69daf91ff36e4236d6a69733432a0e4a97ecd78497250004845e45de942739` |
| `state/escalations/20260904T060506Z.md` | `6f497b3d2b9f0f75a70769f20278aa2e97409cc48222f46eeafffc70f45e248a` |
| `state/escalations/20260904T063044Z.md` | `d3fb31cc75d0873a659ea5f70beda02246f66f027371030920805a4a206e5b5b` |

---

## 6. Primary results

### 6.1 Verifier, run by the referee

Command: `uv run python scripts/verify_run.py --gate G0` (the literal `python` is not on this
shell's PATH; `uv run python` resolves to `.venv/bin/python`, CPython 3.12.13, the same
interpreter the manifests record). Output, read in full:

```
PASS gate=G0 prereg_sha256=c91c197a0eab9764a67a2fbeeb0771825c95d8d294388c3eb6fe166f4f1f4620 checks=12/12 skipped=0
```
exit status 0. Per-check observed values from that output:

| check | observed | threshold | result |
|---|---|---|---|
| nondeterministic_fields_within_bounds | 15 names, 0 problems | 4 allowed categories, 10 forbidden tokens | pass |
| run_artifact_completeness | 3 runs, 0 problems | 13 files, 19 manifest keys | pass |
| sha256sums_verify | listed 36, verified 36, fraction 1.0 | 1.0, must list every file | pass |
| determinism_identity | identity 1.0, contrast_differs true | 1.0, true | pass |
| git_status_clean | 0 lines | max 0 | pass |
| licence_text | "MIT No Attribution" | same | pass |
| verify_on_machine_resolved | 8 total, 8 resolved, unresolved [] | 8 / 8 | pass |
| uv_sync_exit_code | 0 ("Checked 43 packages") | 0 | pass |
| pytest_exit_code | 0 ("91 passed in 1.35s") | 0 | pass |
| pytest_min_tests_collected | 91 | 1 | pass |
| ruff_exit_code | 0 ("All checks passed!") | 0 | pass |
| mypy_exit_code | 0 ("no issues found in 17 source files") | 0 | pass |

The builder's committed report `state/verify_G0.json` (digest above) shows the same 12/12 with
89 tests; the difference of two is the regression test file added at commit 72edbae. It was not
relied on.

### 6.2 Determinism identity confirmed in the raw data by the referee

Read directly from the two seed-12345 `results.json` files (digests in section 5): they differ
in exactly three top-level scalar fields, `run_id`, `created_utc` (`06:59:56Z` vs `06:59:57Z`)
and `wallclock_seconds` (`0.021511332015506923` vs `0.01345602801302448`), all three in the
pre-registered exclusion categories. Every other field is equal: `completion_status completed`,
`config_hash 6f700dc8dc427ad73a70fae39e964fcbe619bae5f3cdc6d6b518d912058eb30a`,
`experiment_id E000_bootstrap`, `extra {}`, `seed 12345`, and the `results` block
`{cells_visited 11, environment_generator_version toy-grid-1.0.0, goal [1,6], grid_size 8,
optimal_steps 6, solved true, start [5,4], steps 12, total_reward 1.0}`. `metrics.csv` is
byte-identical (same digest `ea74d4c8...`, rows steps 12 / solved 1 / total_reward 1.0 /
cells_visited 11 / optimal_steps 6). Stronger than the predicate requires,
`environment_results.csv` (`192c3ce6...`) and `transitions.jsonl` (`52f497cf...`, 12 records) are
also byte-identical across the two runs.

Contrast run (seed 12346, `results.json` digest `d39ca158...`): `config_hash
6bd7ce9e351f1c953ae47681c2fa90475f5307ac5a375163bd325c1005787603`, `start [4,3]`, `goal [3,6]`,
`steps 4`, `optimal_steps 4`, `cells_visited 5`; `metrics.csv` digest `328b94fb...`;
`transitions.jsonl` has 4 records. Every result field differs from the seed-12345 runs, so the
identity is not achieved by a seed-ignoring implementation. Source of randomness confirmed by
reading `src/arc_plasticity/environments/toy.py`: a single `numpy.random.default_rng(config.seed)`
drives start, goal and the 0.7-greedy policy.

### 6.3 Exclusion config against the pre-registration bounds

`configs/nondeterministic_fields.yaml` declares four groups, `run_identifiers` (run_id, guid,
session_id), `timestamps` (created_utc, started_utc, finished_utc, updated_utc, timestamp_utc),
`durations` (wallclock_seconds, elapsed_seconds, duration_seconds), `host_descriptors`
(hostname, hardware, python_executable_path, pid). Each group maps to one of the four allowed
categories in `preregistration/G0.yaml` lines 64 to 68; none of the 15 names is a metric, result
value, seed, config/prompt/lock hash, git commit, or a record stream. The `never_excluded` list
reproduces the pre-registration's forbidden categories verbatim. `compared_files` is exactly
`results.json` and `metrics.csv`. Within bounds.

### 6.4 VERIFY-ON-MACHINE items, judged individually

`docs/EVIDENCE_TOOLING.md` section 11 (digest above); `git diff --numstat d97f638 HEAD` on the
file shows 54 insertions, 0 deletions, so the append-only rule held. Each item against the
pre-registered definition of resolution:

1. `--effort` value set. **Resolved**: observed value `low, medium, high, xhigh, max` from
   `claude --help` on 2.1.260, dated, source named (ledger line 29). The referee confirmed
   `claude --version` = 2.1.260. Corrects the section 2 row listing `ultracode` without
   deleting it. Meets the definition.
2. Status line in headless `-p`. **Resolved (negative)**: `state/usage.json` absent; referee
   confirmed absent now. Cited "8 completed turns, 6 of 6 banners `[gauge: none]`"; referee
   counted 9 `turn` events in `state/supervisor.jsonl` and 7 of 7 banners in
   `state/supervisor.out` (one more turn since the item was written; consistent). Meets the
   definition.
3. Rate-limit failure signature. **Not observable, dated, reason given**: no genuine limit has
   occurred; the single `rate_limit` event (`06:08:38Z`, `returncode 0`) was a false positive.
   Referee confirmed exactly one such event in `state/supervisor.jsonl` and exactly two entries
   in `state/tool_errors.jsonl`, both `returncode 129` with a stdin warning, neither a limit.
   Names where the future observation will land. Meets the definition.
4. `CLAUDE_CODE_OAUTH_TOKEN` sustains headless turns. **Resolved**: the inference rests on the
   supervisor emitting a WARNING when the variable is unset and none appearing. Referee
   confirmed `scripts/supervisor.py` line 442 to 443 prints
   `[supervisor] WARNING: CLAUDE_CODE_OAUTH_TOKEN is not set` when unset, and
   `state/supervisor.out` contains zero occurrences of that string across 7 supervisor `start`
   events, while 9 turns completed. Token lifetime is honestly left open. Meets the definition.
5. `PreToolUse` hook blocks `sed -i` and redirection. **Resolved**: a permanent integration test
   (digest matches). The referee observed the hook live twice during this verdict: a read-only
   command containing `2>&1` plus a frozen path was denied, and a read-only `git show | sha256sum`
   naming the pre-registration was denied. The hook is over-inclusive as the item states. Meets
   the definition.
6. Context exhaustion in headless mode. **Not observable, dated, reason given** (longest turn
   500 s, fresh session per turn, `--autocompact` named as the lever). Referee confirmed
   `elapsed_s 500` is the maximum in `state/supervisor.jsonl`. Meets the definition.
7. Per-model allowance. **Not observable, dated, reason given** (gauge never fires; no
   non-interactive usage query). Meets the definition.
8. Installed version and platform. **Resolved**: 2.1.260, native Linux under WSL2. One
   ambiguity, not an error: the item says "Python 3.12.3", which is `/usr/bin/python3`; the
   project interpreter used for every run is the uv-managed CPython 3.12.13 (manifests,
   `environment_info.json`). Both values were confirmed by the referee. Meets the definition.

All eight meet the definition the pre-registration fixed before results existed. The three "Not
observable" items are carried forward in section 11.

---

## 7. Sections required by the verdict definition that G0 does not populate

- **Confidence intervals: not applicable.** The primary metric is a binary identity over one
  pre-registered pair of invocations, not an estimate; there is no sampling distribution to
  bound.
- **Strongest baseline: not applicable.** `mandated_baselines: []`; G0 compares nothing to
  anything and pre-registers no mechanism.
- **Ablations: not applicable.** There is no mechanism to ablate; the contrast-seed run is a
  control against a seed-ignoring implementation, not an ablation.
- **Compute comparison: not applicable.** There is a single arm with no model calls, no network
  calls, and wall-clock 0.013 to 0.022 s per run (manifests, section 5).

---

## 8. The builder's C5 adversarial self-review, judged

Source: `state/LEDGER.jsonl` lines 32 and 33 (both stamped `07:22:00Z`) and the derived
`state/c5_probe_G0.json`, which was read but not trusted.

**Argument A (a flaw in the ruler).** Confirmed real by reading `scripts/verify_run.py`
lines 179 to 190: `strip_keys` removes any key whose name is in the exclusion set, at any depth,
together with its entire value. A result nested under `hardware` (or any excluded name) would
be invisible to the identity check. The builder's claim that no graded artifact exploits this
was checked by the referee against the raw files, not the probe report: in each of the three
`results.json` the excluded names present are exactly `created_utc`, `run_id`,
`wallclock_seconds`, all top-level, all scalar; the `results` sub-object contains no excluded
name; each `metrics.csv` header is `metric,value` with no excluded column. Not exploited. The
hole is pinned by `tests/regression/test_c5_g0_exclusion_nesting.py` (digest above) so that any
verifier change surfaces. It is a defect in a ruler that was authored before results existed and
whose digest has not changed since; it did not affect this measurement. It must not survive into
a gate whose results carry nested structures: see section 11.

**Argument B (all graded manifests record `git_dirty true`).** The builder's evidence is a
re-run from a later commit; the referee cannot execute experiments and did not rely on it.
Independent check: `git_state.txt` in each run (digests above) lists the dirt exactly:
` M .gitignore`, ` M state/BUDGET.json`, ` M state/PROJECT_STATE.json`, `?? status.sh`, and
for runs 2 and 3 the first run's own output directory. The `.gitignore` change was the two-line
`!artifacts/**/*.log` negation (`git diff ab89404 64267b4 -- .gitignore`). None of these is on
the runner's code path: `scripts/run_experiment.py` reads `state/BUDGET.json` only to supply a
wall-clock fallback, and `resolve_config` (`core/config.py` lines 103 to 110) applies that
fallback only when the config omits a limit; `E000_bootstrap.yaml` declares 600 s and every
`resolved_config.yaml` records 600. Further,
`git diff --stat ab89404 HEAD -- src scripts/run_experiment.py configs pyproject.toml uv.lock`
is empty: the code that produced the artifacts is byte-identical at ab89404 (the manifests'
commit), d6673d4 (the builder's re-run commit) and 72edbae (this verdict). The dirty flag is
truthful and harmless. The underlying cause (the supervisor edits `state/*.json` counters inside
every turn, so every in-turn run will be dirty) is a process property to carry forward, not a
defect in the artifacts.

**Argument C (not machine-testable).** Three prongs.

- *Shared authorship of verifier and pre-registration.* The constitution names this residual
  explicitly (section 7, after C2) and assigns its mitigation to C5 and to this referee. The
  referee therefore compared each threshold with `PROPOSAL_v2.md` section 9 row G0. Eight of
  the twelve are exactly the proposal's predicate (exit codes 0, >= 1 test, porcelain empty,
  MIT-0, 8/8 items). Two are stricter than the predicate: the contrast-seed requirement and the
  requirement that SHA256SUMS list every file. `pytest_min_tests_collected 1` is the proposal's
  own floor and the pre-registration states why it was not raised (test count is not a quality
  measure); the observed 91 tests across 9 test files make it non-binding. No threshold was
  drawn to fit a result: every one was committed 55 minutes before the first result. Not a
  reason to withhold.
- *A dated "Not observable" counts as resolved.* The pre-registration defines this before any
  result existed, with reasoning: a hypothesis left standing is not a resolution, but an
  explicit dated statement of non-observation with the reason is. For items 3, 6 and 7 the
  events in question (a genuine usage limit, context exhaustion, a per-model gauge) cannot be
  produced on demand without spending the allowance the constitution treats as the binding
  constraint. Forcing them would be the wrong trade. Each such line names where the future
  observation will land. The consequence is real and is carried forward: the supervisor's
  rate-limit backstop runs on an unverified signature until the first real limit. Not a reason
  to withhold.
- *No model call, so identity 1.0 says nothing about model-call nondeterminism.* Correct, and
  intended: the pre-registration set `model_calls_allowed: 0` and `network_calls_allowed: 0`
  with the stated reasoning that a G0 failure must be attributable only to the laboratory.
  `PROPOSAL_v2.md` section 9 row G0 asks for a seed-fixed smoke experiment, not a model call;
  model-call determinism belongs to the reference architecture (G3) and later. Withholding here
  would hold G0 to a claim it never pre-registered. **Judgement: C is not a reason to withhold
  the verdict for an infrastructure gate that pre-registered no mechanism.** It does bound
  what this verdict certifies: reproducibility is established for model-free, network-free runs
  of the canonical entry point, and for nothing wider.

**Standing threats of `PROPOSAL_v2.md` section 11.** T10 (in-context learning substitutes for
persistent state): not applicable, there is no model (`model_identifier null`, `model_calls 0`)
and no persistent state (`persistent_state_size_cap 0`). T11 (priors explain efficiency): not
applicable, no agent and no efficiency claim. T12 (mechanism is a renamed method): not
applicable, `mechanism: none`. The retained v1.0 compute confound: not applicable, one arm
only. A baseline implemented too weakly to lose: not applicable, `mandated_baselines: []`. These
threats attach to mechanism gates G6 onward and this verdict makes no finding about them.

---

## 9. Failure analysis

Nothing in the pre-registered predicate failed. Defects found by the referee, none of which
changes the verdict:

1. **Agent-typed timestamps are not the wall clock.** `authored_utc` post-dates the file's own
   commit; ledger line 28 (`07:02:30Z`) was committed in d97f638 at `07:01:09Z`; ledger lines 32
   and 33 (`07:22:00Z`) and `PROJECT_STATE.updated_utc` (`07:23:00Z`) were committed in 72edbae at
   `07:11:07Z`. The agent writes estimated times rather than reading `date -u`. Git commit times
   and `state/supervisor.jsonl` are the reliable clock; the verdict above relied on those. The
   builder's own note that "the ledger timestamp is authoritative" is therefore only
   approximately true. Process defect, not a gate item.
2. **Exclusion-nesting hole in the verifier** (section 8, A). Real, unexploited, pinned.
3. **Every in-turn run will carry `git_dirty true`** (section 8, B) because the supervisor
   edits tracked counters inside the turn. Cosmetic for G0; for mechanism gates it weakens
   the manifest's claim to describe a committed tree. Fixing it means changing a frozen file.
4. **The evidence for section 11 items 2 to 4 lives in gitignored files.** A fresh clone
   cannot re-derive them. This verdict records their digests at verdict time (section 5).
5. **`state/PINNED_HASHES.json` is gitignored**, so a fresh clone has no layer-2 pins, and
   `scripts/verify_run.py` is not among the five pinned files. For G0 this is covered by the
   ledger having recorded the verifier's digest before any result and the referee confirming it
   unchanged, but it is a weaker guarantee than the constitution describes.
6. **The hook is over-inclusive** (denies read-only commands containing `>` plus a frozen path).
   Costs turns; does not weaken protection.

Implementation failure versus hypothesis failure: no failure of either kind. The infrastructure
claim was tested and held.

---

## 10. Novelty implications

None. G0 is infrastructure; it makes no scientific claim, introduces no mechanism and touches
no prior-art comparison. The novelty audit is not triggered before the first mechanism gate.

---

## 11. Single permitted next action

Close G0 and open G1. Concretely, one action: record this verdict (a `verdict` ledger entry
quoting the word and this file's SHA-256; `gate_status: passed`, `last_verified_gate: G0`,
`last_verified_commit` = the commit that carries this file; commit), then author
`preregistration/G1.yaml` with the Write tool, from `PROPOSAL_v2.md` section 9 row G1 and
`docs/EVIDENCE_ARC.md`, before any G1 treatment run. That pre-registration must carry forward
the three items this verdict leaves open, so they are hash-locked rather than remembered:

- a rule that an excluded field may be stripped only when its value is a scalar at top level,
  or that a container-valued excluded key fails the gate, so the section 8 argument-A hole
  cannot be exploited in G1's artifacts (the G1 evaluator in `scripts/verify_run.py`, which
  does not yet exist, reads that rule from the pre-registration);
- an explicit statement that model-call nondeterminism is out of scope for G1 and is owed by
  the gate that first makes a model call;
- the three "Not observable" tooling items (rate-limit signature, context exhaustion,
  per-model allowance) listed as open, with the log each will be resolved from.

Nothing else is permitted before that file exists.
