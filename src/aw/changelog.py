"""Changelog strategies: where a session's entry goes, whether it exists, and collect.

aw places, checks and collects entries. It knows no categories, heading format or versioning scheme: the
project's template shapes an entry, and the caller of collect passes the heading.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, assert_never

from aw import session
from aw.config import Config, git


class Strategy(enum.Enum):
    FILE = "file"
    DIR = "dir"
    NONE = "none"


@dataclass(frozen=True)
class FileTarget:
    path: Path


@dataclass(frozen=True)
class CommitTarget:
    trailer: str = ""


@dataclass(frozen=True)
class NoTarget:
    pass


Target = FileTarget | CommitTarget | NoTarget


class Changelog(Protocol):
    def target(self) -> Target:
        """Where this session's entry goes; the same place again once it exists."""
        ...

    def has_entry(self) -> bool:
        """Whether this session wrote its entry (committed or not)."""
        ...

    def collect(self, heading: str | None) -> tuple[str, ...]:
        """Fold pending entries into the changelog under heading (None: unchanged); the names collected."""
        ...


@dataclass(frozen=True)
class _FileChangelog:
    checkout: Path
    file: Path
    fork_point: str

    def target(self) -> Target:
        return FileTarget(self.file)

    def has_entry(self) -> bool:
        return bool(git("diff", "--name-only", self.fork_point, "--", str(self.file), cwd=self.checkout))

    def collect(self, heading: str | None) -> tuple[str, ...]:  # noqa: ARG002 - the protocol's signature
        return ()


@dataclass(frozen=True)
class _DirChangelog:
    directory: Path
    file: Path
    name: str
    now: Callable[[], datetime]

    def _fragments(self) -> tuple[Path, ...]:
        """Newest first: a fragment's name starts with its UTC timestamp."""
        if not self.directory.is_dir():
            return ()
        return tuple(sorted(self.directory.glob("*.md"), reverse=True))

    def _own(self) -> Path | None:
        return next((p for p in self._fragments() if p.name.partition("-")[2] == f"{self.name}.md"), None)

    def target(self) -> Target:
        own = self._own()
        return FileTarget(own or self.directory / f"{self.now():%Y%m%dT%H%M%SZ}-{self.name}.md")

    def has_entry(self) -> bool:
        return self._own() is not None

    def collect(self, heading: str | None) -> tuple[str, ...]:
        found = self._fragments()
        if not found:
            return ()
        self.file.write_text(_fold(self.file.read_text(), tuple(p.read_text() for p in found), heading))
        for path in found:
            path.unlink()
        return tuple(p.name for p in found)


@dataclass(frozen=True)
class _NoChangelog:
    def target(self) -> Target:
        return NoTarget()

    def has_entry(self) -> bool:
        return True

    def collect(self, heading: str | None) -> tuple[str, ...]:  # noqa: ARG002 - the protocol's signature
        return ()


def _blocks(fragment: str) -> tuple[tuple[str, str], ...]:
    """A fragment as (`### ` line, body) pairs; text before the first such line has the name ""."""
    blocks: list[tuple[str, list[str]]] = [("", [])]
    for line in fragment.splitlines():
        if line.startswith("### "):
            blocks.append((line.strip(), []))
        else:
            blocks[-1][1].append(line)
    return tuple((name, "\n".join(lines).strip()) for name, lines in blocks if name or any(lines))


def _merged(heading: str, fragments: tuple[str, ...]) -> tuple[str, ...]:
    """One section under heading: the fragments' `### ` blocks merged by name, in first-seen order."""
    merged: dict[str, list[str]] = {"": []}
    for fragment in fragments:
        for name, body in _blocks(fragment):
            merged.setdefault(name, []).append(body)
    parts = [
        f"{name}\n\n" + "\n".join(b for b in bodies if b) if name else "\n".join(bodies)
        for name, bodies in merged.items()
    ]
    return (heading, *(part for part in parts if part.strip()))


def _fold(text: str, fragments: tuple[str, ...], heading: str | None) -> str:
    """text with the fragments inserted before its first `## ` line, else appended."""
    parts = _merged(heading, fragments) if heading else fragments
    section = "".join(f"{part.strip()}\n\n" for part in parts)
    lines = text.splitlines(keepends=True)
    at = next((i for i, line in enumerate(lines) if line.startswith("## ")), None)
    if at is None:
        return f"{text.rstrip()}\n\n{section.rstrip()}\n"
    return "".join(lines[:at]) + section + "".join(lines[at:])


def path_keys(cfg: Config) -> tuple[str, ...]:
    """The config keys naming the paths the configured strategy uses."""
    strategy = Strategy(cfg.get("changelog"))
    match strategy:
        case Strategy.FILE:
            return ("changelog_file",)
        case Strategy.DIR:
            return ("changelog_file", "changelog_dir")
        case Strategy.NONE:
            return ()
        case _:
            assert_never(strategy)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def open_changelog(cfg: Config, checkout: Path, fork_point: str, now: Callable[[], datetime] = _utc_now) -> Changelog:
    """The configured changelog of the session in checkout, which forked at fork_point."""
    strategy = Strategy(cfg.get("changelog"))
    file = cfg.inside("changelog_file", checkout / cfg.get("changelog_file"))
    match strategy:
        case Strategy.FILE:
            return _FileChangelog(checkout, file, fork_point)
        case Strategy.DIR:
            directory = cfg.inside("changelog_dir", checkout / cfg.get("changelog_dir"))
            return _DirChangelog(directory, file, checkout.name, now)
        case Strategy.NONE:
            return _NoChangelog()
        case _:
            assert_never(strategy)


def for_session(cfg: Config) -> Changelog:
    """The changelog of the session in the current checkout; raises NoSession outside one."""
    meta = session.read(cfg.checkout)
    since = meta.get("fork_point") or git(
        "merge-base", "HEAD", f"origin/{meta.get('base') or cfg.get('main_branch')}", cwd=cfg.checkout
    )
    return open_changelog(cfg, cfg.checkout, since)


def for_checkout(cfg: Config) -> Changelog:
    """The changelog of the current checkout, for collect: no session needed."""
    return open_changelog(cfg, cfg.checkout, "HEAD")
