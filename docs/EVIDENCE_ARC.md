# Evidence Base, Part A: ARC-AGI-3 Verified Fact Sheet

**Status:** verified external evidence, compiled 2026-09-04 for the ARC-AGI-3 Plasticity Lab.
**Companion documents:** `EVIDENCE_NEURO.md` (neuroscience), `EVIDENCE_TOOLING.md` (Claude
Code, model IDs, subscription limits — everything about the machinery the project runs on).

**Authority:** this document is the project's ground truth for every factual claim about
ARC-AGI-3, its toolkit, its scoring, and the state of the art. The autonomous agent MUST read
this before touching the benchmark and MUST NOT rely on model memory for any of it. Items
marked UNCONFIRMED are open questions, not facts; resolving one requires a fresh source and
an edit to this file recording the URL and the date.

---

## 0. The five facts that reshape the project

Read these before anything else. Each one invalidates an assumption in the v1.0 proposal.

1. **The public game set is saturated and officially disavowed.** At least two independent
   systems reached a perfect 100.00 RHAE on all 25 public games — Tycho with Claude Opus 5 in
   6,641 actions, and `pbshgthm/arc-skill` in 7,645 actions (the arc-skill repository
   describes Claude Code on Opus 5; treat the model attribution for that entry as
   self-reported rather than independently verified). The ARC
   Prize technical report states: *"We will never report public set scores of any system on
   the official leaderboard,"* and *"Evaluating on it is emphatically not a valid measure of
   progress towards AGI."* A public-set number is therefore worth approximately nothing as
   evidence, and the v1.0 proposal's Gate 9 "frozen ARC public holdout" is close to
   signal-free.

2. **The private set is out-of-distribution by construction.** *"These environments are
   significantly more difficult for both humans and AI, and are intentionally
   out-of-distribution relative to the public set,"* and *"The public set does not
   comprehensively represent the mechanics found in the private set."* Public-to-private
   transfer is deliberately broken. ARC measured this directly: in environment TR87, Opus 4.6
   scored 0.0% with no harness and 97.1% with a tuned harness; in environment BP35 the same
   model scored 0.0% under both. Their conclusion: *"Specifically engineered harnesses are not
   a useful way to measure AGI progress."*

3. **Full offline operation is supported, free, and fast.** `OperationMode.OFFLINE` needs no
   API key, has no rate limit, allows unlimited concurrent instances, and runs at roughly
   2,000 frames per second on ordinary hardware. Environment files are downloaded once and
   cached, after which the toolkit operates with no network at all. **Environment stepping is
   therefore free and effectively unlimited on a laptop CPU** — the single most important
   enabler for an autonomous workflow. Note carefully what this does *not* say: the *agent* is
   not free. Model calls are the binding constraint on the whole programme, and every published
   state-of-the-art result on this benchmark cost $5,780–$15,200 per run (§0.4, §5.3). See
   `EVIDENCE_TOOLING.md` §10.

4. **The Kaggle competition track forbids internet access during evaluation.** *"Internet
   access is not available during Kaggle evaluation (no API-based systems like
   GPT/Claude/etc.)"* No frontier-API agent can be submitted. Every published state-of-the-art
   result costs between $5,780 and $15,200 per run in API calls and is therefore inadmissible
   to the competition it appears to be competing in. The leaderboard and the competition are
   effectively different contests.

5. **The field has converged on one architecture, and the load-bearing part is verification.**
   Executable programmatic world models, backtested against the full transition history, then
   searched for a plan. Rodionov's ablation study found replay verification ranked first in
   all four model-and-effort settings tested. Any mechanism this project proposes is an
   *addition to* a verified executable world model, not an alternative to one. A baseline that
   does not include this is not a strong baseline.

---

## 1. Benchmark mechanics

### 1.1 Environment counts

| Set | Environments | Purpose |
|---|---:|---|
| Public demonstration | **25** | Demonstration only; explicitly not a progress measure |
| Semi-private | **55** | Frontier models behind an external API; official leaderboard |
| Fully private | **55** | The official ARC Prize competition |
| **Total** | **135** | |

The 25 public games contain **183 levels** in total. Structure is level-based, with *"at least
six levels per environment."*

> ⚠️ **Contradiction to respect.** The technical report says at least six levels per
> environment, but the worked scoring example uses n = 5. The formula generalises as
> `n(n+1)/2`. **Do not hard-code a level count anywhere.**

Public game ID stems (two independent mirrors agree exactly):

```
ar25  bp35  cd82  cn04  dc22  ft09  g50t  ka59  lf52  lp85  ls20  m0r0  r11l
re86  s5i5  sb26  sc25  sk48  sp80  su15  tn36  tr87  tu93  vc33  wa30
```

Full IDs take the form `<stem>-<version hash>`, for example `ls20-016295f7601e`. **Version
hashes differ between mirrors — treat the four-character stem as stable and the hash as
mutable.** Only three games (`ls20`, `ft09`, `vc33`) are reachable with an anonymous key.

**Substrate observation, this project, 2026-09-04 (G1, experiment E100, artifact-cited per
C4).** Under a uniform-random policy drawn from `available_actions` (RESET excluded, ACTION6
coordinates uniform on 0–63) with 5,000 actions allowed per game, **every one of the 25 public
games ends in `GAME_OVER`; none reaches `WIN`**, in each of three offline runs
(`artifacts/E100_arc_interface/`, run directories and `SHA256SUMS` digests:
`20260904T074939Z_seed12345_8383cad8` `6db258830174e76b032943689552631a7b458ffe0f3fad97429af8e1b75e5190`;
`20260904T074956Z_seed12345_9e2317b0` `1cdca620dfd0fd26553233a206ea50609cd2d122251d59bf92bbaa89614849dd`;
`20260904T075000Z_seed12346_b801dd9b` `c8503416d8fd7e8103862a0a68e1299530991cbbab7d09459506cfc396c3d928`;
verifier report `state/verify_G1.json`
`19870d345c1ae2296eaf64c34b01035d1f173af411d684ff7d256b811a0a57c1`). Per-game step counts are
in each run's `results.json` (`results.games[].steps_taken`, covered by the `SHA256SUMS` above):
the longest game lasts 526 actions at policy seed 12345 and 742 at seed 12346, so the 5,000
budget never binds; ten games stop at round counts (30, 42, 50, 100, 200, 300), consistent with
per-game action caps ending the game rather than a random death. One level was completed in
all 75 game-runs: `ft09` at seed 12346 (`levels_completed` 1 of `win_levels` 6, then `GAME_OVER`
at step 742). Random play therefore carries no information about difficulty, and the human
baselines of §1.4 remain the first real performance reference. Source: this repository at
commit `b69a19a` (local; no URL — project-produced numbers cite artifacts, not sources).

### 1.2 Action space — eight commands

| Command | Semantics | Parameters |
|---|---|---|
| `RESET` | Initialises or restarts the game or level state | none |
| `ACTION1` | Simple action, varies by game, semantically mapped to up | none |
| `ACTION2` | ... mapped to down | none |
| `ACTION3` | ... mapped to left | none |
| `ACTION4` | ... mapped to right | none |
| `ACTION5` | Interact, select, rotate, attach/detach, execute, and similar | none |
| `ACTION6` | Complex action requiring coordinates | **x, y ∈ 0–63** |
| `ACTION7` | Simple undo, present only in games that support it | none |

Only `ACTION6` is parameterised. Each environment exposes a **subset**, surfaced per step in
`available_actions`. In a game-over state the only valid action is `RESET`; anything else
returns HTTP 400.

### 1.3 Observation format

- Grid: **64 × 64**, origin `(0,0)` top-left, `(x, y)` ordering.
- Colours: **16**, integer cell values 0–15.
- **One or more grids per frame.** Multi-grid responses are non-interactive transition
  animations between player turns. Code that assumes a single grid per response is wrong.

`FrameResponse` fields:

| Field | Type | Meaning |
|---|---|---|
| `game_id` | string | game identifier |
| `guid` | string | server session id, required on subsequent commands |
| `frame` | int[][][] | one or more 64×64 grids |
| `state` | enum | `NOT_PLAYED` / `NOT_FINISHED` / `WIN` / `GAME_OVER` |
| `levels_completed` | int 0–254 | cumulative levels completed this run |
| `win_levels` | int 0–254 | level threshold for `WIN` |
| `action_input.id` | int 0–7 | 0 is RESET |
| `action_input.data` | object | parameters, x and y for ACTION6 |
| `action_input.reasoning` | string, optional | caller-supplied |
| `full_reset` | bool, optional | new game versus level reset |
| `available_actions` | int[] 0–7 | actions permitted right now |

> ⚠️ **There is no `score` field.** Progress is `levels_completed` against `win_levels`.
> Scoring is computed downstream from action counts. Online responses also set `AWSALB*`
> cookies that must be echoed on subsequent ACTION commands for session affinity — a real trap
> for any hand-rolled HTTP client. Use the official toolkit.

### 1.4 Human replays

**342 human step-by-step replays** across the 25 public environments, released 14 April 2026.
Underlying study: 486 unique participants, 2,893 attempts, 427.9 hours, exactly ten members of
the public tested per environment, 20-minute soft and 30-minute hard per-environment limits.
Efficiency statistics derive from 1,614 level completions across 340 sessions.

> ⚠️ A blog post gives 458 participants where the report gives 486. Cite the report figure.
> UNCONFIRMED: the resolved download location — the published link is a URL shortener.

These replays are of the public set only. They are legitimate as **human-efficiency reference
data** and as imitation material; they are not an evaluation signal.

**Resolved download location, this project, 2026-09-04 (G2, resolves §6 item 6).** The
[human dataset blog](https://arcprize.org/blog/arc-agi-3-human-dataset) links only the
shortener `https://dub.link/vfwCqvb`, which resolves to the Google Drive folder
[`1FB7yae6VISRe2jDKPNZLJS0mAqIw9JZy`](https://drive.google.com/drive/folders/1FB7yae6VISRe2jDKPNZLJS0mAqIw9JZy).
The shortener answers HTTP 429 then 403 to a non-browser fetch, so the files were placed by the
human (`retrieval_method human_placed`, `retrieval_utc 2026-09-04T14:59:05Z`, Google Drive export
`drive-download-20260904T145905Z-1-001..003.zip`, no ETag) under `data/human_replays/raw/`, which
is gitignored. Inventory: `experiments/human_replays_manifest.json` (sha256
`08ea6ef9898dd0e493bd682131f25e257d61ef2b56a2710b37c25ba85c9bfd79`, generated
2026-09-04T15:36:01Z): **342 recordings, 7,179,719,072 bytes (6.69 GiB), 0 parse failures,
`participant_ids_available false`**, every file digested. The graded ingestion run
`artifacts/E020_human_baselines/20260904T154531Z_seed12345_2599f0a4/` (`SHA256SUMS`
`5a7c569312f9a43240680b724a0ccb7453cc6f5da48082c0e5bde68bbc1b8fac`) records in `results.json`
(`20c8437952a5a1154191b6e0573b6d74c07c1c55ce00dcb831c6300fcaaf1aea`): `replay_units_ingested 342`,
`replay_parse_failures 0`, `replay_units_matched 342`, `replay_units_unmatched 0`, 25 games
matched by stem to the cached `environment_files/`.

**Recorder format as released (same run, `input_manifest.json`
`71aa97fb82869a874f671981896ba949d665639861856c3ac6d30c7d86c7a1bc` and
`replay_ingestion_log.jsonl` `3572a5bfe9336b1a`…, 342 lines, `field_mapping` per file).** One
session per file, `raw/arc_agi_3_public_demo_human_testing/<stem>/<uuid>.recording.jsonl`, one
JSON object `{timestamp, data}` per line. Frame records carry `data.action_input`, `frame`,
`state`, `levels_completed`, `win_levels`, `guid`, `full_reset`, `available_actions` and
`game_id`; the closing record is the toolkit scorecard (`data.cards[<game_id>]` with
`actions`, `actions_by_level`, `total_plays`). **No participant identity exists anywhere in the
release**, so a "participant" is a session; the only other released file,
`extras/testing_feedback_ratings.csv`, keys on the recording uuid. 23 recordings (cn04 12,
tr87 4, m0r0 3, dc22 2, lf52 2) use an older format with string action ids. Opening-frame
accounting, fixed by the toolkit source rather than the data: **record 1 is the play-start
frame, not an issued action**; record k ≥ 2 is issued action k−1; level l is completed at the
first record with `levels_completed ≥ l`; the per-level count is the difference of successive
completion indices. Basis: `arc_agi.scorecard.Card` in `arc-agi` 0.9.9 (`scorecard.py` sha256
`1cc830e48008bec60b8a98ae14d3e9312e8408f102a9878bad42744aa9e489b7`). Under this rule the step-log
attribution equals the scorecard's own `actions_by_level` pairs per level in every recording that
carries them (`input_manifest.json` `dataset_agreement_summary`: 342 files, 324 all levels agree
of which 24 have no completion in either path, 16 have a card without the key, 2 lp85 cards are
ragged with fewer pair lists than plays, 1617 levels agree, 9 disagree, all 9 in those 2 ragged
cards and confirmed equal by hand). Verdict: `docs/decisions/G2_VERDICT.md` sha256
`8f4e980c65be78a41f3495b5271130fd72bc52aa9c2fb0c61c12a1d7d97c57e7`, GO at commit `9e66b0d`.

---

## 2. Scoring: RHAE

**R**elative **H**uman **A**ction **E**fficiency, pronounced "ray". Inspired by SPL from
robotics. Measures per-level action efficiency against a human baseline, normalised per game,
averaged across games.

**Level efficiency score** for level *l* in environment *e*, with *h* human baseline actions
and *a* agent actions:

```
S(l,e) = min( 1.15 , ( h(l,e) / a(l,e) )² )
```

**Environment score** — weighted average with a completion cap. Weight of level *l* is
`w_l = l`, so later levels dominate and *"introductory or tutorial-like levels have the
smallest influence."* With *k* levels completed of *n*:

```
E(e) = min(  Σ(l=1..k) w_l  /  Σ(l=1..n) w_l ,
             Σ(l=1..n) w_l·S(l,e)  /  Σ(l=1..n) w_l  )
```

**Total** `T = (1/|D|) Σ E(e)` — a plain mean over environments.

**100.00 means** every level of every environment completed, each at or below the human
baseline action count. The 1.15 cap means beating humans earns almost no extra credit.

**Why squared:** *"Under a linear formulation, substantial inefficiencies can still yield
disproportionately high scores."* Worked example: 10 human actions against 100 agent actions
scores `(10/100)² = 1%`.

**Two operational rules that function as part of the metric:**
- **Action budget: 5× the human-baseline median per level.** *"for a level with a human median
  of n actions to completion, the agent is terminated after 5n actions."*
- **Cost cap: $10,000 USD per run**, single run, *"we do not average scores across runs."*

> ⚠️ **Two versioned discrepancies. Use the current documentation values.**
> 1. **Cap.** arXiv v1 (March 2026) gives `min(1.0, h/a)²` — cap 1.0, square outside the min.
>    The April 2026 PDF and the current methodology docs give `min(1.15, (h/a)²)` — cap 1.15,
>    square inside. These are not equivalent. **Use 1.15, square inside.** Third-party
>    implementations frequently propagate the arXiv form; do not copy them.
> 2. **Human baseline.** Current docs say *"upper-median best human action count"*, aggregated
>    per level from best first-run playthroughs. arXiv v1 said *"the second-best human by
>    number of actions used."* Use the current definition.

Secondary quantities reported alongside RHAE: levels completed, environments cleared, total
actions, and USD cost. The leaderboard's x-axis is cost, and *"Only systems which required
less than $10,000 to run are shown."*

**Reproduction of the official human baselines from the released replays, this project,
2026-09-04 (G2, artifact-cited per C4).** Applying the documented rule (upper median of the
per-participant best first-session action count per level, sorted value at 1-based index
⌊N/2⌋+1, one session per participant because no identity is released, §1.4) to all 342
recordings, run `artifacts/E020_human_baselines/20260904T154531Z_seed12345_2599f0a4/`
(`SHA256SUMS` `5a7c569312f9a43240680b724a0ccb7453cc6f5da48082c0e5bde68bbc1b8fac`;
`results.json` `20c8437952a5a1154191b6e0573b6d74c07c1c55ce00dcb831c6300fcaaf1aea`;
`human_baselines.json` `1e841bf53ba5450d506e8605cf168e6e4894520953171ae552e115a03b181185`;
`metrics.csv` `2686a8eb65954cbab04c41f9f0fa55e70c754e0a93a8a3114bb19150ee90db63`) derives a
value for **183 of 183 public levels** (`human_baseline_level_coverage 1.0`) and reproduces the
official `metadata.json` `baseline_actions` **exactly on 170 of 183 levels**
(`exact_agreement_fraction 0.9289617486338798`, `median_abs_relative_difference 0.0`). The 13
disagreeing levels all lie in two games; the other 23 games agree on every level:

| Game | Levels | Derived (this project) | Official `metadata.json` |
|---|---|---|---|
| lp85 (`305b61c3`) | 1, 2, 3, 4, 5, 7, 8 of 8 | 18, 39, 43, 23, 39, 57, 131 | 17, 38, 31, 16, 41, 26, 159 |
| vc33 (`5430563c`) | 1, 3, 4, 5, 6, 7 of 7 | 13, 119, 50, 120, 39, 155 | 7, 44, 61, 131, 34, 152 |

The differences are not an accounting offset (official minus derived across lp85 levels 1–8 is
−1, −1, −12, −7, +2, 0, −31, +28), and for vc33 level 3 the official 44 is not among the eight
released level-3 values, so no order statistic of the release yields it. The released population
for lp85 is also not the study's: 54 sessions recorded over two months (2025-12-03 to
2026-01-30) against 10–15 sessions inside a 1–5 day window for every other game. The referee's
independent parser reproduced all 183 derived values from the raw bytes. **Operational rule from
G2 onward (`preregistration/G2.yaml` `canonical_scoring_baseline`):** every RHAE computation
uses the official `metadata.json` value as *h*, delegated to `arc_agi.scorecard`; the derived
table is the reproduction check and the source of per-level human distributions, and any use of
its lp85 or vc33 rows carries this caveat. Verdict: `docs/decisions/G2_VERDICT.md` sha256
`8f4e980c65be78a41f3495b5271130fd72bc52aa9c2fb0c61c12a1d7d97c57e7` (sections 6 and 9(a)).

---

## 3. Toolkit and API

> ⚠️ **Name trap.** Install **`arc-agi`**, not `arc-agi-3`. The latter is a stale 0.0.1
> package from December 2025 with a single release and no declared license.

| | `arc-agi` — use this | `arc-agi-3` — do not use |
|---|---|---|
| Version | **0.9.9** (2026-06-10) | 0.0.1 (2025-12-20) |
| Summary | ARC-AGI Toolkit | Python SDK for building ARC-AGI-3 agents |
| Python | **>= 3.12** | >= 3.12 |
| License | MIT, © 2026 ARC Prize Foundation | not declared |
| Dependencies | `arcengine>=0.9.3`, flask, matplotlib, pydantic, python-dotenv, pillow, requests | — |

> ⚠️ **Python >= 3.12 is required.** The v1.0 proposal specified Python 3.11. That would fail
> at install. The project pins **3.12**.

```bash
uv add arc-agi
```

```python
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

arc = Arcade(operation_mode=OperationMode.OFFLINE)
env = arc.make("ls20", render_mode="terminal")
obs = env.step(GameAction.ACTION1)
```

- Base API URL: `https://three.arcprize.org`, REST `POST /api/cmd/RESET`, `/api/cmd/ACTION1`…`ACTION7`
- Auth header: `X-API-Key`; environment variable `ARC_API_KEY`; anonymous key gives 3 games
- Main class `Arcade`, methods `make()`, `get_environments()`, `create_scorecard()`,
  `open_scorecard()`, `get_scorecard()`, `close_scorecard()`, `listen_and_serve()`
- Environment methods `.step()`, `.action_space`
- Mode also settable by environment variable `OPERATION_MODE=OFFLINE|ONLINE|COMPETITION`

### 3.1 Offline versus online

| | OFFLINE | ONLINE |
|---|---|---|
| Rate limit | **none** | 600 requests/minute, HTTP 429 with exponential backoff |
| Concurrency | *"Unlimited concurrent instances"* | UNCONFIRMED |
| Throughput | **~2,000 FPS** (120,000 frames/minute) | network-bound |
| API key | not required | required |
| Scorecards | unavailable | yes |
| Shareable replays | no | yes |

Docs *"explicitly recommend local operation for development and testing."* Environment files
cache to `environment_files/` after a single download, after which operation is *"fully
offline."* The engine is pure Python plus numpy and targets a floor of 1,000 FPS.

A third mode, `OperationMode.COMPETITION`, is required to appear on the unverified
leaderboard; it forces API-only interaction, scoring across all environments, and a single
interaction per environment.

**Two offline-mode observations, this project, 2026-09-04 (G1 C5 self-review, artifact-cited
per C4).** (a) **The `seed` argument to `Arcade.make()` has no observable effect on any of the
25 public games** (`arc-agi` 0.9.9, `arcengine` 0.9.3, from `uv.lock`): replaying every
recorded action list of run `20260904T074939Z_seed12345_8383cad8` (made with seed 12345) under
`make(..., seed=7)` reproduces the recorded `final_frame_sha256` for 25 of 25 games with the
same final state (ledger `decision` entry, kind `c5_self_review`, 2026-09-04). The public games
are pure functions of the action sequence; a replay-identity check therefore certifies
action-log fidelity, not seed handling, and any experiment that wants environment variation must
obtain it from the policy or from the game set, never from this seed. (b) **All-in throughput,
including `reset()` and digest time, is about half the step-only figure.** From the three run
manifests (`manifest.wallclock_seconds`, covered by the `SHA256SUMS` digests in §1.1) against
`throughput.json` step counts: 3,306 steps in 4.20 s and 4.25 s, 3,820 steps in 4.64 s, giving
777–823 frames per second all-in versus 1,577–1,640 step-only; both are above the ~1,000 FPS
engine target's practical floor of 500 the G1 pre-registration adopted, and below the ~2,000 FPS
figure quoted above. Source: this repository at commit `b69a19a`.

### 3.2 Open source status

The toolkit and engine are MIT (`arc-agi`, `arcengine`). The toolkit repository does **not**
contain game source; games arrive as downloadable environment files. Public environment files
are mirrored by third parties as Python. The environment format is documented and authorable.
Private and semi-private environments are not public.

UNCONFIRMED: the exact license applied to the public game environment files themselves, as
distinct from the toolkit.

### 3.3 Public environment file versions drift, and the replays name two versions

**This project, 2026-09-04 (G2).** Environment file directories are versioned by an eight-hex
hash (`environment_files/<stem>/<hash>/`, `metadata.json` `game_id` = `<stem>-<hash>`). The
local cache downloaded 2026-09-04 (pinned by `experiments/environment_cache_manifest.json`,
sha256 `023726479a3c201161a61ee0d310b20696988933adbf1826dc9d7bd524d960af`) lists a **different
version hash from the third-party
[Hugging Face mirror](https://huggingface.co/datasets/zarczynski/arc-agi-3-public) (revision
`f5757d68`, dated 2026-04-02) for 15 of the 25 public games**: ar25, cn04, dc22, ka59, m0r0,
r11l, re86, s5i5, sc25, sk48, sp80, su15, tn36, tu93, vc33 (ledger `literature` entry, G2.1).
The other ten (bp35, cd82, ft09, g50t, lf52, lp85, ls20, sb26, tr87, wa30) carry the same hash
in both.

**The released human recordings (§1.4) carry two game ids per record, and for exactly those 15
games they disagree.** The frame-side `data.game_id` equals the cached `metadata.json` `game_id`
for all 25 games (run A `input_manifest.json`
`71aa97fb82869a874f671981896ba949d665639861856c3ac6d30c7d86c7a1bc`, `replay_game_ids_by_stem`).
The client-side `data.action_input.data.game_id` names, for the 15 games above, the Hugging Face
version instead (ar25 `e3c63847`, cn04 `65d47d14`, dc22 `4c9bff3e`, ka59 `9f096b4a`, m0r0
`dadda488`, r11l `aa269680`, re86 `4e57566e`, s5i5 `a48e4b1d`, sc25 `f9b21a2f`, sk48 `41055498`,
sp80 `0ee2d095`, su15 `4c352900`, tn36 `ab4f63cc`, tu93 `2b534c15`, vc33 `9851e02b`, against
frame-side `0c556536`, `2fe56bfb`, `fdcac232`, `38d34dbb`, `492f87ba`, `495a7899`, `8af5384d`,
`18d95033`, `635fd71a`, `d8078629`, `589a99af`, `1944f8ab`, `ef4dde99`, `0768757b`, `5430563c`);
found by the G2 referee and reproduced by this agent's scan of all 342 files. lp85 is **not**
among them (both ids `305b61c3`); the ledger's G2.8 decision (c) placing it there is wrong. The
recordings are dated 2025-11-10 to 2026-03-20, before the mirror snapshot, so the clients
requested the versions current at the time and the frame-side ids name versions that appeared
later; whether the frames were regenerated on the newer versions or only relabelled cannot be
decided from the files. 13 of the 15 affected games reproduce the official baselines exactly
(§2); vc33 does not, and neither does the unaffected lp85. Consequences: the replays are
evidence about the frame-side (cached) versions only; any later gate names the cached versions
it runs and records this discrepancy; a re-download on another day may change hashes and
requires a cache-manifest regeneration, not a drift diagnosis. Verdict:
`docs/decisions/G2_VERDICT.md` sha256
`8f4e980c65be78a41f3495b5271130fd72bc52aa9c2fb0c61c12a1d7d97c57e7` (section 9, argument B;
section 10 items 1–2).

---

## 4. ARC Prize 2026 competition (reference only — not this project's target)

Recorded for completeness because it constrains what a submitted artifact could ever look
like. This project does not target the competition; see PROPOSAL_v2 §2.

| Date | Event |
|---|---|
| 25 March 2026 | Competition starts |
| 30 June 2026 | ARC-AGI-3 milestone #1 |
| 30 September 2026 | ARC-AGI-3 milestone #2 |
| 26 October 2026 | Team merger deadline — UNCONFIRMED, single third-party source |
| **2 November 2026** | Final submissions due |
| 8 November 2026 | Papers due, paper track |
| 4 December 2026 | Results announced |

ARC-AGI-3 track prizes total **$850K**: grand prize $700K for the first eligible agent scoring
100%, top-score awards $75K, milestone awards $75K.

**Constraints:**
- **No internet during evaluation.** *"All accelerated Kaggle sessions have internet disabled,
  which is already the default in this kit."*
- Accelerators: `cpu`, `t4` (2× Nvidia T4, default), `p100`, `rtx6000` (ARC-AGI-3 exclusive).
- Runtime limit **6 hours** — UNCONFIRMED, single third-party source. arcprize.org still
  carries stale text saying limits *"will be announced with the competition launch."*
- RAM limits: UNCONFIRMED.
- Licensing, verbatim: *"all code and methods authored by the submitter must be made open
  source under a permissive public domain license (eg. CC0 or MIT-0)"*, and third-party code
  must be *"at least, an open source license which allows public sharing (eg. Apache-2.0,
  GPLv3)."*

> ⚠️ **MIT is not sufficient for authored code — MIT-0 or CC0 is required.** This is cheap to
> get right at commit 1 and painful to retrofit. **This repository is MIT-0 from the first
> commit** regardless of whether a submission is ever made.

Hidden evaluation set: **55 environments**, the fully private set. High confidence but not
restated by Kaggle itself.

---

## 5. State of the art, September 2026

### 5.1 Verified frontier-model scores, no harness

| Model | Score | Date |
|---|---:|---|
| **Claude Opus 5 (High)** | **30.16%** | 2026-07-24 |
| GPT-5.6 Sol | 7.78% | 2026-07-09 |
| Claude Opus 4.8 | 1.52% | 2026-05-28 |
| Claude Opus 4.6 | 0.51% | 2026-02-05 |
| GPT-5.5 | 0.43% | 2026-04-23 |
| Gemini 3.1 Pro Preview | 0.42% | 2026-02-19 |
| Humans | **100%** | — |

> ⚠️ UNCONFIRMED which set the 30.16% is measured on. The ARC results page labels it "Public
> Demo (25 environments)"; an aggregator labels the same series semi-private; the technical
> report says public scores are never reported. **Do not state which set without checking the
> live page.**

### 5.2 Community leaderboard, self-reported, public set

| System | Score | Date |
|---|---:|---|
| Tycho | **100.0%** | 2026-07-29 |
| Retrodict | 99.9% | 2026-07-19 |
| baseline1 | 99.0% | 2026-07-15 |
| Human Intelligence Harness | 95.3% | 2026-04-14 |
| NOOA | 85.1% | 2026-07-09 |
| OPINE-World | 78.4% | 2026-07-01 |
| Vision — Continual Learning v1 | 63.1% | 2026-05-18 |

Hidden-set state of the art: **no public numbers.** Milestone #1 went to Tufa Labs ("The
Duck"), Reki, and "forge"; scores undisclosed.

### 5.3 Published architectures

| Work | Date | Approach | Result |
|---|---|---|---|
| Rudakov, Shock & Cowley, arXiv 2512.24156 | 2025-12 | **Training-free, no LLM.** Frame segmentation, directed state-transition graph, salience-prioritised actions, shortest path to untested state-action pairs | Median 30 of 52 levels across six games; **3rd on the private preview leaderboard**, *"substantially outperforming frontier LLM-based agents"* |
| Rodionov, arXiv 2605.05138 | 2026-05 | Coding agent maintains an **executable Python world model**, verifies against observations, refactors toward simpler abstractions, plans through the model | GPT-5.5 high 58.12% RHAE, 15/25 games |
| Rodionov, arXiv 2607.15439 | 2026-07 | **Ablation** of the above across four nested agents | **Verification ranked 1st in all four settings**; simplification helped in 3/4; gpt-5.6-sol verification variant fully solved every public game, ~99% RHAE |
| Courtis, Li & Sanner (Toronto), arXiv 2607.01531 | 2026-07 | **OPINE-World.** Two cooperating LLM agents; object-centric programmatic world models via counterexample-guided inductive synthesis; **ontology error** as Bayesian uncertainty steering exploration | 78.4%, 20/25 games, 160/183 levels, Opus 4.8. Baselines: WorldCoder 0.0%, latent world models 0.0% |
| Lehmann, Aioanei & Vahdati, arXiv 2607.28287 | 2026-07 | **Tycho.** Games as parameterized rendered deterministic Moore machines; editable Python hypotheses verified against transitions and used for planning by simulation | **100.00% RHAE**, Opus 5, **6,641 actions**; 61% fewer scored actions than human baselines; $5.78k |
| pbshgthm/arc-skill | 2026-08 | **Prediction-before-action as a hard constraint** — the harness refuses unpredicted actions and grades falsifiable claims. Escalation from prose notes to Python analysis to simulators to full executable models with A* | **100.00 RHAE**, 25/25 games, 183/183 levels, **7,645 actions** against a 17,135 human median; 7,627 predictions graded, 443 missed |
| Schema harness | 2026-07 | Observe → deliberate → execute → record; executable `step()` programs; backtest against full history; BFS inside certified models; immediate plan abandonment on prediction mismatch | 98.98% (Opus 4.8 + Fable 5). **Their Claude Code control scored 42.83% — a 56.15 point harness delta** |

### 5.4 What this means

**The convergent architecture, in five parts:**
1. Induce a **program**, not a policy — executable Python that simulates the game.
2. **Verify by replay** against the complete transition history. Rodionov's ablation shows
   this is the load-bearing component.
3. **Plan inside the certified model** — A*, BFS, simulation — rather than querying the model
   per action. This is what buys the action efficiency RHAE rewards.
4. **Falsify and revise on mismatch.** Predict before acting; abandon the plan on a miss.
5. **Simplicity bias** as an MDL proxy; **exploration steering** by uncertainty over
   unexplained behaviour.

**What does not work:** latent world models 0.0%; WorldCoder 0.0%; raw frontier LLMs below
0.5% until Opus 5; plain LLM scaffolds 42.83% against 98.98% for the same model with a
world-model harness. **No leading method uses reinforcement learning or gradient training.**
Everything at the top is training-free inference-time program synthesis over a frozen model.
The one strong non-LLM entry is classical graph exploration, and it beat every frontier LLM
agent in the preview challenge.

**Consequences for this project, stated plainly:**
- B4 in the v1.0 baseline ladder is not a baseline. It is the state of the art, and it must be
  built to a competitive standard or every mechanism comparison is invalid.
- Every mechanism must be tested as a **delta on top of a verified executable world model**.
  A mechanism that only beats a memory-less agent has demonstrated nothing.
- The novelty audit must confront OPINE-World's ontology-error exploration and Rodionov's
  simplification refactoring on day one, because they overlap the v1.0 M2 and M1 respectively.

---

## 6. Open questions carried forward

Each of these is UNCONFIRMED. Resolving one means finding a source, recording the URL and the
date here, and moving it out of this list.

1. Kaggle entry deadline — not stated on any reachable source.
2. Kaggle runtime limit (6 hours) and team merger date — single third-party source each.
3. Kaggle notebook RAM limits — no source.
4. Online-mode concurrency limit.
5. Whether the 55 fully-private environments are exactly the Kaggle hidden set.
6. Resolved download location for the 342 human replays.
7. License applied to public game environment files specifically.
8. Which evaluation set the Opus 5 30.16% figure is measured on.
9. Milestone #1 numeric scores.

**Resolutions (additions only; the numbered list above is never edited).**
- Item 6 **RESOLVED 2026-09-04**: `https://dub.link/vfwCqvb` resolves to Google Drive folder
  [`1FB7yae6VISRe2jDKPNZLJS0mAqIw9JZy`](https://drive.google.com/drive/folders/1FB7yae6VISRe2jDKPNZLJS0mAqIw9JZy);
  342 recordings, 7,179,719,072 bytes, human-placed, inventoried in
  `experiments/human_replays_manifest.json`
  (`08ea6ef9898dd0e493bd682131f25e257d61ef2b56a2710b37c25ba85c9bfd79`). Details in §1.4. The
  shortener is not fetchable by script (HTTP 429/403), so a fresh machine needs a human or a
  browser to obtain the files.

---

## 7. Source index

Toolkit and benchmark:
[docs.arcprize.org/llms.txt](https://docs.arcprize.org/llms.txt) ·
[games](https://docs.arcprize.org/games) ·
[available-games](https://docs.arcprize.org/available-games) ·
[actions](https://docs.arcprize.org/actions) ·
[game-schema](https://docs.arcprize.org/game-schema) ·
[methodology](https://docs.arcprize.org/methodology) ·
[local-vs-online](https://docs.arcprize.org/local-vs-online) ·
[rate_limits](https://docs.arcprize.org/rate_limits) ·
[arc-prize-2026](https://docs.arcprize.org/arc-prize-2026) ·
[competition_mode](https://docs.arcprize.org/toolkit/competition_mode) ·
[toolkit/overview](https://docs.arcprize.org/toolkit/overview) ·
[start-or-reset-game-instance](https://docs.arcprize.org/api-reference/commands/start-or-reset-game-instance)

Primary ARC sources:
[ARC-AGI-3 Technical Report PDF](https://arcprize.org/media/ARC_AGI_3_Technical_Report.pdf) ·
[arXiv 2603.24621](https://arxiv.org/abs/2603.24621) ·
[arXiv HTML v1](https://arxiv.org/html/2603.24621v1) ·
[competitions/2026](https://arcprize.org/competitions/2026) ·
[competitions/2026/arc-agi-3](https://arcprize.org/competitions/2026/arc-agi-3) ·
[Verified Testing Policy](https://arcprize.org/policy) ·
[leaderboard](https://arcprize.org/leaderboard) ·
[community leaderboard](https://arcprize.org/leaderboard/community) ·
[results/anthropic-claude-opus-5](https://arcprize.org/results/anthropic-claude-opus-5) ·
[human dataset blog](https://arcprize.org/blog/arc-agi-3-human-dataset) ·
[milestone-1 blog](https://arcprize.org/blog/arc-prize-2026-milestone-1)

Packages and repositories:
[PyPI arc-agi](https://pypi.org/project/arc-agi/) ·
[PyPI arcengine](https://pypi.org/project/arcengine/) ·
[github arcprize/ARC-AGI](https://github.com/arcprize/ARC-AGI) ·
[github arcprize/ARC-AGI-3-Agents](https://github.com/arcprize/ARC-AGI-3-Agents) ·
[github pbshgthm/arc-skill](https://github.com/pbshgthm/arc-skill) ·
[github axobase001/arc-agi-games](https://github.com/axobase001/arc-agi-games) ·
[HuggingFace zarczynski/arc-agi-3-public](https://huggingface.co/datasets/zarczynski/arc-agi-3-public)

Published architectures:
[arXiv 2512.24156](https://arxiv.org/abs/2512.24156) ·
[arXiv 2605.05138](https://arxiv.org/abs/2605.05138) ·
[arXiv 2607.15439](https://arxiv.org/abs/2607.15439) ·
[arXiv 2607.01531](https://arxiv.org/abs/2607.01531) ·
[arXiv 2607.28287](https://arxiv.org/html/2607.28287) ·
[schema-harness](https://schema-harness.github.io/)
