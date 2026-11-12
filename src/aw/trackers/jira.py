"""Jira Cloud via REST API v3, standard library only.

Credentials come from the environment and are never printed:
  JIRA_USER_EMAIL, JIRA_API_TOKEN   basic auth
  JIRA_CLOUD_ID                     optional; routes through the scoped api.atlassian.com gateway
  JIRA_BASE_URL                     used when jira_base_url is not configured
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from typing import Any

from aw.config import AwError, Config
from aw.trackers import Comment, Issue, Row, Tracker, adf, status_name

CREDENTIALS = ("JIRA_USER_EMAIL", "JIRA_API_TOKEN")
TIMEOUT = 20


def _field_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        if value.get("type") == "doc":
            return adf.to_markdown(value)
        return str(value.get("value") or value.get("name") or value.get("displayName") or "")
    if isinstance(value, list):
        return ", ".join(filter(None, (_field_text(v) for v in value)))
    return str(value)


def _jql_str(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class Jira(Tracker):
    name = "jira"
    id_pattern = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")

    def __init__(self, cfg: Config) -> None:
        super().__init__(cfg)
        self._categories: dict[str, str | None] = {}  # status category per issue, filled by every read
        self._levels: dict[str, int] = {}  # issue type hierarchy level per issue

    def normalize(self, raw: str) -> str:
        return super().normalize(raw.upper())

    # --- transport ---

    def site_url(self) -> str:
        url = self.cfg.get("jira_base_url") or os.environ.get("JIRA_BASE_URL", "")
        if not url:
            raise AwError("jira_base_url is not set (aw init, or JIRA_BASE_URL)")
        if not url.startswith("https://"):  # every request carries the Basic-auth credentials
            raise AwError(f"jira_base_url must start with https://, got {url!r}")
        return url.rstrip("/")

    def api_base(self) -> str:
        cloud = os.environ.get("JIRA_CLOUD_ID")
        return f"https://api.atlassian.com/ex/jira/{cloud}" if cloud else self.site_url()

    def request(self, method: str, path: str, params: dict | None = None, body: Any = None) -> Any:
        missing = [v for v in CREDENTIALS if not os.environ.get(v)]
        if missing:
            raise AwError(f"missing environment variables: {', '.join(missing)}")
        token = base64.b64encode(f"{os.environ['JIRA_USER_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()).decode()
        url = self.api_base() + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(  # noqa: S310 - https URL built from jira_base_url
            url,
            method=method,
            headers={
                "Authorization": f"Basic {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            data=json.dumps(body).encode() if body is not None else None,
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 - the request above
                raw = resp.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise AwError(f"jira {method} {path}: HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            raise AwError(f"jira {method} {path}: {e.reason}") from None
        return json.loads(raw) if raw else None

    # --- helpers ---

    def _row(self, data: dict) -> Row:
        f = data.get("fields", {})
        status, kind = f.get("status") or {}, f.get("issuetype") or {}
        if category := (status.get("statusCategory") or {}).get("key"):
            self._categories[data["key"]] = category
        if (level := kind.get("hierarchyLevel")) is not None:
            self._levels[data["key"]] = level
        return Row(
            data["key"],
            f.get("summary", ""),
            status.get("name", ""),
            kind.get("name", ""),
            parent=(f.get("parent") or {}).get("key", ""),
        )

    def _search(self, jql: str, limit: int) -> list[Row]:
        data = self.request(
            "GET",
            "/rest/api/3/search/jql",
            {"jql": jql, "maxResults": limit, "fields": "summary,status,issuetype,parent"},
        )
        return [self._row(i) for i in data.get("issues", [])]

    def _project_clause(self) -> str:
        project = self.cfg.get("jira_project")
        return f"project = {_jql_str(project)}" if project else "assignee = currentUser()"

    def target_status(self, status: str) -> str:
        return status_name(self.cfg, status)

    # --- contract ---

    def view(self, issue: str) -> Issue:
        extra: dict[str, str] = self.cfg.get("jira_fields")
        fields = ["summary", "status", "issuetype", "labels", "parent", "description", "comment", *extra.values()]
        data = self.request("GET", f"/rest/api/3/issue/{issue}", {"fields": ",".join(fields)})
        f = data.get("fields", {})
        parent = f.get("parent")
        comments = (f.get("comment") or {}).get("comments", [])
        return Issue(
            id=data["key"],
            ref=data["key"],
            title=f.get("summary", ""),
            status=(f.get("status") or {}).get("name", ""),
            type=(f.get("issuetype") or {}).get("name", ""),
            url=f"{self.site_url()}/browse/{data['key']}",
            labels=f.get("labels", []),
            parent=replace(self._row(parent), link="native") if parent else None,
            body=adf.to_markdown(f.get("description")),
            sections={name: _field_text(f.get(fid)) for name, fid in extra.items()},
            children=self.children(issue),
            comments=[  # a Jira site admits only its own users: none of them is outside
                Comment((c.get("author") or {}).get("displayName", "unknown"), adf.to_markdown(c.get("body")))
                for c in comments
            ],
        )

    def parent(self, issue: str) -> Row | None:
        parent = self.request("GET", f"/rest/api/3/issue/{issue}", {"fields": "parent"})["fields"].get("parent")
        return replace(self._row(parent), link="native") if parent else None

    def children(self, issue: str) -> list[Row]:
        """Every child, page by page: the parent rollup decides on this list."""
        jql = f"parent = {issue} ORDER BY created ASC"
        rows, token = [], None
        while True:
            params = {"jql": jql, "maxResults": 100, "fields": "summary,status,issuetype,parent"}
            data = self.request("GET", "/rest/api/3/search/jql", params | ({"nextPageToken": token} if token else {}))
            rows += [replace(self._row(i), link="native") for i in data.get("issues", [])]
            token = data.get("nextPageToken")
            if data.get("isLast", True) or not token:
                return rows

    def set_parent(self, issue: str, parent: str | None) -> str:
        target = self.normalize(parent) if parent else None
        current = self.parent(issue)
        if (current.id if current else None) == target:
            return f"{issue} already under {target}" if target else f"{issue} has no parent"
        try:
            self.request(
                "PUT", f"/rest/api/3/issue/{issue}", body={"fields": {"parent": {"key": target} if target else None}}
            )
        except AwError as e:
            # Hierarchy rules (sub-task under epic, team- vs company-managed) only make sense with the types.
            pair = " under ".join(f"{key} ({self._type(key)})" for key in filter(None, (issue, target)))
            raise AwError(f"jira refused the parent change for {pair}: {e}") from None
        return f"{issue} parent {current.id if current else 'none'} -> {target or 'none'}"

    def _type(self, issue: str) -> str:
        try:
            data = self.request("GET", f"/rest/api/3/issue/{issue}", {"fields": "issuetype"})
        except AwError:
            return "type unknown"
        return (data["fields"].get("issuetype") or {}).get("name", "type unknown")

    def dupes(self, parent: str | None, terms: list[str], limit: int, tree_only: bool = False) -> list[Row]:
        """One text search; hits under parent (two levels) first, the rest of the project after."""
        if parent is None and tree_only:
            raise AwError("--tree-only needs a parent")
        children = [row.id for row in self.children(parent)] if parent else []
        text = " OR ".join(f"text ~ {_jql_str(term)}" for term in terms)
        where = f"parent in ({', '.join([parent, *children])})" if tree_only and parent else self._project_clause()
        rows = self._search(f"{where} AND ({text}) ORDER BY updated DESC", limit)
        tree = {parent, *children} if parent else set()
        for row in rows:  # children and grandchildren hang under the parent or one of its children
            row.scope = "tree" if row.id in tree or row.parent in tree else "elsewhere"
        return sorted(rows, key=lambda row: row.scope != "tree")

    def list_open(self, limit: int) -> list[Row]:
        return self._search(f"{self._project_clause()} AND statusCategory != Done ORDER BY updated DESC", limit)

    def search(self, query: str, limit: int, raw: bool) -> list[Row]:
        jql = query if raw else f"{self._project_clause()} AND text ~ {_jql_str(query)} ORDER BY updated DESC"
        return self._search(jql, limit)

    def create(
        self,
        title: str,
        body: str,
        parent: str | None,
        issue_type: str | None,
        labels: list[str] | None = None,
        status: str | None = None,
        fields: dict[str, str] | None = None,
    ) -> str:
        if fields:
            raise AwError("--field: Jira custom fields are not supported yet")
        project = self.cfg.get("jira_project")
        if not project:
            raise AwError("jira_project is not set")
        fields: dict[str, Any] = {
            "project": {"key": project},
            "issuetype": {"name": issue_type or "Task"},
            "summary": title,
            "description": adf.from_markdown(body),
        }
        if parent:
            fields["parent"] = {"key": self.normalize(parent)}
        if labels:
            fields["labels"] = labels
        key = self.request("POST", "/rest/api/3/issue", body={"fields": fields})["key"]
        if status and status != "none":  # Jira has no way to create in a given status: transition right after
            try:
                self.set_status(key, status)
            except AwError as e:
                raise AwError(
                    f"created {key}, but not moved to {status}: {e}. "
                    f"Run `aw issue set-status {key} {status}`; do not create it again"
                ) from None
        return key

    def comment(self, issue: str, body: str) -> None:
        self.request("POST", f"/rest/api/3/issue/{issue}/comment", body={"body": adf.from_markdown(body)})

    def update(self, issue: str, title: str | None, body: str | None) -> None:
        fields: dict[str, Any] = {}
        if title:
            fields["summary"] = title
        if body is not None:
            fields["description"] = adf.from_markdown(body)
        self.request("PUT", f"/rest/api/3/issue/{issue}", body={"fields": fields})

    def set_status(self, issue: str, status: str) -> str:
        target = self.target_status(status)
        current = self.request("GET", f"/rest/api/3/issue/{issue}", {"fields": "status"})
        if current["fields"]["status"]["name"].casefold() == target.casefold():
            return f"{issue} already {target}"
        transitions = self.request("GET", f"/rest/api/3/issue/{issue}/transitions").get("transitions", [])
        for t in transitions:
            if target.casefold() in ((t.get("to") or {}).get("name", "").casefold(), t.get("name", "").casefold()):
                self.request("POST", f"/rest/api/3/issue/{issue}/transitions", body={"transition": {"id": t["id"]}})
                return f"{issue} -> {target}"
        options = ", ".join(sorted({(t.get("to") or {}).get("name", "") for t in transitions})) or "none"
        raise AwError(f"{issue}: no transition to {target!r} (available: {options}); set status_map.{status}")

    def has_states(self) -> bool:
        return True

    def current_status(self, issue: str) -> str | None:
        status = self.request("GET", f"/rest/api/3/issue/{issue}", {"fields": "status"})["fields"].get("status") or {}
        self._categories[issue] = (status.get("statusCategory") or {}).get("key")
        return status.get("name")

    def is_epic(self, row: Row) -> bool:
        """One of epic_types, or a type above story level (hierarchyLevel 1 and up), whatever its name."""
        return super().is_epic(row) or self._levels.get(row.id, 0) >= 1

    def closed(self, row: Row) -> bool:
        return self.status_category(row.id) == "done"

    def status_category(self, issue: str) -> str | None:
        if issue not in self._categories:
            self.current_status(issue)
        return self._categories.get(issue)
