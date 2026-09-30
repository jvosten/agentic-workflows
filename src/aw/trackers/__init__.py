"""Issue tracker contract. Skills call `aw issue <op>`; each tracker implements the ops it supports."""

from __future__ import annotations

import re
import subprocess
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

    def children(self, issue: str) -> list[Row]:
        raise self._unsupported("children")

    def list_open(self, limit: int) -> list[Row]:
        raise self._unsupported("list")

    def search(self, query: str, limit: int, raw: bool) -> list[Row]:
        raise self._unsupported("search")

    def create(self, title: str, body: str, parent: str | None, issue_type: str | None) -> str:
        raise self._unsupported("create")

    def comment(self, issue: str, body: str) -> None:
        raise self._unsupported("comment")

    def set_status(self, issue: str, status: str) -> str:
        raise self._unsupported("set-status")

    def on_start(self, issue: str) -> str | None:
        """Status change when a session starts; None when the tracker has no workflow states."""
        return None

    def on_merged(self, issue: str) -> str | None:
        """Status change after the merge; None when a PR closing keyword handles it."""
        return None


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
        meta.append(f"parent: {issue.parent.id}" + (f" ({issue.parent.title})" if issue.parent.title else ""))
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
    return f"- {status}{row.id}{kind} {row.title}".rstrip()
