# Human replay dataset — inventory

Last corrected 2026-09-04T15:38:02Z. **Supersedes the version written by `fix_g2_dataset.sh`, which double-counted macOS AppleDouble sidecars as recordings.** See the ledger entry of the same date.

Placed by the human on 2026-09-04 from the public Drive folder linked by `https://dub.link/vfwCqvb` → `https://drive.google.com/drive/folders/1FB7yae6VISRe2jDKPNZLJS0mAqIw9JZy`. Drive split the download into three zips (`drive-download-20260904T145905Z-1-001..003.zip`), all extracted into `raw/`. Files are unmodified and carry their original names.

`raw/` and `extras/` are gitignored, as is `*.recording.jsonl` anywhere in the tree and any `.zip` under `data/`. One file in `extras/` exceeds GitHub's 100 MB hard limit. This inventory is the tracked record of all of it.

## `raw/` — the manifest input

- recordings: **342**
- total size: 6.69 GiB
- naming: `<uuid>.recording.jsonl`
- nesting depth below `raw/`: {2: 342} (0 = flat)
- directories: 25

| directory below `raw/` | recordings |
|---|---|
| `arc_agi_3_public_demo_human_testing/ar25` | 10 |
| `arc_agi_3_public_demo_human_testing/bp35` | 14 |
| `arc_agi_3_public_demo_human_testing/cd82` | 11 |
| `arc_agi_3_public_demo_human_testing/cn04` | 12 |
| `arc_agi_3_public_demo_human_testing/dc22` | 11 |
| `arc_agi_3_public_demo_human_testing/ft09` | 10 |
| `arc_agi_3_public_demo_human_testing/g50t` | 14 |
| `arc_agi_3_public_demo_human_testing/ka59` | 10 |
| `arc_agi_3_public_demo_human_testing/lf52` | 11 |
| `arc_agi_3_public_demo_human_testing/lp85` | 54 |
| `arc_agi_3_public_demo_human_testing/ls20` | 13 |
| `arc_agi_3_public_demo_human_testing/m0r0` | 11 |
| `arc_agi_3_public_demo_human_testing/r11l` | 10 |
| `arc_agi_3_public_demo_human_testing/re86` | 11 |
| `arc_agi_3_public_demo_human_testing/s5i5` | 11 |
| `arc_agi_3_public_demo_human_testing/sb26` | 12 |
| `arc_agi_3_public_demo_human_testing/sc25` | 15 |
| `arc_agi_3_public_demo_human_testing/sk48` | 14 |
| `arc_agi_3_public_demo_human_testing/sp80` | 12 |
| `arc_agi_3_public_demo_human_testing/su15` | 13 |
| `arc_agi_3_public_demo_human_testing/tn36` | 14 |
| `arc_agi_3_public_demo_human_testing/tr87` | 12 |
| `arc_agi_3_public_demo_human_testing/tu93` | 13 |
| `arc_agi_3_public_demo_human_testing/vc33` | 10 |
| `arc_agi_3_public_demo_human_testing/wa30` | 14 |

Walk the tree; do not glob one level. AppleDouble sidecars (`._*`) are excluded from every figure here and must be excluded from the manifest too.

## `extras/` — shipped alongside, not manifest input

### `arc_agi_3_public_demo_human_testing.zip`

- 111,142,305 bytes — sha256 `99a32ffc3b9e55bc3077b979d00906f256c26354b5fada0b052690b2f5cd634a`
- entries: 706 — of which **366 are macOS metadata** (`__MACOSX/` mirror and `._` sidecars)
- real recordings: **340**; real non-recordings: 0
- already present in `raw/`: **340**
- genuinely absent from `raw/`: **0**
- present in `raw/` but not in the zip: 2
- uncompressed size of the real entries: 6.36 GiB
- verdict: **subset of `raw/` — do NOT extract.** Every recording it contains is already present. Extracting it adds no information.

### `testing_feedback_ratings.csv`

- 6,797 bytes — sha256 `919db1b8f2e068a5f933cffdb1f30a9335806f3075534ee6109dd10f1900a511`
- human ratings collected during the public demo; not a replay unit.

