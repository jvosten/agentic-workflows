"""Pull/merge request operations per forge."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from aw.config import AwError

MERGE_FLAGS = {
    "github": {"merge": "--merge", "squash": "--squash", "rebase": "--rebase"},
    "gitlab": {"merge": None, "squash": "--squash", "rebase": "--rebase"},
}


def _run(args: list[str], cwd: Path) -> str:
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if r.returncode:
        raise AwError(f"{' '.join(args[:3])}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def is_merged(forge: str, pr: str, cwd: Path) -> bool:
    if forge == "github":
        state = json.loads(_run(["gh", "pr", "view", pr, "--json", "state"], cwd))["state"]
        return state == "MERGED"
    if forge == "gitlab":
        state = json.loads(_run(["glab", "mr", "view", pr, "--output", "json"], cwd))["state"]
        return state == "merged"
    raise AwError(f"forge {forge!r} has no pull requests")


def merge(forge: str, pr: str, method: str, cwd: Path) -> None:
    """Merge without deleting the head branch; the worktree still has it checked out."""
    flag = MERGE_FLAGS[forge][method]
    if forge == "github":
        _run(["gh", "pr", "merge", pr, flag], cwd)
    elif forge == "gitlab":
        _run(["glab", "mr", "merge", pr, "--yes", "--remove-source-branch=false",
              *([flag] if flag else [])], cwd)
    else:
        raise AwError(f"forge {forge!r} has no pull requests")
