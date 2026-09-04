# Human replay dataset — inventory

Placed by the human on 2026-09-04 from the public Drive folder linked by `https://dub.link/vfwCqvb` → `https://drive.google.com/drive/folders/1FB7yae6VISRe2jDKPNZLJS0mAqIw9JZy`.

Google Drive split the download into three zips (`drive-download-20260904T145905Z-1-001..003.zip`); all three were extracted into `raw/`. Files are unmodified and carry their original names.

`raw/` and `extras/` are **gitignored** — 6.7 GiB, and one file exceeds GitHub's 100 MB hard limit. This inventory is the tracked record of them.

- replay units in `raw/`: **342**
- total size of `raw/`: 6.69 GiB
- naming: `<uuid>.recording.jsonl`

## First-record keys (3 sampled files)

- `00589449-cfb4-4b98-a31e-2a344db66f89.recording.jsonl` → `['data', 'timestamp']`
- `03665144-5518-4e4b-af99-ec7fe6ab546d.recording.jsonl` → `['data', 'timestamp']`
- `0cf890a2-b328-47f3-a845-0fa379d29358.recording.jsonl` → `['data', 'timestamp']`

## Record counts (3 sampled files)

- `00589449-cfb4-4b98-a31e-2a344db66f89.recording.jsonl`: 1557 JSON records, 20.2 MiB
- `03665144-5518-4e4b-af99-ec7fe6ab546d.recording.jsonl`: 970 JSON records, 12.6 MiB
- `0cf890a2-b328-47f3-a845-0fa379d29358.recording.jsonl`: 1035 JSON records, 13.3 MiB

## `extras/` — present in the download, not replay units

- `arc_agi_3_public_demo_human_testing.zip` — 111,142,305 bytes — sha256 `99a32ffc3b9e55bc3077b979d00906f256c26354b5fada0b052690b2f5cd634a`
  - central directory: 706 entries, 680 `*.recording.jsonl`
  - basenames also present in `raw/`: **340/680**
  - verdict: **340 replay file(s) inside are NOT in `raw/`** — extract only those, then re-count

- `testing_feedback_ratings.csv` — 6,797 bytes — sha256 `919db1b8f2e068a5f933cffdb1f30a9335806f3075534ee6109dd10f1900a511`

