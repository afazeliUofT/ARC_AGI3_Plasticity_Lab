"""scripts/check_commit_secrets.py: the commit-diff credential check the human asked for on
2026-09-04T21:47Z. Fake diffs only; the live-value lookup is fed an explicit mapping."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_commit_secrets", ROOT / "scripts" / "check_commit_secrets.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution so the dataclass decorator can resolve the module's
    # postponed annotations (PEP 563) through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ccs() -> ModuleType:
    return _load()


DIFF = """diff --git a/src/x.py b/src/x.py
--- a/src/x.py
+++ b/src/x.py
@@ -1,2 +1,5 @@
-old = 1
+TOKEN_ALIAS_ENV_KEY = "PLASTICITY_LAB_OAUTH_TOKEN"
+stand_in = "sk-ant-oat01-TESTTOKEN-not-a-real-credential"
+leaked = "sk-ant-oat01-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
+value = "LIVEVALUE-0123456789abcdef"
 kept = 2
"""


def test_scan_flags_credential_shapes_and_live_values_but_not_names(ccs: ModuleType) -> None:
    findings = ccs.scan_diff_text(
        DIFF, {"PLASTICITY_LAB_OAUTH_TOKEN": "LIVEVALUE-0123456789abcdef"}
    )
    assert [str(f) for f in findings] == [
        "src/x.py: diff line 8: credential-shaped value (sk-ant-...)",
        "src/x.py: diff line 9: live value of PLASTICITY_LAB_OAUTH_TOKEN",
    ]
    # The alias name and the test stand-in are not findings; removed lines are never scanned.
    assert (
        ccs.scan_diff_text(DIFF.replace("+leaked", "-leaked").replace("+value", "-value"), {}) == []
    )
    # A finding never carries the value itself.
    assert all("LIVEVALUE" not in str(f) and "AbCdEf" not in str(f) for f in findings)


def test_live_values_need_a_minimum_length(ccs: ModuleType) -> None:
    env = {
        "CLAUDE_CODE_OAUTH_TOKEN": "short",
        "PLASTICITY_LAB_OAUTH_TOKEN": "x" * 40,
        "OTHER": "y" * 40,
    }
    assert ccs.live_values(env) == {"PLASTICITY_LAB_OAUTH_TOKEN": "x" * 40}


def test_hook_body_runs_the_staged_scan(ccs: ModuleType) -> None:
    assert ccs.HOOK_BODY.startswith("#!/bin/sh") and "--staged" in ccs.HOOK_BODY
    assert ccs.HOOK_PATH == ROOT / ".git" / "hooks" / "pre-commit"


def test_head_commit_and_staged_tree_are_clean(ccs: ModuleType) -> None:
    """The check run against this repository's own HEAD and index (live values from the
    process environment, as the hook would use them)."""
    assert ccs.main(["--commit", "HEAD"]) == 0
    assert ccs.main(["--staged"]) == 0
