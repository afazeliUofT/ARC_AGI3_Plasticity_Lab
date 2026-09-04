"""Exercise the PreToolUse control-surface hook with synthetic payloads.

This is the empirical evidence behind ``docs/EVIDENCE_TOOLING.md`` section 11 item 5: a
``PreToolUse`` hook that matches ``Bash`` must block ``sed -i`` and shell redirection against a
protected path, and must leave ordinary work alone. The hook is invoked exactly as Claude Code
invokes it: JSON on stdin, decision on stdout, exit 2 for a denial and exit 0 for allow.

The hook script itself lives under ``.claude/`` and is frozen; this test only executes it.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "protect_control_surface.sh"

PREREG = "preregistration/G0.yaml"  # exists and must be write-once
FROZEN = "scripts/supervisor.py"


def run_hook(tool_name: str, tool_input: dict[str, str]) -> tuple[int, dict[str, object]]:
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    decision: dict[str, object] = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return proc.returncode, decision


def is_denied(returncode: int, decision: dict[str, object]) -> bool:
    specific = decision.get("hookSpecificOutput")
    if not isinstance(specific, dict):
        return returncode == 2
    return returncode == 2 and specific.get("permissionDecision") == "deny"


@pytest.fixture(scope="module")
def hook_present() -> None:
    if not HOOK.is_file():
        pytest.skip(f"hook not installed at {HOOK}")
    if not (ROOT / PREREG).is_file():
        pytest.skip(f"{PREREG} missing; the write-once branch cannot be exercised")


@pytest.mark.parametrize(
    "command",
    [
        f"sed -i 's/0/1/' {PREREG}",
        f"echo x >> {PREREG}",
        f"echo x > {PREREG}",
        f"printf 'x' | tee -a {PREREG}",
        f"sed -i 's/0/1/' {FROZEN}",
        f"echo x >> {FROZEN}",
        f"echo x >> {ROOT}/{FROZEN}",  # absolute path
        f"cp /tmp/x {FROZEN}",
        f"git checkout -- {FROZEN}",
        f"python -c \"open('{FROZEN}','w')\"",
        "echo x >> state/PINNED_HASHES.json",
        "echo x >> .claude/settings.json",
        "echo x >> AGENT_CONSTITUTION.md",
        "echo x >> PROPOSAL_v2.md",
    ],
)
def test_bash_writes_to_protected_paths_are_denied(hook_present: None, command: str) -> None:
    rc, decision = run_hook("Bash", {"command": command})
    assert is_denied(rc, decision), (command, rc, decision)


@pytest.mark.parametrize(
    "command",
    [
        "echo x >> /tmp/probe.txt",
        f"cat {PREREG}",
        f"sha256sum {PREREG} {FROZEN}",
        f"grep -n threshold {PREREG}",
        "uv run pytest -q",
        "git add -A && git commit -m 'G0.1: test'",
        "echo x >> docs/EVIDENCE_TOOLING.md",  # evidence docs: append-only is the supervisor's job
    ],
)
def test_bash_reads_and_ordinary_writes_are_allowed(hook_present: None, command: str) -> None:
    rc, decision = run_hook("Bash", {"command": command})
    assert rc == 0 and not decision, (command, rc, decision)


@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit"])
def test_edit_tools_cannot_amend_an_existing_preregistration(hook_present: None, tool: str) -> None:
    rc, decision = run_hook(tool, {"file_path": str(ROOT / PREREG), "content": "x"})
    assert is_denied(rc, decision), (tool, rc, decision)


@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_edit_tools_cannot_touch_frozen_files(hook_present: None, tool: str) -> None:
    for rel in (FROZEN, ".claude/settings.json", "state/PINNED_HASHES.json", "PROPOSAL_v2.md"):
        rc, decision = run_hook(tool, {"file_path": str(ROOT / rel), "content": "x"})
        assert is_denied(rc, decision), (tool, rel, rc, decision)


def test_write_tool_may_author_a_new_preregistration_once(hook_present: None) -> None:
    rc, decision = run_hook(
        "Write", {"file_path": str(ROOT / "preregistration/G99.yaml"), "content": "x"}
    )
    assert rc == 0 and not decision, (rc, decision)


def test_write_tool_may_append_to_evidence_documents(hook_present: None) -> None:
    rc, decision = run_hook("Edit", {"file_path": str(ROOT / "docs/EVIDENCE_TOOLING.md")})
    assert rc == 0 and not decision, (rc, decision)


def test_known_gap_python_script_writes_are_not_matched(hook_present: None) -> None:
    """Documented limitation: the hook matches the command string, not what a script does.

    A script invoked by name that writes to a frozen path is not visible to the hook. The
    supervisor's pinned-hash check (layer 2) is what holds against this; the test pins the
    observed behaviour so a future change to the hook is noticed rather than assumed.
    """
    rc, decision = run_hook("Bash", {"command": "python scripts/some_script.py"})
    assert rc == 0 and not decision, (rc, decision)
