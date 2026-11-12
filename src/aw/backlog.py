"""Backlog file: the backlog itself, or a session inbox that aw-finalize empties into the tracker.

backlog_home = file     the file is the backlog; items may also be pushed to the tracker
backlog_home = tracker  the file collects items during a session; each one goes to the tracker or is
                        discarded before the merge, and the emptied file is deleted
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

from aw.config import AwError, Config

HEADING = re.compile(r"^(#{2,6})\s+(.*\S)\s*$")
RULE = "---"


def file(cfg: Config, checkout: Path | None = None) -> Path:
    name = cfg.get("backlog_file")
    if not name:
        raise AwError("backlog_file is not set")
    return cfg.inside("backlog_file", (checkout or cfg.checkout) / name)


def home(cfg: Config) -> str:
    """tracker or file; without a tracker the file is the only home."""
    return "file" if cfg.get("tracker") == "none" else cfg.get("backlog_home")


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, title) for every Markdown heading."""
    return [(i, len(m.group(1)), m.group(2)) for i, line in enumerate(lines) if (m := HEADING.match(line.rstrip("\n")))]


def _item_level(headings: list[tuple[int, int, str]]) -> int:
    """Heading level the file uses for items: the level of the first heading under `## Items`, else the shallowest
    level that repeats. Sub-headings inside items repeat too, so the deepest repeating level would split items."""
    for (_, level, title), (_, below, _) in pairwise(headings):
        if title.lower() == "items" and below > level:
            return below
    levels = [level for _, level, _ in headings]
    repeated = [level for level in sorted(set(levels)) if levels.count(level) > 1]
    return repeated[0] if repeated else 2


def _splits_with_rules(lines: list[str], level: int) -> bool:
    """True when the file separates items of this level with horizontal rules."""
    items = [i for i, lvl, _ in _headings(lines) if lvl == level]
    return any(any(line.strip() == RULE for line in lines[a + 1 : b]) for a, b in pairwise(items))


def _join(*blocks: str) -> str:
    """One blank line between every non-empty block, one newline at the end."""
    kept = [block.strip("\n").rstrip() for block in blocks if block.strip()]
    return "\n\n".join(kept) + "\n"


def titles(cfg: Config, checkout: Path | None = None) -> list[str]:
    """Item headings in the backlog file, in file order."""
    path = file(cfg, checkout)
    if not path.is_file():
        return []
    headings = _headings(path.read_text().splitlines(keepends=True))
    if not headings:
        return []
    level = _item_level(headings)
    return [title for _, lvl, title in headings if lvl == level]


def add(cfg: Config, title: str, text: str) -> Path:
    """Put the item at the end of the file's run of items, in the file's own shape."""
    path = file(cfg)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Backlog\n\nDeferred work. Each item carries enough context to be picked up later.\n")
    lines = path.read_text().splitlines(keepends=True)
    headings = _headings(lines)
    level = _item_level(headings)
    for _, lvl, heading in _headings(text.splitlines(keepends=True)):
        if lvl <= level:
            raise AwError(
                f"the body's heading {'#' * lvl + ' ' + heading!r} would be an item of its own; "
                f"use {'#' * (level + 1)} or deeper"
            )
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
    if home(cfg) == "tracker" and not titles(cfg):
        path.unlink()  # an empty inbox is not committed
    return path
