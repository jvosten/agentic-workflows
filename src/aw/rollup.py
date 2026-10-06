"""Parent rollup: a story follows its subtasks, in progress with the first session, closable after the last.

Only a story rolls up. An epic (epic_types, a Jira type above story level, a GitHub card without a column)
carries no status of its own and closes by decision, so the rollup never touches it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aw import plan
from aw.config import AwError, Config
from aw.trackers import Row, Tracker, status_hook


@dataclass
class Check:
    parent: Row | None = None
    children: list[Row] = field(default_factory=list)
    left: list[str] = field(default_factory=list)  # what keeps the parent open: open children, unsplit sections
    reason: str = ""  # why there is no parent to roll up to


def story(tracker: Tracker, issue: str) -> tuple[Row | None, str]:
    """The parent a rollup acts on, or None and the reason: no native parent, or an epic."""
    if not tracker.scoped():
        return None, f"{tracker.name} has no parent links"
    parent = tracker.parent(issue)
    if parent is None:
        return None, f"{tracker.ref(issue)} has no parent"
    if parent.link != "native":
        return None, (f"{tracker.ref(parent.id)} is a parent by text only; "
                      f"`aw issue set-parent {issue} {parent.id}` links it natively")
    if tracker.is_epic(parent):
        return None, f"{tracker.ref(parent.id)} is an epic; epics close by decision, not by rollup"
    return parent, ""


def start(tracker: Tracker, issue: str) -> list[str]:
    """Session start on a subtask: its story moves to in_progress too, under the same guard (backlog or ready)."""
    if not tracker.has_states():
        return []
    parent, _ = story(tracker, issue)
    return tracker.advance(parent.id, "in_progress") if parent else []


def check(cfg: Config, tracker: Tracker, issue: str) -> Check:
    """Whether issue's story can close once issue is done: no other open child, no plan section left unsplit."""
    parent, reason = story(tracker, issue)
    if parent is None:
        return Check(reason=reason)
    children = tracker.children(parent.id)
    left = [f"{tracker.ref(row.id)} open" for row in children if row.id != issue and not tracker.closed(row)]
    if path := plan.find(cfg, parent.id):
        left += [f"plan section {name} has no subtask" for name in plan.unsplit(path)]
    return Check(parent, children, left)


def report(tracker: Tracker, issue: str, result: Check) -> str:
    if result.parent is None:
        return result.reason
    ref = tracker.ref(result.parent.id)
    if result.left:
        return f"{ref} stays open: {'; '.join(result.left)}"
    names = ", ".join(tracker.ref(row.id) for row in result.children)
    return f"{ref} can close: no child open besides {tracker.ref(issue)} (children: {names})"


def close(cfg: Config, tracker: Tracker, issue: str) -> list[str]:
    """Close issue's story as done, with a comment naming its children; refuses while anything keeps it open."""
    result = check(cfg, tracker, issue)
    if result.parent is None or result.left:
        raise AwError(f"{report(tracker, issue, result)}; nothing closed")
    parent = result.parent.id
    messages = [tracker.set_status(parent, "done")]
    if hook := status_hook(cfg, parent, "done"):
        messages.append(hook)
    names = ", ".join(tracker.ref(row.id) for row in result.children)
    tracker.comment(parent, f"All children are closed ({names}); closed after {tracker.ref(issue)}.")
    messages.append(f"commented on {tracker.ref(parent)}")
    return messages
