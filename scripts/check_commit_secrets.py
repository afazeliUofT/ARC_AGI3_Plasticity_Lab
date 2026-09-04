#!/usr/bin/env python3
"""Refuse a commit whose diff carries a credential value.

The human's condition of 2026-09-04T21:47Z (state/escalations/20260904T214700Z.md, Ask 1):
"add a check that no commit diff contains either" the OAuth credential or its alias's value.
This script scans the ADDED lines of a diff for

* any value shaped like an Anthropic credential (``sk-ant-`` followed by a long token body),
  except the two fixed stand-ins the unit tests use, which are short and named here; and
* the live value of ``CLAUDE_CODE_OAUTH_TOKEN`` and of the supervisor's alias
  ``PLASTICITY_LAB_OAUTH_TOKEN`` when either is present in this process's environment.

It prints the diff location and the rule that fired, never the value. Exit 0 when clean,
1 when a secret is found, 2 on a usage error. Standard library only, so the git pre-commit
hook can run it with the system ``python3`` before ``uv`` is on the path::

    python3 scripts/check_commit_secrets.py --staged            # what `git commit` would take
    python3 scripts/check_commit_secrets.py --commit <sha>      # one existing commit
    python3 scripts/check_commit_secrets.py --range A..B        # a range of commits

Install as a hook (per clone; .git/hooks is not versioned) with ``--install-hook``. The alias
*name* is not flagged: it must appear in the adapter and its tests. Artifact scans for the
name live in tests/unit/test_headless_client.py.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_ENV_KEYS: tuple[str, ...] = ("CLAUDE_CODE_OAUTH_TOKEN", "PLASTICITY_LAB_OAUTH_TOKEN")
# Test stand-ins (tests/unit/test_headless_client.py). Anything else with the prefix is a hit.
ALLOWED_STAND_INS: frozenset[str] = frozenset(
    {"sk-ant-oat01-TESTTOKEN-not-a-real-credential", "sk-ant-oat01-SECRET", "sk-ant-oat01-OTHER"}
)
CREDENTIAL_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")
MIN_LIVE_VALUE_LENGTH = 16
HOOK_PATH = ROOT / ".git" / "hooks" / "pre-commit"
HOOK_BODY = """#!/bin/sh
# Installed by scripts/check_commit_secrets.py --install-hook (2026-09-04). Refuses a commit
# whose staged diff carries a credential value. Bypass only with an explicit --no-verify.
cd "$(git rev-parse --show-toplevel)" || exit 2
exec python3 scripts/check_commit_secrets.py --staged
"""


@dataclass(frozen=True)
class Finding:
    file: str
    line_in_diff: int
    rule: str

    def __str__(self) -> str:
        return f"{self.file}: diff line {self.line_in_diff}: {self.rule}"


def live_values(environ: dict[str, str] | os._Environ[str]) -> dict[str, str]:
    """The credential values present in ``environ`` (long enough to be unambiguous)."""
    return {
        key: environ[key]
        for key in TOKEN_ENV_KEYS
        if len(environ.get(key, "")) >= MIN_LIVE_VALUE_LENGTH
    }


def scan_diff_text(diff: str, values: dict[str, str]) -> list[Finding]:
    """Findings over the added lines of a unified diff. ``values`` maps a variable name to
    the live value to look for; only the name is ever reported."""
    findings: list[Finding] = []
    current = "<unknown>"
    for number, line in enumerate(diff.splitlines(), start=1):
        if line.startswith("+++ "):
            current = line[4:].strip().removeprefix("b/")
            continue
        if not line.startswith("+") or line.startswith("++"):
            continue
        body = line[1:]
        for match in CREDENTIAL_RE.finditer(body):
            if match.group(0) not in ALLOWED_STAND_INS:
                findings.append(Finding(current, number, "credential-shaped value (sk-ant-...)"))
                break
        for name, value in values.items():
            if value and value in body:
                findings.append(Finding(current, number, f"live value of {name}"))
    return findings


def git_diff(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout


def install_hook() -> Path:
    HOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOOK_PATH.write_text(HOOK_BODY)
    HOOK_PATH.chmod(0o755)
    return HOOK_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true", help="scan the staged diff")
    group.add_argument("--commit", help="scan one commit")
    group.add_argument("--range", dest="range_", help="scan a commit range A..B")
    group.add_argument("--install-hook", action="store_true", help="install the pre-commit hook")
    ns = parser.parse_args(argv)
    if ns.install_hook:
        print(f"installed {install_hook()}")
        return 0
    if ns.staged:
        diff = git_diff(["diff", "--cached", "--no-color", "-U0"])
    elif ns.commit:
        diff = git_diff(["show", "--no-color", "-U0", "--format=", ns.commit])
    elif ns.range_:
        diff = git_diff(["diff", "--no-color", "-U0", ns.range_])
    else:
        parser.print_usage()
        return 2
    findings = scan_diff_text(diff, live_values(os.environ))
    for finding in findings:
        print(f"SECRET: {finding}", file=sys.stderr)
    if findings:
        print(f"refused: {len(findings)} credential value(s) in the diff", file=sys.stderr)
        return 1
    print("clean: no credential value in the diff")
    return 0


if __name__ == "__main__":
    sys.exit(main())
