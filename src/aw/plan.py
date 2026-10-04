"""Plan documents: where one lives, and what already exists for an issue."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from aw.config import AwError, Config
from aw.trackers import Tracker


def directory(cfg: Config) -> Path:
    plan_dir = cfg.get("plan_dir")
    if not plan_dir:
        raise AwError("plan_dir is not set")
    return cfg.checkout / plan_dir


def find(cfg: Config, issue: str) -> Path | None:
    """The plan whose file name carries this issue id, if it is written already."""
    root = directory(cfg)
    needle = issue.casefold()
    matches = sorted(p for p in root.rglob("*.md") if needle in p.name.casefold())
    return matches[0] if matches else None


def owner(cfg: Config, tracker: Tracker, ref: str) -> tuple[str, Path | None]:
    """Issue whose plan covers this ref (its parent story when the ref is a subtask), and the plan file."""
    issue = tracker.normalize(ref)
    found = find(cfg, issue)
    if found is None and tracker.name != "none":
        parent = tracker.parent(issue)
        if parent:
            return parent.id, find(cfg, parent.id)
    return issue, found


def locate(cfg: Config, tracker: Tracker, ref: str, slug: str | None = None) -> tuple[str, Path]:
    """Issue the plan belongs to and its file, composed from slug when no plan exists yet."""
    if slug:
        issue = tracker.normalize(ref)
        found = find(cfg, issue)
        return issue, found or compose(cfg, issue, slug)
    issue, found = owner(cfg, tracker, ref)
    if found is None:
        raise AwError(f"no plan for {issue} under {directory(cfg)}; pass --slug for the path to write")
    return issue, found


def state(cfg: Config, tracker: Tracker, ref: str) -> dict[str, str]:
    issue, found = owner(cfg, tracker, ref)
    subtasks = tracker.children(issue) if tracker.name != "none" else []
    return {"issue": issue, "plan": str(found) if found else "none",
            "subtasks": " ".join(row.id for row in subtasks)}


def compose(cfg: Config, issue: str, slug: str) -> Path:
    """Where the plan of this issue goes when it is written."""
    name = cfg.get("plan_file", issue=issue, slug=slug, date=date.today().isoformat())
    return directory(cfg) / name
