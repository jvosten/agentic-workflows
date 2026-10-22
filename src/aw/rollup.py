"""Parent rollup: a story follows its subtasks, in progress with the first session, closable after the last.

Only a story rolls up. An epic (epic_types, a Jira type above story level, a GitHub card without a column)
carries no status of its own and closes by decision, so the rollup never touches it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from aw import plan
from aw.config import AwError, Config
from aw.trackers import Row, Tracker, status_hook


@dataclass(frozen=True)
class NoStory:
    """Nothing to roll up to: no parent, a parent linked by text only, an epic, or a tracker without parent links."""

    reason: str


@dataclass(frozen=True)
class Unknown:
    """The story's children, or which plan is its own, could not be read completely; nothing may close on this."""

    parent: Row
    reason: str


@dataclass(frozen=True)
class Blocked:
    """Something keeps the story open: another open child, or a plan section without a subtask."""

    parent: Row
    children: tuple[Row, ...]
    left: tuple[str, ...]  # what keeps it open, as report prints it
    open: tuple[str, ...] = ()  # ids of the other children still open
    unsplit: tuple[str, ...] = ()  # plan sections without a subtask


@dataclass(frozen=True)
class CanClose:
    """No child open besides the issue itself, and the plan is fully cut into subtasks."""

    parent: Row
    children: tuple[Row, ...]


Decision = NoStory | Unknown | Blocked | CanClose


def story(tracker: Tracker, issue: str) -> tuple[Row | None, str]:
    """The parent a rollup acts on, or None and the reason: no native parent, or an epic."""
    if not tracker.scoped():
        return None, f"{tracker.name} has no parent links"
    parent = tracker.parent(issue)
    if parent is None:
        return None, f"{tracker.ref(issue)} has no parent"
    if parent.link != "native":
        return None, (
            f"{tracker.ref(parent.id)} is a parent by text only; "
            f"`aw issue set-parent {issue} {parent.id}` links it natively"
        )
    if tracker.is_epic(parent):
        return None, f"{tracker.ref(parent.id)} is an epic; epics close by decision, not by rollup"
    return parent, ""


def start(tracker: Tracker, issue: str) -> list[str]:
    """Session start on a subtask: its story moves to in_progress too, under the same guard (backlog or ready)."""
    if not tracker.has_states():
        return []
    parent, _ = story(tracker, issue)
    return tracker.advance(parent.id, "in_progress") if parent else []


def check(cfg: Config, tracker: Tracker, issue: str) -> Decision:
    """Whether issue's story can close once issue is done: no other open child, no plan section left unsplit.

    A failed listing of the children is Unknown, never an empty list.
    """
    parent, reason = story(tracker, issue)
    if parent is None:
        return NoStory(reason)
    try:
        children = tuple(tracker.children(parent.id))
    except AwError as e:
        return Unknown(parent, str(e))
    still_open = [row.id for row in children if row.id != issue and not tracker.closed(row)]
    try:
        path = plan.find(cfg, parent.id)
    except AwError as e:
        return Unknown(parent, str(e))
    sections = plan.unsplit(path) if path else []
    left = [f"{tracker.ref(i)} open" for i in still_open] + [f"plan section {s} has no subtask" for s in sections]
    if not left:
        return CanClose(parent, children)
    return Blocked(parent, children, tuple(left), tuple(still_open), tuple(sections))


def report(tracker: Tracker, issue: str, result: Decision) -> str:
    match result:
        case NoStory(reason):
            return reason
        case Unknown(parent, reason):
            return f"{tracker.ref(parent.id)}: children unknown ({reason})"
        case Blocked(parent, _, left):
            return f"{tracker.ref(parent.id)} stays open: {'; '.join(left)}"
        case CanClose(parent, children):
            names = ", ".join(tracker.ref(row.id) for row in children)
            return f"{tracker.ref(parent.id)} can close: no child open besides {tracker.ref(issue)} (children: {names})"


def data(tracker: Tracker, issue: str, result: Decision) -> dict[str, object]:
    """The decision for skills to branch on (`aw issue rollup --json`); `line` is report's text, to show as it is.

    children, open and unsplit are null unless the children were read: a failed listing is never an empty one.
    """
    out: dict[str, object] = {"story": None, "children": None, "open": None, "unsplit": None, "reason": None}
    match result:
        case NoStory(reason):
            out |= {"decision": "no_story", "reason": reason}
        case Unknown(parent, reason):
            out |= {"decision": "unknown", "story": parent.id, "reason": reason}
        case Blocked(parent, children, _, still_open, sections):
            ids = [row.id for row in children]
            out |= {"decision": "stays_open", "story": parent.id, "children": ids}
            out |= {"open": list(still_open), "unsplit": list(sections)}
        case CanClose(parent, children):
            ids = [row.id for row in children]
            out |= {"decision": "can_close", "story": parent.id, "children": ids, "open": [], "unsplit": []}
        case _:
            assert_never(result)
    return {"decision": out.pop("decision"), **out, "line": report(tracker, issue, result)}


def decide(cfg: Config, tracker: Tracker, issue: str) -> dict[str, object]:
    """data() for the issue; a lookup that fails before check() can decide is an unknown story, not an error."""
    try:
        result = check(cfg, tracker, issue)
    except AwError as e:
        keys = ("story", "children", "open", "unsplit")
        line = f"{tracker.ref(issue)}: parent story unknown ({e})"
        return {"decision": "unknown", **dict.fromkeys(keys), "reason": str(e), "line": line}
    return data(tracker, issue, result)


def close(cfg: Config, tracker: Tracker, issue: str) -> list[str]:
    """Close issue's story as done, with a comment naming its children; refuses unless the decision is CanClose."""
    cfg.on_host("aw issue rollup --close")
    result = check(cfg, tracker, issue)
    if not isinstance(result, CanClose):
        raise AwError(f"{report(tracker, issue, result)}; nothing closed")
    parent = result.parent.id
    messages = [tracker.set_status(parent, "done")]
    if hook := status_hook(cfg, parent, "done"):
        messages.append(hook)
    names = ", ".join(tracker.ref(row.id) for row in result.children)
    tracker.comment(parent, f"All children are closed ({names}); closed after {tracker.ref(issue)}.")
    messages.append(f"commented on {tracker.ref(parent)}")
    return messages
