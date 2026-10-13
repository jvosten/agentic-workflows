"""Session metadata, kept in the worktree's private git dir (never committed).

It holds what git cannot tell: the issue, the session's type and slug, when it started. Branch and worktree
come from git on every read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aw.config import AwError, checkout_root, dump_toml, git, read_toml

META = "aw-session.toml"
FIELDS = {  # stored field -> type; branch and worktree are not stored, git tells them
    "session": int,
    "issue": str,
    "type": str,
    "slug": str,
    "started": str,
    "base": str,
    "fork_point": str,
    "restack_onto": str,
    "memory_start_tokens": int,
}


class NoSession(AwError):
    """Not in a session worktree. Only this means "outside a session"; an unreadable session file is an error."""


def _meta_path(cwd: Path | str | None) -> Path:
    return Path(git("rev-parse", "--absolute-git-dir", cwd=cwd)) / META


def write(worktree: Path, meta: dict[str, Any]) -> None:
    _meta_path(worktree).write_text(dump_toml(meta))


def _stored(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise NoSession("not in a session worktree (no aw-session metadata); start one with `aw start-task`")
    meta = read_toml(path)
    for key, kind in FIELDS.items():
        value = meta.get(key)
        if value is not None and (not isinstance(value, kind) or isinstance(value, bool)):
            raise AwError(f"{path}: {key} must be {'a whole number' if kind is int else 'a string'}, not {value!r}")
    if meta.get("base") and not meta.get("fork_point"):
        raise AwError(f"{path}: base needs fork_point, the commit the session was cut from")
    return meta


def update(cwd: Path | str | None = None, **fields: Any) -> None:
    """Add or change fields of an existing session's metadata."""
    path = _meta_path(cwd)
    path.write_text(dump_toml(_stored(path) | fields))


def read(cwd: Path | str | None = None) -> dict[str, Any]:
    """Stored fields, checked, plus branch and worktree (a Path) from git."""
    meta = _stored(_meta_path(cwd))
    meta["branch"] = git("branch", "--show-current", cwd=cwd)
    meta["worktree"] = checkout_root(cwd)
    return meta
