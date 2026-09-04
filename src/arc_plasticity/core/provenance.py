"""Provenance facts recorded in every run manifest: git state, lockfile hash, host, Python.

Nothing here is a result. These values exist so a referee can tie an artifact to the exact
code, dependencies and machine that produced it (AGENT_CONSTITUTION.md section 11).
"""

from __future__ import annotations

import hashlib
import os
import platform
import socket
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any


class ProvenanceError(RuntimeError):
    """A provenance fact the manifest requires could not be established."""


@dataclass(frozen=True)
class GitState:
    commit: str
    dirty: bool
    porcelain: str

    def as_text(self) -> str:
        lines = [f"commit {self.commit}", f"dirty {'true' if self.dirty else 'false'}"]
        if self.porcelain:
            lines.append("status --porcelain:")
            lines.extend(self.porcelain.splitlines())
        return "\n".join(lines) + "\n"


def _git(args: list[str], root: Path) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False, timeout=60
    )
    if proc.returncode != 0:
        raise ProvenanceError(f"git {' '.join(args)} failed in {root}: {proc.stderr.strip()}")
    return proc.stdout


def git_state(root: Path) -> GitState:
    commit = _git(["rev-parse", "HEAD"], root).strip()
    porcelain = _git(["status", "--porcelain"], root).rstrip("\n")
    return GitState(commit=commit, dirty=bool(porcelain.strip()), porcelain=porcelain)


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dependency_lock_hash(root: Path) -> str:
    lock = root / "uv.lock"
    if not lock.exists():
        raise ProvenanceError(f"{lock} does not exist; the manifest requires the lockfile hash")
    return sha256_of_file(lock)


def python_version() -> str:
    return platform.python_version()


def hardware_description() -> str:
    cpu = platform.processor() or platform.machine()
    return f"{platform.system()} {platform.release()} {platform.machine()} cpu={cpu} cores={os.cpu_count()}"


def _distribution_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def environment_info() -> dict[str, Any]:
    """Facts about the host and interpreter for ``environment_info.json``.

    Deliberately excluded from the determinism comparison: it is expected to differ across
    hosts and is checked for presence, not identity.
    """
    return {
        "python_version": python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable_path": sys.executable,
        "platform": platform.platform(),
        "hardware": hardware_description(),
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "packages": {
            name: _distribution_version(name)
            for name in ("arc-agi", "arcengine", "numpy", "pydantic", "pyyaml")
        },
    }
