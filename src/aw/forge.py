"""Pull/merge request operations per forge."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aw.config import AwError, json_pages
from aw.trackers import run as _run  # one runner: a missing gh or glab is an AwError, not a traceback

MERGE_FLAGS = {
    "github": {"merge": "--merge", "squash": "--squash", "rebase": "--rebase"},
    "gitlab": {"merge": None, "squash": "--squash", "rebase": "--rebase"},
}


def _proc(args: list[str], cwd: Path, quiet: bool = False) -> subprocess.CompletedProcess:
    """For calls whose exit code carries a result (gh pr checks); quiet discards the output (a watch)."""
    try:
        if quiet:
            return subprocess.run(args, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise AwError(f"{args[0]} not found") from None


def is_merged(forge: str, pr: str, cwd: Path) -> bool:
    if forge == "github":
        state = json.loads(_run(["gh", "pr", "view", pr, "--json", "state"], cwd))["state"]
        return state == "MERGED"
    if forge == "gitlab":
        state = json.loads(_run(["glab", "mr", "view", pr, "--output", "json"], cwd))["state"]
        return state == "merged"
    raise AwError(f"forge {forge!r} has no pull requests")


def merge(forge: str, pr: str, method: str, cwd: Path) -> None:
    """Merge without deleting the head branch; the worktree still has it checked out."""
    flag = MERGE_FLAGS[forge][method]
    if forge == "github":
        _run(["gh", "pr", "merge", pr, *([flag] if flag else [])], cwd)
    elif forge == "gitlab":
        _run(["glab", "mr", "merge", pr, "--yes", "--remove-source-branch=false", *([flag] if flag else [])], cwd)
    else:
        raise AwError(f"forge {forge!r} has no pull requests")


# --- merge request operations: aw mr ----------------------------------------------
# GitHub through gh; GitLab through glab, taken from its documentation and not tested against a live instance.


@dataclass
class MergeRequest:
    number: str
    url: str
    title: str = ""
    state: str = ""
    head: str = ""  # head commit; for a merged request, the one it was merged at


@dataclass
class Check:
    name: str
    bucket: str  # pass | fail | pending | skip


@dataclass
class Thread:
    path: str
    line: int | None
    comments: list[tuple[str, str]]  # (author, body)


@dataclass
class Summary:
    request: MergeRequest
    draft: bool
    checks: list[Check]
    review: str  # approved | changes requested | review required | none
    unresolved: int
    files: int
    additions: int | None
    deletions: int | None
    mergeable: str = ""
    closes: list[str] = field(default_factory=list)  # issue numbers the request closes when it merges


# $endCursor and pageInfo let `gh api graphql --paginate` walk every page of review threads.
THREADS = """query($owner:String!,$repo:String!,$number:Int!,$endCursor:String){repository(owner:$owner,name:$repo){
  pullRequest(number:$number){reviewThreads(first:100,after:$endCursor){pageInfo{hasNextPage endCursor}
  nodes{isResolved path line
  comments(first:20){nodes{author{login} body}}}} comments(last:30){nodes{author{login} body}}}}}"""
GITHUB_BUCKETS = {"pass": "pass", "fail": "fail", "cancel": "fail", "pending": "pending", "skipping": "skip"}
GITLAB_PIPELINE = {"success": "pass", "failed": "fail", "canceled": "fail", "skipped": "skip", "manual": "skip"}
CHECKS_APPEAR = 8  # polls, 15 s apart: how long configured CI may take to report the first check of a new request


def _unsupported(kind: str) -> AwError:
    return AwError(f"forge {kind!r} has no merge requests")


def _json(args: list[str], cwd: Path) -> Any:
    return json.loads(_run(args, cwd) or "null")


def _pages(args: list[str], cwd: Path) -> list[Any]:
    """Every item of a paginated `glab api --paginate` list: one JSON array per page."""
    return [item for page in json_pages(_run(args, cwd)) for item in page or []]


def find_open(kind: str, branch: str, cwd: Path) -> MergeRequest | None:
    """The open merge request whose source is branch, if there is one."""
    if kind == "github":
        rows = _json(["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number,url,title"], cwd)
        return MergeRequest(str(rows[0]["number"]), rows[0]["url"], rows[0]["title"], "open") if rows else None
    if kind == "gitlab":
        rows = _json(["glab", "mr", "list", "--source-branch", branch, "--output", "json"], cwd)
        return MergeRequest(str(rows[0]["iid"]), rows[0]["web_url"], rows[0]["title"], "open") if rows else None
    raise _unsupported(kind)


def merged(kind: str, branch: str, cwd: Path) -> list[MergeRequest]:
    """Merged requests from branch, oldest first: the parts a multi-merge session has shipped."""
    if kind == "github":
        rows = _json(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "merged",
                "--limit",
                "100",
                "--json",
                "number,url,title,headRefOid,mergedAt",
            ],
            cwd,
        )
        rows = sorted(rows, key=lambda r: r["mergedAt"])
        return [MergeRequest(str(r["number"]), r["url"], r["title"], "merged", r["headRefOid"]) for r in rows]
    if kind == "gitlab":
        rows = _json(["glab", "mr", "list", "--source-branch", branch, "--merged", "--output", "json"], cwd) or []
        rows = sorted(rows, key=lambda r: r.get("merged_at") or "")
        return [MergeRequest(str(r["iid"]), r["web_url"], r["title"], "merged", r.get("sha", "")) for r in rows]
    raise _unsupported(kind)


def head(kind: str, ref: str, cwd: Path) -> str:
    """The request's head commit (for a merged one, the commit it was merged at)."""
    if kind == "github":
        return _json(["gh", "pr", "view", ref, "--json", "headRefOid"], cwd)["headRefOid"]
    if kind == "gitlab":
        return _json(["glab", "mr", "view", ref, "--output", "json"], cwd)["sha"]
    raise _unsupported(kind)


def body(kind: str, ref: str, cwd: Path) -> str:
    """The request's description as it is now."""
    if kind == "github":
        return _json(["gh", "pr", "view", ref, "--json", "body"], cwd)["body"] or ""
    if kind == "gitlab":
        return _json(["glab", "mr", "view", ref, "--output", "json"], cwd).get("description") or ""
    raise _unsupported(kind)


def closes(kind: str, ref: str, cwd: Path) -> list[str]:
    """Issue numbers the request closes when it merges, as the forge parsed them from its description."""
    if kind == "github":
        refs = _json(["gh", "pr", "view", ref, "--json", "closingIssuesReferences"], cwd)["closingIssuesReferences"]
        return [str(i["number"]) for i in refs or []]
    if kind == "gitlab":  # from the API documentation, not tested against a live instance
        iid = ref if ref.isdigit() else str(_json(["glab", "mr", "view", ref, "--output", "json"], cwd)["iid"])
        issues = _json(["glab", "api", f"projects/:id/merge_requests/{iid}/closes_issues"], cwd) or []
        return [str(i["iid"]) for i in issues]
    raise _unsupported(kind)


def target(kind: str, ref: str, cwd: Path) -> str:
    """The branch the request merges into."""
    if kind == "github":
        return _json(["gh", "pr", "view", ref, "--json", "baseRefName"], cwd)["baseRefName"]
    if kind == "gitlab":
        return _json(["glab", "mr", "view", ref, "--output", "json"], cwd)["target_branch"]
    raise _unsupported(kind)


def retarget(kind: str, ref: str, branch: str, cwd: Path) -> None:
    if kind == "github":
        _run(["gh", "pr", "edit", ref, "--base", branch], cwd)
    elif kind == "gitlab":
        _run(["glab", "mr", "update", ref, "--target-branch", branch], cwd)
    else:
        raise _unsupported(kind)


def create(kind: str, branch: str, base: str, title: str, body: str, draft: bool, cwd: Path) -> MergeRequest:
    if kind == "github":
        args = ["gh", "pr", "create", "--head", branch, "--base", base, "--title", title, "--body-file", "-"]
        url = _run([*args, *(["--draft"] if draft else [])], cwd, body).splitlines()[-1]
    elif kind == "gitlab":
        out = _run(
            [
                "glab",
                "mr",
                "create",
                "--source-branch",
                branch,
                "--target-branch",
                base,
                "--title",
                title,
                "--description",
                body,
                "--yes",
                *(["--draft"] if draft else []),
            ],
            cwd,
        )
        url = next((w for w in out.split() if "/merge_requests/" in w), out.splitlines()[-1])
    else:
        raise _unsupported(kind)
    return MergeRequest(url.rstrip("/").rsplit("/", 1)[-1], url, title, "open")


def update(kind: str, ref: str, title: str | None, body: str | None, cwd: Path) -> None:
    if kind == "github":
        args = ["gh", "pr", "edit", ref, *(["--title", title] if title else [])]
        if body is None:
            _run(args, cwd)
            return
        _run([*args, "--body-file", "-"], cwd, body)
    elif kind == "gitlab":
        _run(
            [
                "glab",
                "mr",
                "update",
                ref,
                *(["--title", title] if title else []),
                *(["--description", body] if body is not None else []),
            ],
            cwd,
        )
    else:
        raise _unsupported(kind)


def ci_file(kind: str, checkout: Path) -> str | None:
    """The CI configuration in this checkout that reports checks on a request, or None when there is none."""
    if kind == "github":
        workflows = checkout / ".github/workflows"
        return ".github/workflows" if any(workflows.glob("*.yml")) or any(workflows.glob("*.yaml")) else None
    if kind == "gitlab":
        return ".gitlab-ci.yml" if (checkout / ".gitlab-ci.yml").is_file() else None
    return None


def checks(kind: str, ref: str, cwd: Path, watch: bool = False) -> list[Check]:
    """CI results; with watch, wait until nothing is pending. Progress output is discarded, only results return.

    With CI configured in the checkout, no checks right after a request opened means none reported yet: a watch
    waits for the first one (CHECKS_APPEAR polls) before it watches them.
    """
    results = _checks(kind, ref, cwd, watch)
    if watch and ci_file(kind, cwd):
        for _ in range(CHECKS_APPEAR):
            if results:
                break
            time.sleep(15)
            results = _checks(kind, ref, cwd, watch)
    return results


def _checks(kind: str, ref: str, cwd: Path, watch: bool) -> list[Check]:
    if kind == "github":
        if watch:
            _proc(["gh", "pr", "checks", ref, "--watch", "--interval", "15"], cwd, quiet=True)
        r = _proc(["gh", "pr", "checks", ref, "--json", "name,bucket"], cwd)
        if r.returncode not in (0, 1, 8):  # 1: a check failed, 8: pending; both still print the JSON
            raise AwError(f"gh pr checks: {r.stderr.strip()}")
        if not r.stdout.strip():
            if "no checks" in r.stderr:
                return []
            raise AwError(f"gh pr checks: {r.stderr.strip()}")
        return [Check(c["name"], GITHUB_BUCKETS.get(c["bucket"], "pending")) for c in json.loads(r.stdout)]
    if kind == "gitlab":
        while True:
            mr = _json(["glab", "mr", "view", ref, "--output", "json"], cwd)
            pipeline = mr.get("head_pipeline") or mr.get("pipeline")
            if not pipeline:
                return []
            bucket = GITLAB_PIPELINE.get(pipeline.get("status", ""), "pending")
            if bucket != "pending" or not watch:
                break
            time.sleep(15)
        jobs = _pages(["glab", "api", "--paginate", f"projects/:id/pipelines/{pipeline['id']}/jobs"], cwd)
        if not jobs:
            return [Check("pipeline", bucket)]
        return [Check(j["name"], GITLAB_PIPELINE.get(j["status"], "pending")) for j in jobs]
    raise _unsupported(kind)


def comments(kind: str, ref: str, cwd: Path) -> tuple[list[Thread], list[tuple[str, str]], int]:
    """Unresolved review threads, general comments, and how many threads are resolved."""
    if kind == "github":
        number = ref if ref.isdigit() else str(_json(["gh", "pr", "view", ref, "--json", "number"], cwd)["number"])
        pages = json_pages(
            _run(
                [
                    "gh",
                    "api",
                    "graphql",
                    "--paginate",
                    "-f",
                    f"query={THREADS}",
                    "-F",
                    "owner={owner}",
                    "-F",
                    "repo={repo}",
                    "-F",
                    f"number={number}",
                ],
                cwd,
            )
        )
        data = pages[0]["data"]["repository"]["pullRequest"]  # general comments: the same on every page
        threads = [t for p in pages for t in p["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]]
        open_threads = [
            Thread(
                t["path"],
                t.get("line"),
                [((c.get("author") or {}).get("login", "?"), c["body"]) for c in t["comments"]["nodes"]],
            )
            for t in threads
            if not t["isResolved"]
        ]
        general = [((c.get("author") or {}).get("login", "?"), c["body"]) for c in data["comments"]["nodes"]]
        return open_threads, general, len(threads) - len(open_threads)
    if kind == "gitlab":
        iid = ref if ref.isdigit() else str(_json(["glab", "mr", "view", ref, "--output", "json"], cwd)["iid"])
        discussions = _pages(["glab", "api", "--paginate", f"projects/:id/merge_requests/{iid}/discussions"], cwd)
        open_threads, general, resolved = [], [], 0
        for d in discussions:
            notes = [n for n in d.get("notes", []) if not n.get("system")]
            if not notes:
                continue
            if not notes[0].get("resolvable"):
                general += [((n.get("author") or {}).get("username", "?"), n["body"]) for n in notes]
            elif all(n.get("resolved") for n in notes if n.get("resolvable")):
                resolved += 1
            else:
                position = notes[0].get("position") or {}
                open_threads.append(
                    Thread(
                        position.get("new_path", ""),
                        position.get("new_line"),
                        [((n.get("author") or {}).get("username", "?"), n["body"]) for n in notes],
                    )
                )
        return open_threads, general, resolved
    raise _unsupported(kind)


def summary(kind: str, ref: str, cwd: Path) -> Summary:
    """Everything the merge gate shows, in as few calls as the forge allows."""
    if kind == "github":
        d = _json(
            [
                "gh",
                "pr",
                "view",
                ref,
                "--json",
                "number,url,title,state,isDraft,reviewDecision,changedFiles,additions,deletions,mergeable,"
                "closingIssuesReferences",
            ],
            cwd,
        )
        review = {
            "APPROVED": "approved",
            "CHANGES_REQUESTED": "changes requested",
            "REVIEW_REQUIRED": "review required",
        }.get(d.get("reviewDecision") or "", "none")
        threads, _, _ = comments(kind, str(d["number"]), cwd)
        return Summary(
            MergeRequest(str(d["number"]), d["url"], d["title"], d["state"].lower()),
            d["isDraft"],
            checks(kind, str(d["number"]), cwd),
            review,
            len(threads),
            d["changedFiles"],
            d["additions"],
            d["deletions"],
            (d.get("mergeable") or "").lower(),
            [str(i["number"]) for i in d.get("closingIssuesReferences") or []],
        )
    if kind == "gitlab":
        d = _json(["glab", "mr", "view", ref, "--output", "json"], cwd)
        iid = str(d["iid"])
        threads, _, _ = comments(kind, iid, cwd)
        status = d.get("detailed_merge_status") or ""
        review = "review required" if status == "not_approved" else "none"
        files = int(str(d.get("changes_count") or "0").rstrip("+") or 0)
        return Summary(
            MergeRequest(iid, d["web_url"], d["title"], d["state"]),
            bool(d.get("draft")),
            checks(kind, iid, cwd),
            review,
            len(threads),
            files,
            None,
            None,
            status.replace("_", " "),
            closes(kind, iid, cwd),
        )
    raise _unsupported(kind)
