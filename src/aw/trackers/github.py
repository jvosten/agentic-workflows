"""GitHub Issues via the gh CLI."""

from __future__ import annotations

import json
import re
from typing import Any

from aw.config import AwError
from aw.trackers import STATUSES, Issue, Row, Tracker, run

PART_OF = re.compile(r"\bPart of #(\d+)", re.IGNORECASE)
TASK_REF = re.compile(r"^\s*[-*] \[[ xX]\] .*?#(\d+)", re.MULTILINE)


class GitHub(Tracker):
    name = "github"
    id_pattern = re.compile(r"^\d+$")

    def ref(self, issue: str) -> str:
        return f"#{issue}"

    def pr_text(self, issue: str) -> str:
        return f"{self.cfg.get('pr_close_keyword')} #{issue}"

    def gh(self, *args: str, stdin: str | None = None) -> str:
        return run(["gh", *args], self.cfg.checkout, stdin)

    def gh_json(self, *args: str) -> Any:
        return json.loads(self.gh(*args) or "null")

    @staticmethod
    def _row(d: dict) -> Row:
        return Row(str(d["number"]), d.get("title", ""), d.get("state", "").lower())

    def view(self, issue: str) -> Issue:
        d = self.gh_json("issue", "view", issue, "--json", "number,title,body,state,url,labels,comments")
        body = d.get("body") or ""
        parent = None
        if m := PART_OF.search(body):
            parent = Row(m.group(1))
        return Issue(
            id=str(d["number"]), ref=f"#{d['number']}", title=d["title"], status=d["state"].lower(),
            url=d.get("url", ""), labels=[lb["name"] for lb in d.get("labels", [])], parent=parent, body=body,
            children=self.children(issue, body),
            comments=[((c.get("author") or {}).get("login", "unknown"), c.get("body", ""))
                      for c in d.get("comments", [])],
        )

    def children(self, issue: str, body: str | None = None) -> list[Row]:
        try:
            subs = self.gh_json("api", f"repos/{{owner}}/{{repo}}/issues/{issue}/sub_issues") or []
        except AwError:
            subs = []
        rows = [self._row(s) for s in subs]
        if body is None:
            body = self.gh_json("issue", "view", issue, "--json", "body").get("body") or ""
        known = {r.id for r in rows}
        for n in dict.fromkeys(TASK_REF.findall(body)):
            if n not in known:
                try:
                    rows.append(self._row(self.gh_json("issue", "view", n, "--json", "number,title,state")))
                except AwError:
                    rows.append(Row(n))
        return rows

    def list_open(self, limit: int) -> list[Row]:
        data = self.gh_json("issue", "list", "--state", "open", "--limit", str(limit), "--json", "number,title,state")
        return [self._row(d) for d in data]

    def search(self, query: str, limit: int, raw: bool) -> list[Row]:
        data = self.gh_json("issue", "list", "--state", "all", "--search", query, "--limit", str(limit),
                            "--json", "number,title,state")
        return [self._row(d) for d in data]

    def create(self, title: str, body: str, parent: str | None, issue_type: str | None) -> str:
        url = self.gh("issue", "create", "--title", title, "--body-file", "-", stdin=body)
        number = url.rstrip("/").rsplit("/", 1)[-1]
        if parent:
            node_id = self.gh("api", f"repos/{{owner}}/{{repo}}/issues/{number}", "--jq", ".id")
            self.gh("api", "--method", "POST", f"repos/{{owner}}/{{repo}}/issues/{self.normalize(parent)}/sub_issues",
                    "-F", f"sub_issue_id={node_id}")
        return number

    def comment(self, issue: str, body: str) -> None:
        self.gh("issue", "comment", issue, "--body-file", "-", stdin=body)
    def update(self, issue: str, title: str | None, body: str | None) -> None:
        args = ["issue", "edit", issue]
        if title:
            args += ["--title", title]
        if body is None:
            self.gh(*args)
            return
        self.gh(*args, "--body-file", "-", stdin=body)

    def set_status(self, issue: str, status: str) -> str:
        if status not in STATUSES:
            raise AwError(f"status must be one of {', '.join(STATUSES)}")
        state = self.gh_json("issue", "view", issue, "--json", "state")["state"].lower()
        if status == "done":
            if state == "closed":
                return f"#{issue} already closed"
            self.gh("issue", "close", issue)
            return f"#{issue} closed"
        if state == "closed":
            self.gh("issue", "reopen", issue)
            return f"#{issue} reopened (GitHub issues have no {status} state; use a board hook for that)"
        return f"#{issue} open (GitHub issues have no {status} state; use a board hook for that)"
