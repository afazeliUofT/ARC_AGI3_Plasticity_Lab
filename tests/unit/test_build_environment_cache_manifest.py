"""The cache manifest script: layout, relative paths, totals, and agreement with the cache."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _script() -> ModuleType:
    name = "build_environment_cache_manifest"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fake_cache(root: Path) -> Path:
    env = root / "environment_files"
    for stem, version, n_baseline in (("aa11", "0123abcd", 3), ("bb22", "89efcdab", 0)):
        d = env / stem / version
        d.mkdir(parents=True)
        (d / "metadata.json").write_text(
            json.dumps(
                {
                    "game_id": f"{stem}-{version}",
                    "baseline_actions": list(range(n_baseline)),
                    "date_downloaded": "2026-09-04T05:28:00+00:00",
                }
            )
        )
        (d / f"{stem}.py").write_text(f"# {stem}\n")
    (env / "aa11" / "0123abcd" / "__pycache__").mkdir()
    (env / "aa11" / "0123abcd" / "__pycache__" / "aa11.cpython-312.pyc").write_bytes(b"\x00")
    return env


def test_manifest_layout_on_synthetic_cache(tmp_path: Path) -> None:
    mod = _script()
    env = _fake_cache(tmp_path)
    now = datetime(2026, 9, 4, 7, 0, 0, tzinfo=UTC)
    m = mod.build_manifest(tmp_path, env, now)
    assert m["schema_version"] == 1
    assert m["generated_utc"] == "2026-09-04T07:00:00Z"
    assert m["environments_dir"] == "environment_files"
    assert m["totals"] == {"games": 2, "files": 4}
    assert [g["stem"] for g in m["games"]] == ["aa11", "bb22"]
    g = m["games"][0]
    assert g["game_id"] == "aa11-0123abcd"
    assert g["local_dir"] == "environment_files/aa11/0123abcd"
    assert g["baseline_actions_count"] == 3
    assert g["date_downloaded"] == "2026-09-04T05:28:00+00:00"
    assert set(g["files"]) == {"aa11/0123abcd/metadata.json", "aa11/0123abcd/aa11.py"}
    expected = hashlib.sha256((env / "aa11" / "0123abcd" / "aa11.py").read_bytes()).hexdigest()
    assert g["files"]["aa11/0123abcd/aa11.py"] == expected
    assert not any(".pyc" in rel for game in m["games"] for rel in game["files"])


def test_manifest_refuses_stray_files_and_duplicate_stems(tmp_path: Path) -> None:
    mod = _script()
    env = _fake_cache(tmp_path)
    (env / "README.txt").write_text("stray")
    with pytest.raises(mod.CacheLayoutError, match="belong to no game"):
        mod.build_manifest(tmp_path, env, datetime.now(UTC))
    (env / "README.txt").unlink()
    dup = env / "aa11" / "ffffffff"
    dup.mkdir()
    (dup / "metadata.json").write_text(json.dumps({"game_id": "aa11-ffffffff"}))
    with pytest.raises(mod.CacheLayoutError, match="more than once"):
        mod.build_manifest(tmp_path, env, datetime.now(UTC))


def test_manifest_refuses_missing_directory(tmp_path: Path) -> None:
    mod = _script()
    with pytest.raises(mod.CacheLayoutError):
        mod.build_manifest(tmp_path, tmp_path / "nope", datetime.now(UTC))


def test_write_manifest_round_trips(tmp_path: Path) -> None:
    mod = _script()
    env = _fake_cache(tmp_path)
    m = mod.build_manifest(tmp_path, env, datetime.now(UTC))
    out = tmp_path / "experiments" / "environment_cache_manifest.json"
    mod.write_manifest(m, out)
    assert json.loads(out.read_text()) == m


@pytest.mark.skipif(not (ROOT / "environment_files").is_dir(), reason="offline cache absent")
def test_committed_manifest_matches_the_cache_on_disk() -> None:
    """The committed manifest must be exactly what the script would generate now (hashes only)."""
    mod = _script()
    committed = json.loads((ROOT / "experiments" / "environment_cache_manifest.json").read_text())
    fresh = mod.build_manifest(ROOT, ROOT / "environment_files", datetime.now(UTC))
    committed.pop("generated_utc")
    fresh.pop("generated_utc")
    assert committed == fresh
