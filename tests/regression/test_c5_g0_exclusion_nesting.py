"""Regression: the G0 determinism ruler's known hole stays documented and unexploited.

Found by the C5 adversarial self-review before the G0 verdict (scripts/c5_probe_G0.py,
ledger 2026-09-04). scripts/verify_run.py strips an excluded key together with its whole
value at any depth, so a result value nested under an excluded name such as ``hardware``
would be invisible to the identity check. The verifier is frozen (constitution section 6
item 13), so the hole cannot be closed here; these tests keep it visible and assert that no
graded E000 artifact uses an excluded key as a container or below top level. If the verifier
is ever changed by escalation to close the hole, the first test fails and should be inverted.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts" / "E000_bootstrap"


def _script(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def excluded() -> frozenset[str]:
    data = yaml.safe_load((ROOT / "configs" / "nondeterministic_fields.yaml").read_text())
    return frozenset(n for group in data["excluded_fields"].values() for n in group)


def test_verifier_strips_whole_value_under_excluded_key(
    tmp_path: Path, excluded: frozenset[str]
) -> None:
    """Documents the hole: a nested result under an excluded key compares identical."""
    vr = _script("verify_run")
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps({"results": {"steps": 1}, "hardware": {"steps": 1}}))
    b.write_text(json.dumps({"results": {"steps": 1}, "hardware": {"steps": 2}}))
    assert vr.canonical_json_bytes(a, excluded) == vr.canonical_json_bytes(b, excluded)
    a.write_text(json.dumps({"results": {"steps": 1}}))
    b.write_text(json.dumps({"results": {"steps": 2}}))
    assert vr.canonical_json_bytes(a, excluded) != vr.canonical_json_bytes(b, excluded)


def _excluded_hits(obj: Any, depth: int, excluded: frozenset[str]) -> list[tuple[int, bool]]:
    hits: list[tuple[int, bool]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in excluded:
                hits.append((depth + 1, isinstance(v, (dict, list))))
            hits.extend(_excluded_hits(v, depth + 1, excluded))
    elif isinstance(obj, list):
        for v in obj:
            hits.extend(_excluded_hits(v, depth + 1, excluded))
    return hits


@pytest.mark.skipif(not ARTIFACTS.is_dir(), reason="no graded E000 artifacts in this checkout")
def test_graded_artifacts_do_not_exploit_the_hole(excluded: frozenset[str]) -> None:
    runs = [p for p in ARTIFACTS.iterdir() if p.is_dir()]
    assert runs
    for run in runs:
        hits = _excluded_hits(json.loads((run / "results.json").read_text()), 0, excluded)
        assert hits, f"{run.name}: results.json exercises no excluded field at all"
        for depth, is_container in hits:
            assert depth == 1 and not is_container, f"{run.name}: nested or container excluded key"
