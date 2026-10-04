"""Repo backlog file: add an item, pop it once the tracker has one."""

from __future__ import annotations

import re
from pathlib import Path

from aw.config import AwError, Config

HEADING = re.compile(r"^(#{2,6})\s+(.*\S)\s*$")
RULE = "---"


def file(cfg: Config) -> Path:
    name = cfg.get("backlog_file")
    if not name:
        raise AwError("backlog_file is not set")
    return cfg.checkout / name


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, title) for every Markdown heading."""
    return [(i, len(m.group(1)), m.group(2))
            for i, line in enumerate(lines) if (m := HEADING.match(line.rstrip("\n")))]


def _item_level(headings: list[tuple[int, int, str]]) -> int:
    """Heading level the file uses for items: the deepest level that repeats."""
    levels = [level for _, level, _ in headings]
    repeated = [level for level in sorted(set(levels)) if levels.count(level) > 1]
    return repeated[-1] if repeated else 2


def _splits_with_rules(lines: list[str], level: int) -> bool:
    """True when the file separates items of this level with horizontal rules."""
    items = [i for i, lvl, _ in _headings(lines) if lvl == level]
    return any(any(line.strip() == RULE for line in lines[a + 1:b]) for a, b in zip(items, items[1:]))


def _join(*blocks: str) -> str:
    """One blank line between every non-empty block, one newline at the end."""
    kept = [block.strip("\n").rstrip() for block in blocks if block.strip()]
    return "\n\n".join(kept) + "\n"


def add(cfg: Config, title: str, text: str) -> Path:
    """Put the item at the end of the file's run of items, in the file's own shape."""
    path = file(cfg)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Backlog\n\nDeferred work. Each item carries enough context to be picked up later.\n")
    lines = path.read_text().splitlines(keepends=True)
    headings = _headings(lines)
    level = _item_level(headings)
    entry = f"{'#' * level} {title}\n\n{text.strip()}\n"
    if _splits_with_rules(lines, level):
        entry = f"{RULE}\n\n{entry}"
    items = [i for i, lvl, _ in headings if lvl == level]
    after = [i for i, lvl, _ in headings if items and i > items[-1] and lvl <= level]
    at = after[0] if after else len(lines)
    while at > 0 and lines[at - 1].strip() in ("", RULE):  # a rule closing the item list stays after the new item
        at -= 1
    path.write_text(_join("".join(lines[:at]), entry, "".join(lines[at:])))
    return path


def pop(cfg: Config, title: str) -> Path:
    """Remove the item with this heading, and the rule that separated it."""
    path = file(cfg)
    if not path.is_file():
        raise AwError(f"{path} does not exist")
    lines = path.read_text().splitlines(keepends=True)
    headings = _headings(lines)
    found = next(((i, level) for i, level, text in headings if text == title), None)
    if found is None:
        raise AwError(f"{path}: no item titled {title!r}")
    start, level = found
    end = next((i for i, lvl, _ in headings if i > start and lvl <= level), len(lines))
    before = "".join(lines[:start]).rstrip()
    while before.endswith(RULE):
        before = before[: -len(RULE)].rstrip()
    path.write_text(_join(before, "".join(lines[end:])))
    return path
