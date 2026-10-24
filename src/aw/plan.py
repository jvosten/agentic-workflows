"""Plan documents: where one lives, and what already exists for an issue."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from aw.config import AwError, Config, git
from aw.trackers import Row, Tracker

PLACEHOLDER = re.compile(r"\\\{(\w+)\\\}")
SECTION = re.compile(r"^### (S\d+)\b", re.MULTILINE)
SUBTASK = re.compile(r"^\*\*Subtask:\*\*(.*)$", re.MULTILINE)


def directory(cfg: Config) -> Path:
    """Plan directory: in the current checkout when plans are committed, in the primary one when they are local.

    Local plans are untracked, and a session worktree does not see untracked files of the primary checkout,
    so every worktree reads and writes them in one place.
    """
    plan_dir = cfg.get("plan_dir") or cfg.schema["plan_dir"]["default"]
    base = cfg.root if cfg.get("plan_scope") == "local" else cfg.checkout
    return cfg.inside("plan_dir", base / plan_dir)


def ignored(cfg: Config) -> bool:
    # A path inside the directory: a `plans/` pattern matches only directories, and this one may not exist yet.
    try:
        git("check-ignore", "-q", str(directory(cfg) / "plan.md"), cwd=cfg.root)
    except AwError:
        return False
    return True


def _name_pattern(cfg: Config, issue: str) -> re.Pattern[str]:
    """File names plan_file produces for this issue, whatever the slug and date."""
    name = cfg.values["plan_file"].rsplit("/", 1)[-1]
    if "{issue}" not in name:
        raise AwError(f"plan_file must carry {{issue}} in its file name: {cfg.values['plan_file']!r}")
    escaped = re.escape(name)
    return re.compile(
        "^" + PLACEHOLDER.sub(lambda m: re.escape(issue) if m.group(1) == "issue" else "[^/]*", escaped) + "$",
        re.IGNORECASE,
    )


def find(cfg: Config, issue: str) -> Path | None:
    """The plan whose file name carries this issue id, if it is written already. Several are refused: which one
    is current is not decided by sort order."""
    pattern = _name_pattern(cfg, issue)
    matches = sorted(p for p in directory(cfg).rglob("*.md") if pattern.match(p.name))
    if len(matches) > 1:
        raise AwError(f"several plans for {issue}; keep one:\n" + "\n".join(f"  {p}" for p in matches))
    return matches[0] if matches else None


def owner(cfg: Config, tracker: Tracker, ref: str) -> tuple[str, Path | None]:
    """Issue whose plan covers this ref (its parent story when the ref is a subtask), and the plan file."""
    issue = tracker.normalize(ref)
    found = find(cfg, issue)
    if found is None and tracker.name != "none":
        parent = tracker.parent(issue)
        if parent and not tracker.is_epic(parent):
            return parent.id, find(cfg, parent.id)
    return issue, found


def locate(cfg: Config, tracker: Tracker, ref: str, slug: str | None = None) -> tuple[str, Path]:
    """Issue the plan belongs to and its file, composed from slug when no plan exists yet."""
    if slug:
        issue = tracker.normalize(ref)
        found = find(cfg, issue)
        return issue, found or compose(cfg, issue, slug, tracker.parent(issue) if tracker.name != "none" else None)
    issue, found = owner(cfg, tracker, ref)
    if found is None:
        raise AwError(f"no plan for {issue} under {directory(cfg)}; pass --slug for the path to write")
    return issue, found


def state(cfg: Config, tracker: Tracker, ref: str) -> dict[str, str]:
    issue, found = owner(cfg, tracker, ref)
    subtasks = tracker.children(issue) if tracker.scoped() else []
    return {"issue": issue, "plan": str(found) if found else "none", "subtasks": " ".join(row.id for row in subtasks)}


def unsplit(path: Path) -> list[str]:
    """Implementation sections whose **Subtask:** line names no issue: work never cut into a subtask."""
    text = path.read_text()
    marks = list(SECTION.finditer(text))
    left = []
    for mark, after in zip(marks, [*marks[1:], None], strict=True):
        line = SUBTASK.search(text, mark.end(), after.start() if after else len(text))
        value = line.group(1).strip() if line else ""
        if not re.search(r"\d", value) or value.casefold().startswith(("none", "<")):
            left.append(mark.group(1))
    return left


def slugify(text: str, words: int = 5) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", text.casefold())[:words])


def compose(cfg: Config, issue: str, slug: str, parent: Row | None = None) -> Path:
    """Where the plan of this issue goes when it is written. No parent → the area folder drops out."""
    parent_slug = slugify(parent.title) if parent and parent.title else ""
    area = "-".join(filter(None, (parent.id if parent else "", parent_slug)))
    name = cfg.get(
        "plan_file",
        issue=issue,
        slug=slug,
        date=date.today().isoformat(),
        parent=parent.id if parent else "",
        parent_slug=parent_slug,
        area=area,
    )
    parts = [part for part in name.split("/") if part.strip("-_ ")]
    return directory(cfg).joinpath(*parts)
