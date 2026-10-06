"""Session metadata, kept in the worktree's private git dir (never committed).

It holds what git cannot tell: the issue, the session's type and slug, when it started. Branch and worktree
come from git on every read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aw.config import AwError, checkout_root, dump_toml, git, read_toml

META = "aw-session.toml"


def _meta_path(cwd: Path | str | None) -> Path:
    return Path(git("rev-parse", "--absolute-git-dir", cwd=cwd)) / META


def write(worktree: Path, meta: dict[str, Any]) -> None:
    _meta_path(worktree).write_text(dump_toml(meta))


def update(cwd: Path | str | None = None, **fields: Any) -> None:
    """Add or change fields of an existing session's metadata."""
    path = _meta_path(cwd)
    if not path.is_file():
        raise AwError("not in a session worktree (no aw-session metadata); start one with `aw start-task`")
    path.write_text(dump_toml(read_toml(path) | fields))


def read(cwd: Path | str | None = None) -> dict[str, Any]:
    path = _meta_path(cwd)
    if not path.is_file():
        raise AwError("not in a session worktree (no aw-session metadata); start one with `aw start-task`")
    meta = read_toml(path)
    meta["branch"] = git("branch", "--show-current", cwd=cwd)
    meta["worktree"] = str(checkout_root(cwd))
    return meta
