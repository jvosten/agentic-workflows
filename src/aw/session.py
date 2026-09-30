"""Session metadata, kept in the worktree's private git dir (never committed)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aw.config import AwError, dump_toml, git, read_toml

META = "aw-session.toml"


def _meta_path(cwd: Path | str | None) -> Path:
    return Path(git("rev-parse", "--absolute-git-dir", cwd=cwd)) / META


def write(worktree: Path, meta: dict[str, Any]) -> None:
    _meta_path(worktree).write_text(dump_toml(meta))


def read(cwd: Path | str | None = None) -> dict[str, Any]:
    path = _meta_path(cwd)
    if not path.is_file():
        raise AwError("not in a session worktree (no aw-session metadata); start one with `aw start-task`")
    return read_toml(path)
