"""GitLab issues via the glab CLI. Untested against a live instance."""

from __future__ import annotations

import json
import re
from typing import Any

from aw.config import AwError
from aw.trackers import STATUSES, Issue, Row, Tracker, gitlab_access, run


class GitLab(Tracker):
    name = "gitlab"
    id_pattern = re.compile(r"^\d+$")

    def ref(self, issue: str) -> str:
        return f"#{issue}"

    def pr_text(self, issue: str) -> str:
        return f"{self.cfg.get('pr_close_keyword')} #{issue}"

    def glab(self, *args: str) -> str:
        return run(["glab", *args], self.cfg.checkout)

    def glab_json(self, *args: str) -> Any:
        return json.loads(self.glab(*args) or "null")

    @staticmethod
    def _row(d: dict) -> Row:
        return Row(str(d["iid"]), d.get("title", ""), d.get("state", ""))

    def view(self, issue: str) -> Issue:
        d = self.glab_json("issue", "view", issue, "--output", "json")
        return Issue(
            id=str(d["iid"]),
            ref=f"#{d['iid']}",
            title=d["title"],
            status=d.get("state", ""),
            url=d.get("web_url", ""),
            labels=d.get("labels", []),
            body=d.get("description") or "",
            opened_by=gitlab_access(self.cfg.get("trusted_bots"), self.glab).comment(
                (d.get("author") or {}).get("username", ""), ""
            ),
        )

    def list_open(self, limit: int) -> list[Row]:
        return [self._row(d) for d in self.glab_json("issue", "list", "--per-page", str(limit), "--output", "json")]

    def search(self, query: str, limit: int, raw: bool) -> list[Row]:
        return [
            self._row(d)
            for d in self.glab_json(
                "issue", "list", "--all", "--search", query, "--per-page", str(limit), "--output", "json"
            )
        ]

    def comment(self, issue: str, body: str) -> None:
        self.glab("issue", "note", issue, "--message", body)

    def set_status(self, issue: str, status: str) -> str:
        if status not in STATUSES:
            raise AwError(f"status must be one of {', '.join(STATUSES)}")
        if status == "done":
            self.glab("issue", "close", issue)
            return f"#{issue} closed"
        self.glab("issue", "reopen", issue)
        return f"#{issue} open (GitLab issues have no {status} state; use labels or a hook)"
