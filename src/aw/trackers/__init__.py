"""Issue tracker contract. Skills call `aw issue <op>`; each tracker implements the ops it supports."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from aw.config import AwError, Config

STATUSES = ("backlog", "ready", "in_progress", "in_review", "done")


@dataclass
class Row:
    id: str
    title: str = ""
    status: str = ""
    type: str = ""
    link: str = ""  # how a parent or child is linked: native | text; empty outside parent-child results


@dataclass
class Issue:
    id: str
    ref: str
    title: str
    status: str
    url: str = ""
    type: str = ""
    labels: list[str] = field(default_factory=list)
    parent: Row | None = None
    body: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    children: list[Row] = field(default_factory=list)
    comments: list[tuple[str, str]] = field(default_factory=list)


def run(args: list[str], cwd: Path, stdin: str | None = None) -> str:
    try:
        r = subprocess.run(args, cwd=cwd, input=stdin, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise AwError(f"{args[0]} not found") from None
    if r.returncode:
        raise AwError(f"{' '.join(args[:3])}: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


class Tracker:
    name = "none"
    id_pattern = re.compile(r"^[A-Za-z0-9_.-]+$")

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def normalize(self, raw: str) -> str:
        value = raw.strip().removeprefix("#")
        if not self.id_pattern.match(value):
            raise AwError(f"invalid {self.name} issue id: {raw!r}")
        return value

    def ref(self, issue: str) -> str:
        return issue

    def pr_text(self, issue: str) -> str:
        return self.ref(issue)

    def _unsupported(self, op: str) -> AwError:
        return AwError(f"tracker {self.name!r} does not support `aw issue {op}`")

    def view(self, issue: str) -> Issue:
        raise self._unsupported("view")

    def parent(self, issue: str) -> Row | None:
        return self.view(issue).parent

    def children(self, issue: str) -> list[Row]:
        raise self._unsupported("children")

    def text_children(self, issue: str) -> list[Row]:
        """Children linked to this issue only by text, not by the tracker's own parent link."""
        return [row for row in self.children(issue) if row.link == "text"]

    def set_parent(self, issue: str, parent: str | None) -> str:
        raise self._unsupported("set-parent")

    def list_open(self, limit: int) -> list[Row]:
        raise self._unsupported("list")

    def search(self, query: str, limit: int, raw: bool) -> list[Row]:
        raise self._unsupported("search")

    def create(self, title: str, body: str, parent: str | None, issue_type: str | None,
               labels: list[str] | None = None) -> str:
        raise self._unsupported("create")

    def comment(self, issue: str, body: str) -> None:
        raise self._unsupported("comment")

    def update(self, issue: str, title: str | None, body: str | None) -> None:
        raise self._unsupported("update")

    def set_status(self, issue: str, status: str) -> str:
        raise self._unsupported("set-status")

    def scoped(self) -> bool:
        """True when this tracker knows parent-child links, so dupes can be scoped."""
        return type(self).children is not Tracker.children

    def dupes(self, parent: str, terms: list[str], limit: int) -> list[Row]:
        """Issues under parent (two levels of native links) that match any term in title or body."""
        scope: dict[str, Row] = {}
        if self.scoped():
            for child in self.native_children(parent):
                scope[child.id] = child
                for grandchild in self.native_children(child.id):
                    scope[grandchild.id] = grandchild
        hits: dict[str, Row] = {}
        for term in terms:
            for row in self.search(term, limit, raw=False):
                if row.id in scope or not scope:
                    hits[row.id] = row
        for row in scope.values():
            if any(term.casefold() in row.title.casefold() for term in terms):
                hits[row.id] = row
        return sorted(hits.values(), key=lambda row: row.id)

    def native_children(self, issue: str) -> list[Row]:
        return [row for row in self.children(issue) if row.link != "text"]

    def has_states(self) -> bool:
        """True when set_status moves the issue through workflow states (Jira, a GitHub board)."""
        return False

    def current_status(self, issue: str) -> str | None:
        """The tracker's name for the issue's current state; None when unknown or stateless."""
        return None

    def advance(self, issue: str, target: str) -> list[str]:
        """Automatic move at session start (in_progress) or after the merge (done); never backwards.

        An explicit `aw issue set-status` is not guarded: someone chose that state.
        """
        if target == "in_progress":
            current = self.current_status(issue)
            if current and canonical(self.cfg, current) not in (None, "backlog", "ready"):
                return [f"{self.ref(issue)} stays at {current}: a session start moves only from backlog or ready"]
        messages = [self.set_status(issue, target)] if self.has_states() else []
        if hook := status_hook(self.cfg, issue, target):
            messages.append(hook)
        return messages


def status_name(cfg: Config, status: str) -> str:
    """The tracker's (or board's) name for a canonical status: status_map, else title case."""
    if status not in STATUSES:
        raise AwError(f"status must be one of {', '.join(STATUSES)}")
    return cfg.get("status_map").get(status) or status.replace("_", " ").title()


def canonical(cfg: Config, name: str) -> str | None:
    """The canonical status a tracker or board name stands for, through status_map; None when unmapped."""
    return next((s for s in STATUSES if status_name(cfg, s).casefold() == name.casefold()), None)


def status_hook(cfg: Config, issue: str, status: str) -> str | None:
    """Run on_issue_status after a status change, e.g. to move the issue on a project board."""
    if not cfg.values["on_issue_status"]:
        return None
    cmd = cfg.get("on_issue_status", issue=issue, status=status, status_name=status_name(cfg, status))
    r = subprocess.run(cmd, shell=True, cwd=cfg.checkout, stdout=sys.stderr, check=False)
    if r.returncode:
        raise AwError(f"on_issue_status exited {r.returncode}: {cmd}")
    return f"on_issue_status: {cmd}"


def get(cfg: Config) -> Tracker:
    from aw.trackers import github, gitlab, jira

    kinds: dict[str, type[Tracker]] = {
        "none": Tracker, "github": github.GitHub, "gitlab": gitlab.GitLab, "jira": jira.Jira,
    }
    return kinds[cfg.get("tracker")](cfg)


def render(issue: Issue) -> str:
    meta = [f"status: {issue.status or 'unknown'}"]
    if issue.type:
        meta.append(f"type: {issue.type}")
    if issue.parent:
        title = f" ({issue.parent.title})" if issue.parent.title else ""
        meta.append(f"parent: {issue.parent.id}{title}" + (" [text link]" if issue.parent.link == "text" else ""))
    if issue.labels:
        meta.append(f"labels: {', '.join(issue.labels)}")
    lines = [f"# {issue.ref}: {issue.title}", "", " · ".join(meta)]
    if issue.url:
        lines.append(issue.url)
    lines += ["", "## Description", "", issue.body.strip() or "_none_"]
    for name, text in issue.sections.items():
        lines += ["", f"## {name.replace('_', ' ').capitalize()}", "", text.strip() or "_none_"]
    if issue.children:
        lines += ["", f"## Children ({len(issue.children)})", ""]
        lines += [rows_line(r) for r in issue.children]
    if issue.comments:
        lines += ["", f"## Comments ({len(issue.comments)})"]
        for author, body in issue.comments:
            lines += ["", f"### {author}", "", body.strip()]
    return "\n".join(lines) + "\n"


def rows_line(row: Row) -> str:
    status = f"[{row.status}] " if row.status else ""
    kind = f" ({row.type})" if row.type else ""
    link = " [text link]" if row.link == "text" else ""
    return f"- {status}{row.id}{kind} {row.title}".rstrip() + link
