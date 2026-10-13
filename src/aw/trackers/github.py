"""GitHub Issues via the gh CLI. Parent links are native sub-issues, read and written through GraphQL."""

from __future__ import annotations

import json
import re
import sys
from functools import cached_property
from typing import Any

from aw.config import AwError, json_pages
from aw.trackers import STATUSES, Issue, Row, Tracker, run, status_name

PART_OF = re.compile(r"\bPart of #(\d+)", re.IGNORECASE)
TASK_REF = re.compile(r"^\s*[-*] \[[ xX]\] .*?#(\d+)", re.MULTILINE)

META = """query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo){
  issue(number:$number){body issueType{name} parent{number title state issueType{name}}}}}"""
SEARCH = """query($q:String!,$first:Int!){search(query:$q,type:ISSUE,first:$first){
  nodes{... on Issue{number title state parent{number}}}}}"""
PART_OF_SEARCH = """query($q:String!){search(query:$q,type:ISSUE,first:100){
  nodes{... on Issue{number title state body parent{number}}}}}"""
CREATE_CONTEXT = """query($owner:String!,$repo:String!,$parent:Int!,$withParent:Boolean!){
  repository(owner:$owner,name:$repo){id owner{__typename} issueTypes(first:50){nodes{id name}}
  labels(first:100){nodes{id name}}
  parent: issue(number:$parent) @include(if:$withParent){id}}}"""
CREATE = """mutation($repoId:ID!,$title:String!,$body:String!,$parentId:ID,$typeId:ID,$labelIds:[ID!]){
  createIssue(input:{repositoryId:$repoId,title:$title,body:$body,parentIssueId:$parentId,issueTypeId:$typeId,
  labelIds:$labelIds}){issue{number}}}"""
LINK_CONTEXT = """query($owner:String!,$repo:String!,$number:Int!,$parent:Int!,$withParent:Boolean!){
  repository(owner:$owner,name:$repo){issue(number:$number){id parent{id number}}
  target: issue(number:$parent) @include(if:$withParent){id}}}"""
ADD_SUB = """mutation($parentId:ID!,$childId:ID!){
  addSubIssue(input:{issueId:$parentId,subIssueId:$childId,replaceParent:true}){issue{number}}}"""
BOARD = """query($login:String!,$number:Int!,$field:String!){repositoryOwner(login:$login){
  ... on ProjectV2Owner{projectV2(number:$number){id title
  field(name:$field){... on ProjectV2SingleSelectField{id name options{id name}}}
  workflows(first:20){nodes{name enabled}}}}}}"""
CARD = """query($owner:String!,$repo:String!,$number:Int!,$field:String!){repository(owner:$owner,name:$repo){
  issue(number:$number){id projectItems(first:50){nodes{id project{id}
  fieldValueByName(name:$field){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}"""
ADD_CARD = """mutation($projectId:ID!,$contentId:ID!){
  addProjectV2ItemById(input:{projectId:$projectId,contentId:$contentId}){item{id}}}"""
SET_CARD = """mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!,$optionId:String!){
  updateProjectV2ItemFieldValue(input:{projectId:$projectId,itemId:$itemId,fieldId:$fieldId,
  value:{singleSelectOptionId:$optionId}}){projectV2Item{id}}}"""
REMOVE_SUB = """mutation($parentId:ID!,$childId:ID!){
  removeSubIssue(input:{issueId:$parentId,subIssueId:$childId}){issue{number}}}"""


class GitHub(Tracker):
    name = "github"
    id_pattern = re.compile(r"^\d+$")

    def ref(self, issue: str) -> str:
        return f"#{issue}"

    def pr_text(self, issue: str) -> str:
        return f"{self.cfg.get('pr_close_keyword')} #{issue}"

    def gh(self, *args: str, stdin: str | None = None) -> str:
        return run(["gh", *args], self.cfg.checkout, stdin)

    def gh_json(self, *args: str, stdin: str | None = None) -> Any:
        return json.loads(self.gh(*args, stdin=stdin) or "null")

    def graphql(
        self,
        query: str,
        stdin: str | None = None,
        raw: dict[str, str] | None = None,
        **typed: str | int | bool | list[str],
    ) -> dict:
        """GraphQL request. `typed` goes through -F (numbers, booleans, ids, `{owner}` placeholders, `@-` for stdin,
        lists as `key[]=` per item); `raw` through -f, for user text that -F would misread (a title like `42`)."""
        args = ["api", "graphql", "-f", f"query={query}", "-F", "owner={owner}", "-F", "repo={repo}"]
        for key, value in typed.items():
            if isinstance(value, list):
                args += [arg for item in value for arg in ("-F", f"{key}[]={item}")]
            else:
                args += ["-F", f"{key}={str(value).lower() if isinstance(value, bool) else value}"]
        for key, value in (raw or {}).items():
            args += ["-f", f"{key}={value}"]
        return (self.gh_json(*args, stdin=stdin) or {}).get("data") or {}

    @staticmethod
    def _row(d: dict, link: str = "") -> Row:
        parent = str(d["parent"]["number"]) if d.get("parent") else ""
        return Row(
            str(d["number"]),
            d.get("title", ""),
            d.get("state", "").lower(),
            (d.get("issueType") or {}).get("name", ""),
            link=link,
            parent=parent,
        )

    def _meta(self, issue: str) -> dict:
        return self.graphql(META, number=int(issue))["repository"]["issue"]

    def _parent(self, meta: dict) -> Row | None:
        """Native parent; a `Part of #N` line in the body only when there is none."""
        if meta.get("parent"):
            return self._row(meta["parent"], "native")
        if m := PART_OF.search(meta.get("body") or ""):
            return Row(m.group(1), link="text")
        return None

    def parent(self, issue: str) -> Row | None:
        return self._parent(self._meta(issue))

    def view(self, issue: str) -> Issue:
        d = self.gh_json("issue", "view", issue, "--json", "number,title,body,state,url,labels,comments")
        body = d.get("body") or ""
        meta = self._meta(issue)
        return Issue(
            id=str(d["number"]),
            ref=f"#{d['number']}",
            title=d["title"],
            status=d["state"].lower(),
            url=d.get("url", ""),
            type=(meta.get("issueType") or {}).get("name", ""),
            labels=[lb["name"] for lb in d.get("labels", [])],
            parent=self._parent(meta),
            body=body,
            children=self.children(issue, body),
            comments=[
                ((c.get("author") or {}).get("login", "unknown"), c.get("body", "")) for c in d.get("comments", [])
            ],
        )

    def native_children(self, issue: str) -> list[Row]:
        """Sub-issues only, from every page; no lookups of task-list refs that would be dropped anyway.

        A failed request raises: decisions such as the parent rollup must never read it as "no children". HTTP 404
        is the one complete empty answer: the server has no sub-issues for this issue.
        """
        try:
            text = self.gh("api", "--paginate", f"repos/{{owner}}/{{repo}}/issues/{issue}/sub_issues")
        except AwError as e:
            if "HTTP 404" in str(e):
                return []
            raise
        return [self._row(s, "native") for page in json_pages(text) for s in page or []]

    def children(self, issue: str, body: str | None = None) -> list[Row]:
        rows = self.native_children(issue)
        if body is None:
            body = self.gh_json("issue", "view", issue, "--json", "body").get("body") or ""
        known = {r.id for r in rows}
        for n in dict.fromkeys(TASK_REF.findall(body)):
            if n not in known:
                try:
                    rows.append(self._row(self.gh_json("issue", "view", n, "--json", "number,title,state"), "text"))
                except AwError:
                    rows.append(Row(n, link="text"))
        return rows

    def text_children(self, issue: str) -> list[Row]:
        """Task-list refs in this issue's body, plus issues whose `Part of #N` line points here, minus native links."""
        rows = super().text_children(issue)
        seen = {r.id for r in rows}
        query = f'repo:{{owner}}/{{repo}} is:issue "Part of #{issue}" in:body'
        for node in self.graphql(PART_OF_SEARCH, q=query)["search"]["nodes"]:
            m = PART_OF.search(node.get("body") or "")
            native = (node.get("parent") or {}).get("number")
            if m and m.group(1) == issue and str(native) != issue and str(node["number"]) not in seen:
                rows.append(self._row(node, "text"))
        return rows

    def list_open(self, limit: int) -> list[Row]:
        data = self.gh_json("issue", "list", "--state", "open", "--limit", str(limit), "--json", "number,title,state")
        return [self._row(d) for d in data]

    def search(self, query: str, limit: int, raw: bool) -> list[Row]:
        """Issues in any state, with their native parent, through GitHub search syntax."""
        data = self.graphql(SEARCH, q=f"repo:{{owner}}/{{repo}} is:issue {query}", first=min(limit, 100))
        return [self._row(node) for node in data["search"]["nodes"] if node]

    def create(
        self,
        title: str,
        body: str,
        parent: str | None,
        issue_type: str | None,
        labels: list[str] | None = None,
        status: str | None = None,
    ) -> str:
        """One createIssue mutation, so the issue never exists without its parent link or labels.

        With github_project, the new issue then goes on the board in the column for status (default backlog;
        "none": on the board without a column, e.g. an epic). The column is resolved first, so a board that
        cannot take it fails before anything is created. Without a board, status other than none needs one.
        """
        status = status or "backlog"
        if self.has_states() and status != "none":
            self.option(status)
        elif not self.has_states() and status not in ("backlog", "none"):
            raise AwError(f"--status {status} needs a board (github_project); a new GitHub issue is just open")
        target = self.normalize(parent) if parent else None
        repo = self.graphql(CREATE_CONTEXT, parent=int(target or 0), withParent=bool(target))["repository"]
        ids = {"repoId": repo["id"]}
        if target:
            ids["parentId"] = repo["parent"]["id"]
        if issue_type:
            types = (repo.get("issueTypes") or {}).get("nodes") or []
            if not types:
                why = (
                    "issue types need an organization-owned repository"
                    if repo["owner"]["__typename"] == "User"
                    else "this repository has no issue types"
                )
                print(f"warning: --type {issue_type!r} ignored: {why}", file=sys.stderr)
            else:
                match = [t["id"] for t in types if t["name"].casefold() == issue_type.casefold()]
                if not match:
                    raise AwError(
                        f"unknown issue type {issue_type!r} (available: {', '.join(t['name'] for t in types)})"
                    )
                ids["typeId"] = match[0]
        label_ids: list[str] = []
        if labels:
            known = {node["name"].casefold(): node["id"] for node in (repo.get("labels") or {}).get("nodes") or []}
            unknown = [name for name in labels if name.casefold() not in known]
            if unknown:
                raise AwError(f"unknown label(s): {', '.join(unknown)}; create them first (gh label create)")
            label_ids = [known[name.casefold()] for name in labels]
        data = self.graphql(
            CREATE, stdin=body, raw={"title": title}, body="@-", **ids, **({"labelIds": label_ids} if label_ids else {})
        )
        number = str(data["createIssue"]["issue"]["number"])
        if self.has_states():
            try:
                if status == "none":
                    self._add_card(number)
                else:
                    self.set_status(number, status)
            except AwError as e:
                repair = f"aw issue set-status {number} {'backlog' if status == 'none' else status}"
                raise AwError(
                    f"created #{number}, but it is not on the board: {e}. Run `{repair}`; do not create it again"
                ) from None
        return number

    def set_parent(self, issue: str, parent: str | None) -> str:
        target = self.normalize(parent) if parent else None
        repo = self.graphql(LINK_CONTEXT, number=int(issue), parent=int(target or 0), withParent=bool(target))
        child = repo["repository"]["issue"]
        current = child.get("parent")
        was = f"#{current['number']}" if current else "none"
        if target is None:
            if not current:
                return f"#{issue} has no parent"
            self.graphql(REMOVE_SUB, parentId=current["id"], childId=child["id"])
            return f"#{issue} parent {was} -> none"
        if current and str(current["number"]) == target:
            return f"#{issue} already under #{target}"
        self.graphql(ADD_SUB, parentId=repo["repository"]["target"]["id"], childId=child["id"])
        return f"#{issue} parent {was} -> #{target}"

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

    # --- board: a GitHub Projects single-select field as the issue's workflow state ---

    def has_states(self) -> bool:
        return bool(self.cfg.get("github_project"))

    @cached_property
    def board(self) -> dict:
        """The github_project board: id, title, status field with its options, workflows."""
        spec, field = self.cfg.get("github_project"), self.cfg.get("status_field")
        owner, _, number = spec.partition("/")
        if not owner or not number.isdigit():
            raise AwError(f"github_project must be owner/number, got {spec!r}")
        try:
            data = self.graphql(BOARD, raw={"login": owner, "field": field}, number=int(number))
        except AwError as e:
            raise AwError(
                f"github_project {spec}: {e} (token needs the project scope: gh auth refresh -s project)"
            ) from None
        project = (data.get("repositoryOwner") or {}).get("projectV2")
        if not project:
            raise AwError(f"github_project {spec} not found")
        if not (project.get("field") or {}).get("options"):
            raise AwError(f"github_project {spec} has no single-select field {field!r} (status_field)")
        return project

    def option(self, status: str) -> dict:
        """The board column for a canonical status: status_map name, matched case-insensitively."""
        name = status_name(self.cfg, status)
        options = self.board["field"]["options"]
        match = next((o for o in options if o["name"].casefold() == name.casefold()), None)
        if match is None:
            available = ", ".join(o["name"] for o in options)
            raise AwError(f"board has no column {name!r} (columns: {available}); set status_map.{status}")
        return match

    def _card(self, issue: str) -> tuple[str, dict | None]:
        """Issue node id, and its item on the board if it is there."""
        node = self.graphql(CARD, number=int(issue), raw={"field": self.cfg.get("status_field")})["repository"]["issue"]
        item = next((i for i in node["projectItems"]["nodes"] if i["project"]["id"] == self.board["id"]), None)
        return node["id"], item

    def current_status(self, issue: str) -> str | None:
        if not self.has_states():
            return None
        _, item = self._card(issue)
        return ((item or {}).get("fieldValueByName") or {}).get("name")

    def is_epic(self, row: Row) -> bool:
        """One of epic_types, or on the board without a column: how `aw issue create --status none` files an epic."""
        if super().is_epic(row):
            return True
        if not self.has_states():
            return False
        _, item = self._card(row.id)
        return item is not None and not (item.get("fieldValueByName") or {}).get("name")

    def _add_card(self, issue: str) -> dict:
        node_id, item = self._card(issue)
        if item is None:  # addProjectV2ItemById is idempotent, but only an absent card needs it
            item = self.graphql(ADD_CARD, projectId=self.board["id"], contentId=node_id)["addProjectV2ItemById"]["item"]
        return item

    def _move_card(self, issue: str, option: dict) -> str:
        node_id, item = self._card(issue)
        if item and ((item.get("fieldValueByName") or {}).get("name") or "").casefold() == option["name"].casefold():
            return f"board already {option['name']}"
        if item is None:  # addProjectV2ItemById is idempotent, but only an absent card needs it
            item = self.graphql(ADD_CARD, projectId=self.board["id"], contentId=node_id)["addProjectV2ItemById"]["item"]
        self.graphql(
            SET_CARD,
            projectId=self.board["id"],
            itemId=item["id"],
            fieldId=self.board["field"]["id"],
            raw={"optionId": option["id"]},
        )
        return f"board {option['name']}"

    def set_status(self, issue: str, status: str) -> str:
        if status not in STATUSES:
            raise AwError(f"status must be one of {', '.join(STATUSES)}")
        option = self.option(status) if self.has_states() else None  # an unknown column fails before any change
        state = self.gh_json("issue", "view", issue, "--json", "state")["state"].lower()
        if status == "done":
            message = f"#{issue} already closed" if state == "closed" else f"#{issue} closed"
            if state != "closed":
                self.gh("issue", "close", issue)
        elif state == "closed":
            self.gh("issue", "reopen", issue)
            message = f"#{issue} reopened"
        else:
            message = f"#{issue} open"
        return f"{message} · {self._move_card(issue, option)}" if option else message
