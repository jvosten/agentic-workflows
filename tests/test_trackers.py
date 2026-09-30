import io
import json
import urllib.error
import urllib.request

import pytest

from aw import cli, finish, session, start_task, trackers
from aw.config import AwError, git, load
from aw.trackers import adf
from aw.trackers.github import GitHub
from aw.trackers.jira import Jira

# --- ADF ----------------------------------------------------------------------

ADF_DOC = {"type": "doc", "version": 1, "content": [
    {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Goal"}]},
    {"type": "paragraph", "content": [
        {"type": "text", "text": "Use "},
        {"type": "text", "text": "retries", "marks": [{"type": "strong"}]},
        {"type": "text", "text": " per "},
        {"type": "text", "text": "docs", "marks": [{"type": "link", "attrs": {"href": "https://x.test"}}]},
        {"type": "text", "text": ", ask "},
        {"type": "mention", "attrs": {"text": "@dev"}},
    ]},
    {"type": "bulletList", "content": [
        {"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "one"}]},
            {"type": "bulletList", "content": [{"type": "listItem", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "nested"}]}]}]},
        ]},
        {"type": "listItem", "content": [{"type": "paragraph", "content": [
            {"type": "text", "text": "cfg", "marks": [{"type": "code"}]}]}]},
    ]},
    {"type": "codeBlock", "attrs": {"language": "sh"}, "content": [{"type": "text", "text": "make test"}]},
    {"type": "table", "content": [
        {"type": "tableRow", "content": [
            {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "a"}]}]},
            {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "b"}]}]}]},
        {"type": "tableRow", "content": [
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "1"}]}]},
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "2"}]}]}]},
    ]},
]}

MARKDOWN = """## Goal

Use **retries** per [docs](https://x.test), ask @dev

- one
  - nested
- `cfg`

```sh
make test
```

| a | b |
|---|---|
| 1 | 2 |
"""


def test_adf_to_markdown():
    assert adf.to_markdown(ADF_DOC) == MARKDOWN


def test_markdown_roundtrip():
    md = MARKDOWN.replace(", ask @dev", "")
    assert adf.to_markdown(adf.from_markdown(md)) == md


def test_markdown_inline_marks():
    nodes = adf.inline("a **b _c_** `d` ~~e~~")
    assert [(n["text"], [m["type"] for m in n.get("marks", [])]) for n in nodes] == [
        ("a ", []), ("b ", ["strong"]), ("c", ["strong", "em"]), (" ", []), ("d", ["code"]), (" ", []),
        ("e", ["strike"]),
    ]


def test_ordered_list_and_quote():
    doc = adf.from_markdown("1. first\n2. second\n\n> note\n")
    assert [n["type"] for n in doc["content"]] == ["orderedList", "blockquote"]


# --- Jira ---------------------------------------------------------------------

def jira_cfg(repo, extra=""):
    (repo / ".agents").mkdir(exist_ok=True)
    (repo / ".agents/aw.toml").write_text(
        'tracker = "jira"\njira_base_url = "https://example.atlassian.net"\njira_project = "PROJ"\n'
        'jira_fields = { acceptance_criteria = "customfield_1" }\n' + extra)
    return load()


class FakeJira:
    """Records requests and serves canned responses keyed by (method, path)."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, method, path, params=None, body=None):
        self.calls.append((method, path, params, body))
        return self.responses.get((method, path), {})


ISSUE = {"key": "PROJ-12", "fields": {
    "summary": "Add retries", "status": {"name": "To Do"}, "issuetype": {"name": "Story"},
    "labels": ["backend"], "parent": {"key": "PROJ-1", "fields": {"summary": "Epic one"}},
    "description": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Body"}]}]},
    "customfield_1": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "AC"}]}]},
    "comment": {"comments": [{"author": {"displayName": "Dev"}, "body": {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "LGTM"}]}]}}]},
}}
CHILDREN = {"issues": [{"key": "PROJ-13", "fields": {
    "summary": "Subtask", "status": {"name": "Done"}, "issuetype": {"name": "Sub-task"}}}]}


def test_jira_view_renders_everything(repo, monkeypatch):
    fake = FakeJira({("GET", "/rest/api/3/issue/PROJ-12"): ISSUE, ("GET", "/rest/api/3/search/jql"): CHILDREN})
    tracker = trackers.get(jira_cfg(repo))
    monkeypatch.setattr(tracker, "request", fake)
    text = trackers.render(tracker.view(tracker.normalize("proj-12")))
    assert text.startswith("# PROJ-12: Add retries\n\nstatus: To Do · type: Story · parent: PROJ-1 (Epic one)")
    assert "https://example.atlassian.net/browse/PROJ-12" in text
    assert "## Acceptance criteria\n\nAC" in text
    assert "- [Done] PROJ-13 (Sub-task) Subtask" in text
    assert "### Dev\n\nLGTM" in text
    assert "customfield_1" in fake.calls[0][2]["fields"]
    assert fake.calls[1][2]["jql"] == "parent = PROJ-12 ORDER BY created ASC"


def test_jira_queries(repo, monkeypatch):
    fake = FakeJira({})
    tracker = trackers.get(jira_cfg(repo))
    monkeypatch.setattr(tracker, "request", fake)
    tracker.list_open(5)
    tracker.search('say "hi"', 5, raw=False)
    tracker.search("labels = x", 5, raw=True)
    jqls = [c[2]["jql"] for c in fake.calls]
    assert jqls == [
        'project = "PROJ" AND statusCategory != Done ORDER BY updated DESC',
        'project = "PROJ" AND text ~ "say \\"hi\\"" ORDER BY updated DESC',
        "labels = x",
    ]


def test_jira_create_and_comment(repo, monkeypatch):
    fake = FakeJira({("POST", "/rest/api/3/issue"): {"key": "PROJ-20"}})
    tracker = trackers.get(jira_cfg(repo))
    monkeypatch.setattr(tracker, "request", fake)
    assert tracker.create("Title", "## H\n\ntext", "proj-1", "Sub-task") == "PROJ-20"
    fields = fake.calls[0][3]["fields"]
    assert fields["parent"] == {"key": "PROJ-1"} and fields["issuetype"] == {"name": "Sub-task"}
    assert fields["description"]["content"][0]["type"] == "heading"
    tracker.comment("PROJ-20", "hello")
    assert fake.calls[1][:2] == ("POST", "/rest/api/3/issue/PROJ-20/comment")


def test_jira_set_status(repo, monkeypatch):
    tracker = trackers.get(jira_cfg(repo, 'status_map = { in_progress = "Doing" }\n'))
    transitions = {"transitions": [
        {"id": "11", "name": "Start", "to": {"name": "Doing"}},
        {"id": "31", "name": "Finish", "to": {"name": "Done"}}]}
    fake = FakeJira({("GET", "/rest/api/3/issue/PROJ-12"): {"fields": {"status": {"name": "To Do"}}},
                     ("GET", "/rest/api/3/issue/PROJ-12/transitions"): transitions})
    monkeypatch.setattr(tracker, "request", fake)
    assert tracker.set_status("PROJ-12", "in_progress") == "PROJ-12 -> Doing"
    assert fake.calls[-1] == ("POST", "/rest/api/3/issue/PROJ-12/transitions", None, {"transition": {"id": "11"}})
    with pytest.raises(AwError, match="available: Doing, Done"):
        tracker.set_status("PROJ-12", "in_review")
    fake.responses[("GET", "/rest/api/3/issue/PROJ-12")] = {"fields": {"status": {"name": "done"}}}
    assert tracker.set_status("PROJ-12", "done") == "PROJ-12 already Done"


def test_jira_request_auth_and_errors(repo, monkeypatch):
    tracker = trackers.get(jira_cfg(repo))
    with pytest.raises(AwError, match="JIRA_USER_EMAIL, JIRA_API_TOKEN"):
        tracker.request("GET", "/rest/api/3/myself")
    monkeypatch.setenv("JIRA_USER_EMAIL", "me@example.invalid")
    monkeypatch.setenv("JIRA_API_TOKEN", "sekrit-token")
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"], seen["auth"] = req.full_url, req.get_header("Authorization")
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b'{"errorMessages":["denied"]}'))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(AwError) as e:
        tracker.request("GET", "/rest/api/3/myself")
    assert "HTTP 401" in str(e.value) and "sekrit" not in str(e.value)
    assert seen["url"] == "https://example.atlassian.net/rest/api/3/myself"
    assert seen["auth"].startswith("Basic ")
    monkeypatch.setenv("JIRA_CLOUD_ID", "abc")
    with pytest.raises(AwError):
        tracker.request("GET", "/x")
    assert seen["url"] == "https://api.atlassian.com/ex/jira/abc/x"


def test_jira_ids(repo):
    tracker = trackers.get(jira_cfg(repo))
    assert (tracker.normalize("proj-7"), tracker.ref("PROJ-7"), tracker.pr_text("PROJ-7")) == ("PROJ-7",) * 3
    with pytest.raises(AwError, match="invalid jira issue id"):
        tracker.normalize("#7")


# --- GitHub -------------------------------------------------------------------

def test_github_view_children_and_status(repo, monkeypatch):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('tracker = "github"\n')
    calls = []
    body = "Part of #3\n\n- [ ] #8 later\n- [x] #9"

    def fake_gh(self, *args, stdin=None):
        calls.append(args)
        if args[:2] == ("issue", "view") and "state" == args[-1]:
            return json.dumps({"state": "OPEN"})
        if args[:2] == ("issue", "view") and args[-1] == "number,title,state":
            return json.dumps({"number": int(args[2]), "title": f"Task {args[2]}", "state": "OPEN"})
        if args[:2] == ("issue", "view"):
            return json.dumps({"number": 5, "title": "T", "body": body, "state": "OPEN", "url": "u",
                               "labels": [{"name": "bug"}], "comments": [{"author": {"login": "a"}, "body": "c"}]})
        if args[0] == "api":
            return json.dumps([{"number": 9, "title": "Sub", "state": "CLOSED"}])
        return ""

    monkeypatch.setattr(GitHub, "gh", fake_gh)
    tracker = trackers.get(load())
    issue = tracker.view(tracker.normalize("#5"))
    assert (issue.ref, issue.parent.id, [c.id for c in issue.children]) == ("#5", "3", ["9", "8"])
    assert issue.children[1].title == "Task 8"
    assert tracker.pr_text("5") == "Fixes #5"
    assert tracker.set_status("5", "done") == "#5 closed"
    assert ("issue", "close", "5") in calls
    assert tracker.on_start("5") is None


# --- integration --------------------------------------------------------------

def test_start_and_finish_sync_jira_status(repo, tmp_path, monkeypatch):
    jira_cfg(repo, f'worktree_root = "{tmp_path}/wt"\nbranch_name = "{{type}}/{{issue}}-{{slug}}"\n')
    git("add", ".", cwd=repo)
    git("commit", "-qm", "cfg", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    moves = []
    monkeypatch.setattr(Jira, "set_status", lambda self, i, s: moves.append((i, s)) or f"{i} -> {s}")

    out = start_task.run(load(), "feat", "retries", "proj-12")
    assert out["branch"] == "feat/PROJ-12-retries" and out["issue"] == "PROJ-12"
    assert start_task.run(load(), "docs", "no-issue", None)["branch"] == "docs/no-issue"

    wt = out["worktree"]
    (tmp_path / "wt/s1-retries/f.txt").write_text("x")
    git("add", ".", cwd=wt)
    git("commit", "-qm", "feat: x", cwd=wt)
    git("push", "-q", "-u", "origin", out["branch"], cwd=wt)
    git("merge", "-q", "--no-ff", "-m", "m", out["branch"], cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    monkeypatch.chdir(wt)
    monkeypatch.setenv("AW_FORGE", "none")
    log = finish.run(load(), session.read(), None)
    assert moves == [("PROJ-12", "in_progress"), ("PROJ-12", "done")]
    assert "PROJ-12 -> done" in log


def test_cli_issue_ref_and_view(repo, monkeypatch, capsys):
    jira_cfg(repo)
    monkeypatch.setattr(Jira, "view", lambda self, i: trackers.Issue(id=i, ref=i, title="T", status="Open"))
    assert cli.main(["issue", "ref", "proj-3"]) == 0
    assert cli.main(["issue", "view", "proj-3"]) == 0
    assert cli.main(["issue", "view", "bad"]) == 1
    out = capsys.readouterr()
    assert out.out.startswith("PROJ-3\n# PROJ-3: T")
    assert "invalid jira issue id" in out.err


def test_doctor_jira_reports_missing_env_by_name(repo):
    from aw import doctor

    jira_cfg(repo)
    results = {m: lvl for lvl, m in doctor.check_jira(load())}
    assert results == {"JIRA_USER_EMAIL is not set": "fail", "JIRA_API_TOKEN is not set": "fail"}
