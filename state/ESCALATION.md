# Escalation (turn 18): the 342 human replays cannot be obtained by the agent

Gate: G2 · Task: G2.5 · Time: 2026-09-04T08:54:30Z · Turn: 18
Constitution grounds: section 6 item 11 (a required external resource cannot be obtained;
the 342 human replays are the case the constitution names). Pre-registered in
`preregistration/G2.yaml` under `dataset_acquisition` (`named_fallback_status`,
`escalation_timing`); sha256 `f6539aa1a1ddfad220651050d88f7d73e8a7fe3d0455318f65266117720b7344`,
committed at `3fe3298`.

**How to reply: append a section to this file that begins with `## ANSWER`.** Nothing else
clears the block: not a chat message, not a file placed elsewhere on its own. The turn
protocol and the supervisor both check only for a line beginning `## ANSWER`. On finding it,
the next turn moves this file to `state/escalations/<timestamp>.md`, clears `blocked_on`,
records the answer as a `decision` ledger entry, and follows the matching branch below.

---

## 1. What is needed

The ARC-AGI-3 human dataset: 342 step-by-step human replays over the 25 public games,
released 2026-04-14 and announced at https://arcprize.org/blog/arc-agi-3-human-dataset.
G2's primary metric is the derivation of the per-level human action baselines from these
replays and their agreement with the official baselines embedded in each game's
`metadata.json` (`PROPOSAL_v2.md` section 9, `preregistration/G2.yaml` `human_baselines`).
Without the replays the gate has no data to grade and nothing I can debug produces a dataset.

Everything that does not depend on the data already exists and is tested:

| Component | Where | Verified by |
|---|---|---|
| RHAE adapter delegating to `arc_agi.scorecard.EnvironmentScoreCalculator` | `src/arc_plasticity/evaluation/rhae.py` | 8 pre-registered vectors, `tests/unit/test_rhae_synthetic_vectors.py` |
| Replay ingestion and baseline derivation | `src/arc_plasticity/evaluation/human_replays.py` | 9 pre-registered derivation vectors reproduced exactly |
| Manifest builder for the raw directory | `scripts/build_human_replays_manifest.py` | refuses on absent/empty raw dir |
| E020 runner and config | `src/arc_plasticity/evaluation/human_baseline_run.py`, `configs/experiments/E020_human_baselines.yaml` | integration test, two runs on a synthetic world, all 14 non-tooling G2 checks pass |
| G2 evaluator | `scripts/verify_run.py` `evaluate_g2` | unit test with a failing mutation per data check |

`uv run pytest -q` reports 245 passed at commit `1767414`; `ruff check` and `mypy` are clean.

## 2. What was tried (ledger `literature` entry, G2.1, 2026-09-04)

- https://arcprize.org/blog/arc-agi-3-human-dataset links the dataset only through the
  shortener https://dub.link/vfwCqvb. It answered HTTP 429 and then 403 to the WebFetch tool.
  The resolved location is unknown from this machine.
- https://huggingface.co/datasets/zarczynski/arc-agi-3-public, the fallback named in
  `PROPOSAL_v2.md`, holds only `environment_files/` for the 25 public games (revision
  `f5757d68c2589be59b3119b6ed9fc6b652aff937`, last modified 2026-04-02, before the release).
  No replay data.
- https://docs.arcprize.org/llms.txt lists no human-dataset page. The `arcprize` GitHub
  organisation has no repository for it (`arc-agi-3-benchmarking` holds recorder code only).
- The agent shell has no network permission: a `curl` probe was denied on 2026-09-04.
  The Hugging Face cache on this machine is empty and no file matching replay, human_baseline
  or arc-agi-3-public exists under `/home/afazeli2006` to depth 5.

## 3. The acceptable answers

**(A) You place the files.** Resolve https://dub.link/vfwCqvb in a browser, download the
dataset, and place it unmodified with its original file names under `data/human_replays/raw/`
(already gitignored). Answer with the resolved source URL and the retrieval date. Keep any
archive alongside the extracted files or note its name; the manifest records every file it
finds.

**(B) You authorise a download.** Answer with the resolved URL and an explicit sentence
authorising the agent to download it. I then write `scripts/fetch_human_replays.py`
(`dataset_acquisition` step 2: records source_url, retrieval_utc, retrieval_method,
ETag/Last-Modified, sha256 and byte count per file) and run it. Note the current permission
set denies `curl` and `wget`; if the deny list is not relaxed for that one script the
download will fail and I re-escalate at once rather than work around the deny list.

**(C) The dataset is not available.** Say so. Then G2 cannot pass as pre-registered: the
coverage floor (0.80 of 183 levels), the replay-unit floor (342) and the parse-failure ceiling
(0) all need the data, and `G2.yaml` is write-once. The choice is yours between waiting for
the dataset and a proposal-level route change; a route change touches `PROPOSAL_v2.md`'s
gate definition and is constitution section 6 item 12, so I would not make it alone.

## 4. What I do with each answer

**On (A) or (B), once files are under `data/human_replays/raw/`:**

1. Build the manifest, replacing the URL and method:

   ```
   uv run python scripts/build_human_replays_manifest.py --source-url <resolved url> \
     --retrieval-method human_placed   # or agent_download; add --revision <etag|date> if known
   ```

2. Read its `totals`. The pre-registered ingestion preflight requires `replay_units >= 342`
   and `parse_failures == 0`. A shortfall in either is recorded in the ledger and appended
   to `docs/EVIDENCE_ARC.md` section 1.4 with the numbers, and re-escalated. No threshold is
   fitted to the data. A schema that differs from the documented recorder format shows up
   here as parse failures; the adapter is then extended under the ladder with the field
   mapping recorded in `input_manifest.json`, as `G2.yaml` `ingestion_paths` requires.

3. Commit `experiments/human_replays_manifest.json` alone.

4. Two graded runs (seed 12345 from the config, no `--seed`):

   ```
   uv run python scripts/run_experiment.py --config configs/experiments/E020_human_baselines.yaml
   uv run python scripts/run_experiment.py --config configs/experiments/E020_human_baselines.yaml
   ```

5. `uv run python scripts/verify_run.py --gate G2 --report state/verify_G2.json`, then the
   C5 adversarial self-review in the ledger, then the `referee` for the verdict.

**On (C):** ledger `decision`, `gate_status` stays `in_progress` with `blocked_on` describing
the dependency, and I stop again with a fresh escalation framed as section 6 item 12 unless
your answer already names the route.

## 5. Non-blocking items for your attention (from `open_questions`; no reply needed)

- `state/PINNED_HASHES.json` is gitignored and `scripts/verify_run.py` is not among the
  pinned files, so layer 2 of C1/C2 is weaker than the constitution describes. A fresh clone
  has no pins.
- The supervisor's uncommitted turn-counter edits to `state/*.json` make every in-turn run
  report `git_dirty: true` in its manifest. The G0 and G1 referees were told; it will recur
  for E020.
- The push after G0 and G1 is deferred until the visibility of
  `git@github.com:afazeliUofT/ARC_AGI3_Plasticity_Lab.git` is confirmed private. `main` is
  well ahead of `origin/main`. A one-word confirmation in your answer lets me push after G2.
- `uv run ruff format --check .` flags 17 pre-existing files, among them the frozen
  `scripts/verify_run.py` and `scripts/c5_probe_G0.py`. The gate threshold is `ruff check`,
  which is clean. Reformatting the frozen files needs your say-so; the rest is a housekeeping
  turn I can take at any time.

## Uncommitted in the working tree

Only this turn's `state/ESCALATION.md`, `state/LEDGER.jsonl`, `state/PROJECT_STATE.json` and
the supervisor's counter edit to `state/BUDGET.json`, all committed by this turn.
