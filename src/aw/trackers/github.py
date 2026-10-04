"""GitHub Issues via the gh CLI. Parent links are native sub-issues, read and written through GraphQL."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from aw.config import AwError
from aw.trackers import STATUSES, Issue, Row, Tracker, run

PART_OF = re.compile(r"\bPart of #(\d+)", re.IGNORECASE)
TASK_REF = re.compile(r"^\s*[-*] \[[ xX]\] .*?#(\d+)", re.MULTILINE)

META = """query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo){
  issue(number:$number){body issueType{name} parent{number title state}}}}"""
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

    def graphql(self, query: str, stdin: str | None = None, raw: dict[str, str] | None = None,
                **typed: str | int | bool | list[str]) -> dict:
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
        return Row(str(d["number"]), d.get("title", ""), d.get("state", "").lower(), link=link)

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
            id=str(d["number"]), ref=f"#{d['number']}", title=d["title"], status=d["state"].lower(),
            url=d.get("url", ""), type=(meta.get("issueType") or {}).get("name", ""),
            labels=[lb["name"] for lb in d.get("labels", [])], parent=self._parent(meta), body=body,
            children=self.children(issue, body),
            comments=[((c.get("author") or {}).get("login", "unknown"), c.get("body", ""))
                      for c in d.get("comments", [])],
        )

    def children(self, issue: str, body: str | None = None) -> list[Row]:
        try:
            subs = self.gh_json("api", f"repos/{{owner}}/{{repo}}/issues/{issue}/sub_issues") or []
        except AwError:
            subs = []
        rows = [self._row(s, "native") for s in subs]
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
        data = self.gh_json("issue", "list", "--state", "all", "--search", query, "--limit", str(limit),
                            "--json", "number,title,state")
        return [self._row(d) for d in data]

    def create(self, title: str, body: str, parent: str | None, issue_type: str | None,
               labels: list[str] | None = None) -> str:
        """One createIssue mutation, so the issue never exists without its parent link or labels."""
        target = self.normalize(parent) if parent else None
        repo = self.graphql(CREATE_CONTEXT, parent=int(target or 0), withParent=bool(target))["repository"]
        ids = {"repoId": repo["id"]}
        if target:
            ids["parentId"] = repo["parent"]["id"]
        if issue_type:
            types = (repo.get("issueTypes") or {}).get("nodes") or []
            if not types:
                why = ("issue types need an organization-owned repository" if repo["owner"]["__typename"] == "User"
                       else "this repository has no issue types")
                print(f"warning: --type {issue_type!r} ignored: {why}", file=sys.stderr)
            else:
                match = [t["id"] for t in types if t["name"].casefold() == issue_type.casefold()]
                if not match:
                    raise AwError(f"unknown issue type {issue_type!r} (available: {', '.join(t['name'] for t in types)})")
                ids["typeId"] = match[0]
        label_ids: list[str] = []
        if labels:
            known = {node["name"].casefold(): node["id"] for node in (repo.get("labels") or {}).get("nodes") or []}
            unknown = [name for name in labels if name.casefold() not in known]
            if unknown:
                raise AwError(f"unknown label(s): {', '.join(unknown)}; create them first (gh label create)")
            label_ids = [known[name.casefold()] for name in labels]
        data = self.graphql(CREATE, stdin=body, raw={"title": title}, body="@-", **ids,
                            **({"labelIds": label_ids} if label_ids else {}))
        return str(data["createIssue"]["issue"]["number"])

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
            return f"#{issue} reopened"
        return f"#{issue} open"
