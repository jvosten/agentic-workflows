import io
import json
import urllib.error
import urllib.request
from email.message import Message

import pytest

from aw import cli, finish, session, start_task, trackers
from aw.config import AwError, git, load
from aw.trackers import adf
from aw.trackers.github import GitHub
from aw.trackers.jira import Jira

# --- ADF ----------------------------------------------------------------------

ADF_DOC = {
    "type": "doc",
    "version": 1,
    "content": [
        {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Goal"}]},
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Use "},
                {"type": "text", "text": "retries", "marks": [{"type": "strong"}]},
                {"type": "text", "text": " per "},
                {"type": "text", "text": "docs", "marks": [{"type": "link", "attrs": {"href": "https://x.test"}}]},
                {"type": "text", "text": ", ask "},
                {"type": "mention", "attrs": {"text": "@dev"}},
            ],
        },
        {
            "type": "bulletList",
            "content": [
                {
                    "type": "listItem",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "one"}]},
                        {
                            "type": "bulletList",
                            "content": [
                                {
                                    "type": "listItem",
                                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "nested"}]}],
                                }
                            ],
                        },
                    ],
                },
                {
                    "type": "listItem",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "cfg", "marks": [{"type": "code"}]}]}
                    ],
                },
            ],
        },
        {"type": "codeBlock", "attrs": {"language": "sh"}, "content": [{"type": "text", "text": "make test"}]},
        {
            "type": "table",
            "content": [
                {
                    "type": "tableRow",
                    "content": [
                        {
                            "type": "tableHeader",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "a"}]}],
                        },
                        {
                            "type": "tableHeader",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "b"}]}],
                        },
                    ],
                },
                {
                    "type": "tableRow",
                    "content": [
                        {
                            "type": "tableCell",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "1"}]}],
                        },
                        {
                            "type": "tableCell",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "2"}]}],
                        },
                    ],
                },
            ],
        },
    ],
}

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
        ("a ", []),
        ("b ", ["strong"]),
        ("c", ["strong", "em"]),
        (" ", []),
        ("d", ["code"]),
        (" ", []),
        ("e", ["strike"]),
    ]


def test_ordered_list_and_quote():
    doc = adf.from_markdown("1. first\n2. second\n\n> note\n")
    assert [n["type"] for n in doc["content"]] == ["orderedList", "blockquote"]


def test_a_list_at_column_zero_keeps_its_nested_levels():
    doc = adf.from_markdown("- a\n  - b\n    - c\n- d\n")

    def depth(node):
        lists = [n for item in node["content"] for n in item["content"] if n["type"] == "bulletList"]
        return 1 + max((depth(n) for n in lists), default=0)

    assert depth(doc["content"][0]) == 3
    assert adf.to_markdown(doc) == "- a\n  - b\n    - c\n- d\n"


# --- Jira ---------------------------------------------------------------------


def jira_cfg(repo, extra=""):
    (repo / ".agents").mkdir(exist_ok=True)
    (repo / ".agents/aw.toml").write_text(
        'tracker = "jira"\njira_base_url = "https://example.atlassian.net"\njira_project = "PROJ"\n'
        'jira_fields = { acceptance_criteria = "customfield_1" }\n' + extra
    )
    return load()


class FakeJira:
    """Records requests and serves canned responses keyed by (method, path)."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, method, path, params=None, body=None):
        self.calls.append((method, path, params, body))
        return self.responses.get((method, path), {})


ISSUE = {
    "key": "PROJ-12",
    "fields": {
        "summary": "Add retries",
        "status": {"name": "To Do"},
        "issuetype": {"name": "Story"},
        "labels": ["backend"],
        "parent": {"key": "PROJ-1", "fields": {"summary": "Epic one"}},
        "description": {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Body"}]}],
        },
        "customfield_1": {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "AC"}]}],
        },
        "comment": {
            "comments": [
                {
                    "author": {"displayName": "Dev"},
                    "body": {
                        "type": "doc",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "LGTM"}]}],
                    },
                }
            ]
        },
    },
}
CHILDREN = {
    "issues": [
        {
            "key": "PROJ-13",
            "fields": {"summary": "Subtask", "status": {"name": "Done"}, "issuetype": {"name": "Sub-task"}},
        }
    ]
}


def test_jira_view_renders_everything(repo, monkeypatch):
    fake = FakeJira({("GET", "/rest/api/3/issue/PROJ-12"): ISSUE, ("GET", "/rest/api/3/search/jql"): CHILDREN})
    tracker = Jira(jira_cfg(repo))
    monkeypatch.setattr(tracker, "request", fake)
    text = trackers.render(tracker.view(tracker.normalize("proj-12")))
    assert text.startswith("# PROJ-12: Add retries\n\nstatus: To Do · type: Story · parent: PROJ-1 (Epic one) ·")
    assert "text link" not in text
    assert "https://example.atlassian.net/browse/PROJ-12" in text
    assert "## Acceptance criteria\n\nAC" in text
    assert "- [Done] PROJ-13 (Sub-task) Subtask" in text
    assert "### Dev\n\nLGTM" in text
    assert "customfield_1" in fake.calls[0][2]["fields"]
    assert fake.calls[1][2]["jql"] == "parent = PROJ-12 ORDER BY created ASC"


def test_jira_queries(repo, monkeypatch):
    fake = FakeJira({})
    tracker = Jira(jira_cfg(repo))
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
    tracker = Jira(jira_cfg(repo))
    monkeypatch.setattr(tracker, "request", fake)
    assert tracker.create("Title", "## H\n\ntext", "proj-1", "Sub-task") == "PROJ-20"
    fields = fake.calls[0][3]["fields"]
    assert fields["parent"] == {"key": "PROJ-1"} and fields["issuetype"] == {"name": "Sub-task"}
    assert "labels" not in fields
    tracker.create("Title", "", None, None, ["backend", "debt"])
    assert fake.calls[-1][3]["fields"]["labels"] == ["backend", "debt"]
    assert fields["description"]["content"][0]["type"] == "heading"
    tracker.comment("PROJ-20", "hello")
    assert fake.calls[-1][:2] == ("POST", "/rest/api/3/issue/PROJ-20/comment")


def test_jira_set_parent_moves_clears_and_names_types_on_refusal(repo, monkeypatch):
    fake = FakeJira({("GET", "/rest/api/3/issue/PROJ-12"): ISSUE})
    tracker = Jira(jira_cfg(repo))
    monkeypatch.setattr(tracker, "request", fake)
    assert tracker.parent("PROJ-12") == trackers.Row("PROJ-1", "Epic one", "", "", "native")
    assert tracker.set_parent("PROJ-12", "proj-2") == "PROJ-12 parent PROJ-1 -> PROJ-2"
    assert fake.calls[-1] == ("PUT", "/rest/api/3/issue/PROJ-12", None, {"fields": {"parent": {"key": "PROJ-2"}}})
    assert tracker.set_parent("PROJ-12", None) == "PROJ-12 parent PROJ-1 -> none"
    assert fake.calls[-1][3] == {"fields": {"parent": None}}
    assert tracker.set_parent("PROJ-12", "PROJ-1") == "PROJ-12 already under PROJ-1"
    assert fake.calls[-1][0] == "GET"

    def refuse(method, path, params=None, body=None):
        if method == "PUT":
            raise AwError("jira PUT /rest/api/3/issue/PROJ-12: HTTP 400: parent: invalid hierarchy")
        if params == {"fields": "issuetype"}:
            return {"fields": {"issuetype": {"name": "Epic" if path.endswith("PROJ-9") else "Story"}}}
        return ISSUE

    monkeypatch.setattr(tracker, "request", refuse)
    with pytest.raises(AwError, match=r"PROJ-12 \(Story\) under PROJ-9 \(Epic\): .*invalid hierarchy"):
        tracker.set_parent("PROJ-12", "PROJ-9")


def test_jira_dupes_lists_the_tree_first_then_the_rest_of_the_project(repo, monkeypatch):
    def hit(key, parent=None):
        fields = {"summary": f"Retry {key}", "status": {"name": "To Do"}, "issuetype": {"name": "Task"}}
        if parent:
            fields["parent"] = {"key": parent}
        return {"key": key, "fields": fields}

    jqls = []

    def fake(method, path, params=None, body=None):
        assert params
        jqls.append(params["jql"])
        if params["jql"].startswith("parent = "):
            return CHILDREN
        return {
            "issues": [hit("PROJ-40", "PROJ-2"), hit("PROJ-14", "PROJ-13"), hit("PROJ-41"), hit("PROJ-13", "PROJ-12")]
        }

    tracker = Jira(jira_cfg(repo))
    monkeypatch.setattr(tracker, "request", fake)
    rows = tracker.dupes("PROJ-12", ["retry", "backoff"], 20)
    assert jqls[-1] == 'project = "PROJ" AND (text ~ "retry" OR text ~ "backoff") ORDER BY updated DESC'
    assert [(r.id, r.scope, r.parent) for r in rows] == [
        ("PROJ-14", "tree", "PROJ-13"),
        ("PROJ-13", "tree", "PROJ-12"),
        ("PROJ-40", "elsewhere", "PROJ-2"),
        ("PROJ-41", "elsewhere", ""),
    ]
    assert trackers.rows_line(rows[2]).endswith("[elsewhere: parent PROJ-2]")
    assert trackers.rows_line(rows[3]).endswith("[elsewhere: no parent]")

    tracker.dupes("PROJ-12", ["retry"], 20, tree_only=True)
    assert jqls[-1] == 'parent in (PROJ-12, PROJ-13) AND (text ~ "retry") ORDER BY updated DESC'


def test_jira_update_replaces_summary_and_description(repo, monkeypatch):
    fake = FakeJira({})
    tracker = Jira(jira_cfg(repo))
    monkeypatch.setattr(tracker, "request", fake)
    tracker.update("PROJ-12", "New title", "## H\n\ntext")
    method, path, _, body = fake.calls[0]
    assert (method, path) == ("PUT", "/rest/api/3/issue/PROJ-12")
    assert body["fields"]["summary"] == "New title"
    assert body["fields"]["description"]["content"][0]["type"] == "heading"


def test_jira_set_status(repo, monkeypatch):
    tracker = trackers.get(jira_cfg(repo, 'status_map = { in_progress = "Doing" }\n'))
    transitions = {
        "transitions": [
            {"id": "11", "name": "Start", "to": {"name": "Doing"}},
            {"id": "31", "name": "Finish", "to": {"name": "Done"}},
        ]
    }
    fake = FakeJira(
        {
            ("GET", "/rest/api/3/issue/PROJ-12"): {"fields": {"status": {"name": "To Do"}}},
            ("GET", "/rest/api/3/issue/PROJ-12/transitions"): transitions,
        }
    )
    monkeypatch.setattr(tracker, "request", fake)
    assert tracker.set_status("PROJ-12", "in_progress") == "PROJ-12 -> Doing"
    assert fake.calls[-1] == ("POST", "/rest/api/3/issue/PROJ-12/transitions", None, {"transition": {"id": "11"}})
    with pytest.raises(AwError, match="available: Doing, Done"):
        tracker.set_status("PROJ-12", "in_review")
    fake.responses[("GET", "/rest/api/3/issue/PROJ-12")] = {"fields": {"status": {"name": "done"}}}
    assert tracker.set_status("PROJ-12", "done") == "PROJ-12 already Done"


def test_jira_request_auth_and_errors(repo, monkeypatch):
    tracker = Jira(jira_cfg(repo))
    with pytest.raises(AwError, match="JIRA_USER_EMAIL, JIRA_API_TOKEN"):
        tracker.request("GET", "/rest/api/3/myself")
    monkeypatch.setenv("JIRA_USER_EMAIL", "me@example.invalid")
    monkeypatch.setenv("JIRA_API_TOKEN", "sekrit-token")
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"], seen["auth"] = req.full_url, req.get_header("Authorization")
        raise urllib.error.HTTPError(req.full_url, 401, "no", Message(), io.BytesIO(b'{"errorMessages":["denied"]}'))

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
    tracker = Jira(jira_cfg(repo))
    assert (tracker.normalize("proj-7"), tracker.ref("PROJ-7"), tracker.pr_text("PROJ-7")) == ("PROJ-7",) * 3
    with pytest.raises(AwError, match="invalid jira issue id"):
        tracker.normalize("#7")


# --- GitHub -------------------------------------------------------------------


def github_cfg(repo):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('tracker = "github"\n')
    return load()


class FakeGh:
    """Records gh calls and serves canned responses: GraphQL by operation name in the query, the rest by args."""

    def __init__(self, graphql=None, issues=None, subs=None):
        self.graphql, self.issues, self.subs = graphql or {}, issues or {}, subs or {}
        self.calls = []

    def ops(self):
        return [op for op, _, _ in self.calls if op]

    def __call__(self, *args, stdin=None):
        if args[:2] == ("api", "graphql"):
            pairs = [(flag, *value.split("=", 1)) for flag, value in zip(args[2::2], args[3::2], strict=True)]
            query = next(v for _, k, v in pairs if k == "query")
            fields = {}
            for flag, k, v in pairs:
                if k.endswith("[]"):
                    fields.setdefault(k, (flag, []))[1].append(v)
                elif k != "query":
                    fields[k] = (flag, v)
            op = next(name for name in self.graphql if name in query)
            self.calls.append((op, fields, stdin))
            response = self.graphql[op]
            return json.dumps({"data": response(fields) if callable(response) else response})
        self.calls.append((None, args, stdin))
        if args[0] == "api":  # the URL comes last, after flags such as --paginate
            return json.dumps(self.subs.get(args[-1].rsplit("/", 2)[-2], []))
        if args[:2] == ("issue", "view"):
            data = self.issues[args[2]]
            return json.dumps({k: data[k] for k in args[4].split(",") if k in data})
        if args[:2] == ("issue", "list"):
            return json.dumps(self.issues.get("list", []))
        if args[:2] == ("label", "list"):
            return json.dumps(self.issues.get("labels", []))
        if args[:2] == ("repo", "view"):
            return "me/proj"
        return ""


def gh_issue(number, title="T", body="", state="OPEN"):
    return {
        "number": number,
        "title": title,
        "body": body,
        "state": state,
        "url": "u",
        "labels": [{"name": "bug"}],
        "comments": [{"author": {"login": "a"}, "body": "c"}],
    }


def gh_meta(parent=None, body="", issue_type=None):
    return {"repository": {"issue": {"body": body, "issueType": issue_type and {"name": issue_type}, "parent": parent}}}


def test_github_view_prefers_the_native_parent_and_marks_text_children(repo, monkeypatch):
    github_cfg(repo)
    body = "Part of #3\n\n- [ ] #8 later\n- [x] #9"
    fake = FakeGh(
        graphql={"body issueType": gh_meta({"number": 4, "title": "Epic", "state": "OPEN"}, body, "Feature")},
        issues={"5": gh_issue(5, body=body), "8": gh_issue(8, "Task 8")},
        subs={"5": [{"number": 9, "title": "Sub", "state": "CLOSED"}]},
    )
    monkeypatch.setattr(GitHub, "gh", fake)
    tracker = trackers.get(load())
    issue = tracker.view(tracker.normalize("#5"))
    assert issue.parent
    assert (issue.ref, issue.type, issue.parent.id, issue.parent.link) == ("#5", "Feature", "4", "native")
    assert [(c.id, c.link) for c in issue.children] == [("9", "native"), ("8", "text")]
    text = trackers.render(issue)
    assert "parent: 4 (Epic) ·" in text and "[text link]" not in text.split("\n")[2]
    assert "- [open] 8 Task 8 [text link]" in text and "- [closed] 9 Sub\n" in text
    assert fake.calls[1][1]["number"] == ("-F", "5")


def test_github_parent_falls_back_to_a_part_of_line(repo, monkeypatch):
    github_cfg(repo)
    monkeypatch.setattr(GitHub, "gh", FakeGh(graphql={"body issueType": gh_meta(None, "Part of #3")}))
    assert trackers.get(load()).parent("5") == trackers.Row("3", link="text")


def test_github_parent_carries_its_type_and_an_epic_type_stops_the_rollup(repo, monkeypatch):
    github_cfg(repo)
    parent = {"number": 4, "title": "Big", "state": "OPEN", "issueType": {"name": "epic"}}
    monkeypatch.setattr(GitHub, "gh", FakeGh(graphql={"body issueType": gh_meta(parent)}))
    tracker = trackers.get(load())
    row = tracker.parent("5")
    assert row
    assert (row.id, row.type, row.link) == ("4", "epic", "native")
    assert tracker.is_epic(row)  # epic_types match case-insensitively
    assert not tracker.is_epic(trackers.Row("4", type="Feature"))


def test_board_card_without_a_column_is_an_epic(repo, monkeypatch):
    board_cfg(repo)
    for column, epic in ((None, True), ("Backlog", False), (False, False)):  # False: not on the board
        monkeypatch.setattr(GitHub, "gh", board_gh(column))
        assert trackers.get(load()).is_epic(trackers.Row("5")) is epic, column


def test_jira_epic_by_hierarchy_level_and_closed_by_category(repo, monkeypatch):
    tracker = Jira(jira_cfg(repo))
    level = {"key": "PROJ-1", "fields": {"summary": "Initiative", "issuetype": {"name": "Theme", "hierarchyLevel": 1}}}
    fake = FakeJira(
        {
            ("GET", "/rest/api/3/issue/PROJ-12"): {"fields": {"parent": level}},
            ("GET", "/rest/api/3/search/jql"): {
                "issues": [
                    {"key": key, "fields": {"status": {"name": name, "statusCategory": {"key": category}}}}
                    for key, name, category in (("PROJ-13", "Shipped", "done"), ("PROJ-14", "QA", "indeterminate"))
                ]
            },
        }
    )
    monkeypatch.setattr(tracker, "request", fake)
    parent = tracker.parent("PROJ-12")
    assert parent
    assert tracker.is_epic(parent)
    assert not tracker.is_epic(trackers.Row("PROJ-2", type="Story"))
    children = tracker.children("PROJ-1")
    calls = len(fake.calls)
    assert [tracker.closed(row) for row in children] == [True, False]
    assert len(fake.calls) == calls  # the categories came with the search


def test_github_set_status(repo, monkeypatch):
    github_cfg(repo)
    fake = FakeGh(issues={"5": gh_issue(5)})
    monkeypatch.setattr(GitHub, "gh", fake)
    tracker = trackers.get(load())
    assert tracker.pr_text("5") == "Fixes #5"
    assert tracker.set_status("5", "done") == "#5 closed"
    assert (None, ("issue", "close", "5"), None) in fake.calls
    assert tracker.advance("5", "in_progress") == []  # no board, no hook: nothing to move


def test_github_text_only_children_are_what_is_left_to_migrate(repo, monkeypatch, capsys):
    github_cfg(repo)
    search = {
        "search": {
            "nodes": [
                {"number": 11, "title": "Says part of", "state": "OPEN", "body": "Part of #5", "parent": None},
                {
                    "number": 12,
                    "title": "Already native",
                    "state": "OPEN",
                    "body": "Part of #5",
                    "parent": {"number": 5},
                },
                {"number": 13, "title": "Other epic", "state": "OPEN", "body": "Part of #50", "parent": None},
                {"number": 8, "title": "Task 8", "state": "OPEN", "body": "Part of #5", "parent": None},
            ]
        }
    }
    fake = FakeGh(
        graphql={"search(": search},
        issues={"5": gh_issue(5, body="- [ ] #8\n- [ ] #9"), "8": gh_issue(8, "Task 8")},
        subs={"5": [{"number": 9, "title": "Sub", "state": "OPEN"}]},
    )
    monkeypatch.setattr(GitHub, "gh", fake)
    assert cli.main(["issue", "children", "5", "--text-only", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [(r["id"], r["link"]) for r in rows] == [("8", "text"), ("11", "text")]
    assert fake.calls[-1][1]["q"] == ("-F", 'repo:{owner}/{repo} is:issue "Part of #5" in:body')


def test_github_create_links_and_types_in_one_mutation(repo, monkeypatch):
    github_cfg(repo)
    context = {
        "repository": {
            "id": "R1",
            "owner": {"__typename": "Organization"},
            "parent": {"id": "I3"},
            "issueTypes": {"nodes": [{"id": "T1", "name": "Bug"}, {"id": "T2", "name": "Task"}]},
        }
    }
    fake = FakeGh(graphql={"issueTypes": context, "createIssue": {"createIssue": {"issue": {"number": 21}}}})
    monkeypatch.setattr(GitHub, "gh", fake)
    tracker = trackers.get(load())
    assert tracker.create("42", "## Body", "#3", "task") == "21"
    assert fake.ops() == ["issueTypes", "createIssue"]
    assert fake.calls[0][1]["parent"] == ("-F", "3") and fake.calls[0][1]["withParent"] == ("-F", "true")
    _, fields, stdin = fake.calls[1]
    assert fields["title"] == ("-f", "42") and fields["body"] == ("-F", "@-") and stdin == "## Body"
    assert (fields["repoId"], fields["parentId"], fields["typeId"]) == (("-F", "R1"), ("-F", "I3"), ("-F", "T2"))

    with pytest.raises(AwError, match="unknown issue type 'Epic' \\(available: Bug, Task\\)"):
        tracker.create("T", "", None, "Epic")
    assert fake.ops().count("createIssue") == 1


def test_github_create_sets_labels_in_the_same_mutation(repo, monkeypatch):
    github_cfg(repo)
    context = {
        "repository": {
            "id": "R1",
            "owner": {"__typename": "User"},
            "issueTypes": None,
            "labels": {"nodes": [{"id": "L1", "name": "infra"}, {"id": "L2", "name": "Tech debt"}]},
        }
    }
    fake = FakeGh(graphql={"issueTypes": context, "createIssue": {"createIssue": {"issue": {"number": 23}}}})
    monkeypatch.setattr(GitHub, "gh", fake)
    tracker = trackers.get(load())
    assert tracker.create("T", "", None, None, ["infra", "tech debt"]) == "23"
    assert fake.calls[1][1]["labelIds[]"] == ("-F", ["L1", "L2"])
    with pytest.raises(AwError, match="unknown label\\(s\\): bug"):
        tracker.create("T", "", None, None, ["infra", "bug"])
    assert fake.ops().count("createIssue") == 1


def test_github_create_warns_that_user_repos_have_no_types(repo, monkeypatch, capsys):
    github_cfg(repo)
    context = {"repository": {"id": "R1", "owner": {"__typename": "User"}, "issueTypes": None}}
    fake = FakeGh(graphql={"issueTypes": context, "createIssue": {"createIssue": {"issue": {"number": 22}}}})
    monkeypatch.setattr(GitHub, "gh", fake)
    assert trackers.get(load()).create("T", "", None, "Task") == "22"
    assert "parentId" not in fake.calls[1][1] and "typeId" not in fake.calls[1][1]
    assert "--type 'Task' ignored: issue types need an organization-owned repository" in capsys.readouterr().err


def test_github_set_parent_links_replaces_and_unlinks(repo, monkeypatch):
    github_cfg(repo)
    state = {"parent": {"id": "I2", "number": 2}}

    def context(fields):
        return {"repository": {"issue": {"id": "I5", "parent": state["parent"]}, "target": {"id": "I3"}}}

    fake = FakeGh(graphql={"target:": context, "addSubIssue": {}, "removeSubIssue": {}})
    monkeypatch.setattr(GitHub, "gh", fake)
    tracker = trackers.get(load())
    assert tracker.set_parent("5", "3") == "#5 parent #2 -> #3"
    assert fake.calls[-1][1] == {
        "owner": ("-F", "{owner}"),
        "repo": ("-F", "{repo}"),
        "parentId": ("-F", "I3"),
        "childId": ("-F", "I5"),
    }
    assert tracker.set_parent("5", None) == "#5 parent #2 -> none"
    assert fake.calls[-1][0] == "removeSubIssue" and fake.calls[-1][1]["parentId"] == ("-F", "I2")
    state["parent"] = {"id": "I3", "number": 3}
    assert tracker.set_parent("5", "3") == "#5 already under #3"
    state["parent"] = None
    assert tracker.set_parent("5", None) == "#5 has no parent"
    assert fake.ops() == ["target:", "addSubIssue", "target:", "removeSubIssue", "target:", "target:"]


def test_cli_set_parent_dry_run_and_arguments(repo, monkeypatch, capsys):
    jira_cfg(repo)
    calls = []
    monkeypatch.setattr(Jira, "parent", lambda self, i: trackers.Row("PROJ-1", link="native"))
    monkeypatch.setattr(Jira, "set_parent", lambda self, i, p: calls.append((i, p)) or f"{i} -> {p}")
    assert cli.main(["issue", "set-parent", "proj-5", "proj-2", "--dry-run"]) == 0
    assert capsys.readouterr().out == "DRY RUN (jira): PROJ-5 parent PROJ-1 (native link) -> PROJ-2\n"
    assert calls == []
    assert cli.main(["issue", "set-parent", "proj-5", "--none"]) == 0
    assert calls == [("PROJ-5", None)]
    assert cli.main(["issue", "set-parent", "proj-5"]) == 1
    assert cli.main(["issue", "set-parent", "proj-5", "proj-2", "--none"]) == 1
    assert cli.main(["issue", "set-parent", "proj-5", "proj-5"]) == 1
    assert "cannot be its own parent" in capsys.readouterr().err
    assert len(calls) == 1


def test_github_dupes_shows_hits_outside_the_tree_after_those_in_it(repo, monkeypatch, capsys):
    github_cfg(repo)

    def search(fields):
        term = fields["q"][1].rsplit(" ", 1)[-1]
        nodes = {
            "backoff": [
                {"number": 40, "title": "Backoff, linked by text only", "state": "OPEN", "parent": None},
                {"number": 9, "title": "Backoff", "state": "CLOSED", "parent": {"number": 8}},
                {"number": 41, "title": "Backoff audit", "state": "OPEN", "parent": {"number": 3}},
            ]
        }
        return {"search": {"nodes": nodes.get(term, [])}}

    fake = FakeGh(
        graphql={"search(": search},
        issues={
            "7": gh_issue(7, body="- [ ] #40"),
            "8": gh_issue(8),
            "9": gh_issue(9),
            "40": gh_issue(40, "Backoff, linked by text only"),
        },
        subs={
            "7": [{"number": 8, "title": "Retry uploads", "state": "OPEN"}],
            "8": [{"number": 9, "title": "Backoff", "state": "CLOSED"}],
        },
    )
    monkeypatch.setattr(GitHub, "gh", fake)
    tracker = trackers.get(load())
    rows = tracker.dupes("7", ["backoff", "retry"], 20)
    assert [(r.id, r.scope, r.parent) for r in rows] == [
        ("8", "tree", "7"),
        ("9", "tree", "8"),
        ("40", "elsewhere", ""),
        ("41", "elsewhere", "3"),
    ]
    searches = [fields["q"][1] for op, fields, _ in fake.calls if op == "search("]
    assert searches == ["repo:{owner}/{repo} is:issue backoff", "repo:{owner}/{repo} is:issue retry"]

    assert [r.id for r in tracker.dupes("7", ["backoff", "retry"], 20, tree_only=True)] == ["8", "9"]

    assert cli.main(["issue", "dupes", "7", "--terms", "backoff"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "- [closed] 9 Backoff",
        "- [open] 40 Backoff, linked by text only [elsewhere: no parent]",
        "- [open] 41 Backoff audit [elsewhere: parent 3]",
    ]
    # 41 matches both terms, 40 only one: within the group, more matched terms rank first
    original = search

    def search(fields):
        data = original(fields)
        if fields["q"][1].endswith(" audit"):
            data = {"search": {"nodes": [{"number": 41, "title": "Backoff audit", "state": "OPEN", "parent": None}]}}
        return data

    fake.graphql["search("] = search
    assert [r.id for r in tracker.dupes("7", ["backoff", "audit"], 20)] == ["9", "41", "40"]

    assert not [
        c for c in fake.calls if c[0] is None and c[1][:2] == ("issue", "view")
    ]  # the tree needs no body or task-list lookups

    capsys.readouterr()
    assert cli.main(["issue", "dupes", "7", "--terms", "backoff", "--limit", "2"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "- [closed] 9 Backoff",
        "- [open] 40 Backoff, linked by text only [elsewhere: no parent]",
        "… 1 more elsewhere, matching fewer terms (--limit raises the cap)",
    ]

    rows = tracker.dupes(None, ["backoff"], 20)  # no parent: the whole repo, every hit elsewhere
    assert [(r.id, r.scope) for r in rows] == [("9", "elsewhere"), ("40", "elsewhere"), ("41", "elsewhere")]
    assert cli.main(["issue", "dupes", "--terms", "backoff", "--tree-only"]) == 1


def test_github_update_replaces_title_and_body(repo, monkeypatch):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('tracker = "github"\n')
    calls = []

    def fake_gh(self, *args, stdin=None):
        calls.append((args, stdin))
        return ""

    monkeypatch.setattr(GitHub, "gh", fake_gh)
    tracker = trackers.get(load())
    tracker.update("5", "New title", "New body")
    assert calls == [(("issue", "edit", "5", "--title", "New title", "--body-file", "-"), "New body")]


# --- integration --------------------------------------------------------------


def test_start_and_finish_sync_jira_status(repo, tmp_path, monkeypatch):
    jira_cfg(
        repo,
        f'worktree_root = "{tmp_path}/wt"\nbranch_name = "{{type}}/{{issue}}-{{slug}}"\n'
        f'on_issue_status = "echo {{issue}} {{status}} {{status_name}} >> {tmp_path}/board.log"\n'
        'status_map = { done = "Shipped" }\n',
    )
    git("add", ".", cwd=repo)
    git("commit", "-qm", "cfg", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    moves = []
    monkeypatch.setattr(Jira, "set_status", lambda self, i, s: moves.append((i, s)) or f"{i} -> {s}")
    monkeypatch.setattr(Jira, "current_status", lambda self, i: "To Do")
    # unmapped, but Jira's to-do category; PROJ-13, the story's other subtask, is done
    monkeypatch.setattr(Jira, "status_category", lambda self, i: "done" if i == "PROJ-13" else "new")
    story = trackers.Row("PROJ-1", "Story", type="Story", link="native")
    monkeypatch.setattr(Jira, "parent", lambda self, i: story if i == "PROJ-12" else None)
    monkeypatch.setattr(Jira, "children", lambda self, i: [trackers.Row("PROJ-12"), trackers.Row("PROJ-13")])

    out = start_task.run(load(), "feat", "retries", "proj-12")
    assert out["branch"] == "feat/PROJ-12-retries" and out["issue"] == "PROJ-12"
    assert start_task.run(load(), "docs", "no-issue", None)["branch"] == "docs/no-issue"

    wt = out["worktree"]
    (tmp_path / "wt/PROJ-12-retries/f.txt").write_text("x")
    git("add", ".", cwd=wt)
    git("commit", "-qm", "feat: x", cwd=wt)
    git("push", "-q", "-u", "origin", out["branch"], cwd=wt)
    git("merge", "-q", "--no-ff", "-m", "m", out["branch"], cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    monkeypatch.chdir(wt)
    monkeypatch.setenv("AW_FORGE", "none")
    log = finish.run(load(), session.read(), None)
    assert moves == [("PROJ-12", "in_progress"), ("PROJ-1", "in_progress"), ("PROJ-12", "done")]
    assert "PROJ-12 -> done" in log
    assert (
        "PROJ-1 can close: no child open besides PROJ-12 (children: PROJ-12, PROJ-13); "
        "`aw issue rollup PROJ-12 --close` closes it"
    ) in log
    assert (tmp_path / "board.log").read_text() == (
        "PROJ-12 in_progress In Progress\nPROJ-1 in_progress In Progress\nPROJ-12 done Shipped\n"
    )


def test_cli_issue_ref_and_view(repo, monkeypatch, capsys):
    jira_cfg(repo)
    monkeypatch.setattr(Jira, "view", lambda self, i: trackers.Issue(id=i, ref=i, title="T", status="Open"))
    assert cli.main(["issue", "ref", "proj-3"]) == 0
    assert cli.main(["issue", "view", "proj-3"]) == 0
    assert cli.main(["issue", "view", "bad"]) == 1
    out = capsys.readouterr()
    assert out.out.startswith("PROJ-3\n# PROJ-3: T")
    assert "invalid jira issue id" in out.err


def test_cli_set_status_runs_the_status_hook(repo, tmp_path, monkeypatch, capfd):
    github_cfg(repo)
    (repo / ".agents/aw.toml").write_text(
        'tracker = "github"\nstatus_map = { backlog = "Inbox" }\n'
        f'on_issue_status = "echo {{issue}}={{status_name}} > {tmp_path}/hook"\n'
    )
    monkeypatch.setattr(GitHub, "set_status", lambda self, i, s: f"#{i} open")
    assert cli.main(["issue", "set-status", "7", "backlog"]) == 0
    assert (tmp_path / "hook").read_text() == "7=Inbox\n"
    assert capfd.readouterr().out.splitlines()[0] == "#7 open"

    (repo / ".agents/aw.toml").write_text('tracker = "github"\non_issue_status = "exit 3"\n')
    assert cli.main(["issue", "set-status", "7", "ready"]) == 1
    assert "on_issue_status exited 3" in capfd.readouterr().err


def test_cli_issue_dupes_marks_closed_candidates(repo, monkeypatch, capsys):
    jira_cfg(repo)
    monkeypatch.setattr(
        Jira,
        "dupes",
        lambda self, parent, terms, limit, tree_only: [trackers.Row("PROJ-20", "Retry uploads", "Done", "Sub-task")],
    )
    assert cli.main(["issue", "dupes", "proj-12", "--terms", "retry", "upload"]) == 0
    assert capsys.readouterr().out.strip() == "- [Done] PROJ-20 (Sub-task) Retry uploads"


def test_cli_issue_update_dry_run_writes_nothing(repo, tmp_path, monkeypatch, capsys):
    jira_cfg(repo)
    calls = []
    monkeypatch.setattr(Jira, "update", lambda self, i, t, b: calls.append((i, t, b)))
    body = tmp_path / "body.md"
    body.write_text("line one\nline two\n")
    assert cli.main(["issue", "update", "proj-3", "--body-file", str(body), "--dry-run"]) == 0
    assert calls == []
    assert "DRY RUN" in capsys.readouterr().out
    assert cli.main(["issue", "update", "proj-3", "--title", "T", "--body-file", str(body)]) == 0
    assert calls == [("PROJ-3", "T", "line one\nline two\n")]


def test_doctor_jira_reports_missing_env_by_name(repo):
    from aw import doctor

    jira_cfg(repo)
    results = {m: lvl for lvl, m in doctor.check_jira(load())}
    assert results == {"JIRA_USER_EMAIL is not set": "fail", "JIRA_API_TOKEN is not set": "fail"}


def test_doctor_jira_probes_search_not_myself(repo, monkeypatch):
    from aw import doctor

    jira_cfg(repo)
    monkeypatch.setenv("JIRA_USER_EMAIL", "a@b.c")
    monkeypatch.setenv("JIRA_API_TOKEN", "x")
    paths = []
    monkeypatch.setattr(Jira, "request", lambda self, method, path, *a, **k: paths.append(path) or {})
    assert ("ok", "jira authenticated") in doctor.check_jira(load())
    assert paths == ["/rest/api/3/search/jql"]


# --- GitHub Projects board -------------------------------------------------------

BOARD = {
    "repositoryOwner": {
        "projectV2": {
            "id": "P1",
            "title": "Homelab",
            "field": {
                "id": "F1",
                "name": "Status",
                "options": [
                    {"id": "o-backlog", "name": "Backlog"},
                    {"id": "o-ready", "name": "Ready"},
                    {"id": "o-progress", "name": "In progress"},
                    {"id": "o-done", "name": "Done"},
                ],
            },
            "fields": {
                "nodes": [
                    {"id": "F1", "name": "Status", "options": []},
                    {
                        "id": "F2",
                        "name": "Area",
                        "options": [
                            {"id": "a-net", "name": "net"},
                            {"id": "a-k8s", "name": "k8s"},
                            {"id": "a-lab", "name": "home lab"},
                        ],
                    },
                    {
                        "id": "F3",
                        "name": "Priority",
                        "options": [{"id": "p-1", "name": "P1"}, {"id": "p-2", "name": "P2"}],
                    },
                    {},  # a field that is not single-select
                ]
            },
            "workflows": {
                "nodes": [
                    {"name": "Item closed", "enabled": False},
                    {"name": "Auto-add sub-issues to project", "enabled": True},
                ]
            },
        }
    }
}


def board_cfg(repo, extra=""):
    (repo / ".agents").mkdir(exist_ok=True)
    (repo / ".agents/aw.toml").write_text(f'tracker = "github"\ngithub_project = "jvosten/1"\n{extra}')
    return load()


def card(status=None, item="I1", project="P1"):
    nodes = (
        []
        if status is False
        else [{"id": item, "project": {"id": project}, "fieldValueByName": status and {"name": status}}]
    )
    return {"repository": {"issue": {"id": "ISSUE5", "projectItems": {"nodes": nodes}}}}


def board_gh(status=None, state="OPEN", **graphql):
    return FakeGh(
        graphql={
            "repositoryOwner": BOARD,
            "projectItems": card(status),
            "addProjectV2ItemById": {"addProjectV2ItemById": {"item": {"id": "I2"}}},
            "updateProjectV2ItemFieldValue": {},
            **graphql,
        },
        issues={"5": gh_issue(5, state=state)},
    )


def test_board_set_status_moves_the_card_and_matches_columns_case_insensitively(repo, monkeypatch):
    board_cfg(repo)
    fake = board_gh("Backlog")
    monkeypatch.setattr(GitHub, "gh", fake)
    tracker = trackers.get(load())
    assert tracker.set_status("5", "in_progress") == "#5 open · board In progress"
    _, fields, _ = fake.calls[-1]
    assert fake.calls[-1][0] == "updateProjectV2ItemFieldValue"
    assert (fields["projectId"], fields["itemId"], fields["fieldId"], fields["optionId"]) == (
        ("-F", "P1"),
        ("-F", "I1"),
        ("-F", "F1"),
        ("-f", "o-progress"),
    )
    assert fake.ops().count("repositoryOwner") == 1  # the board is read once per run


def test_board_adds_a_missing_card_and_skips_a_card_already_there(repo, monkeypatch):
    board_cfg(repo)
    fake = board_gh(False)
    monkeypatch.setattr(GitHub, "gh", fake)
    assert trackers.get(load()).set_status("5", "backlog") == "#5 open · board Backlog"
    assert fake.ops()[-2:] == ["addProjectV2ItemById", "updateProjectV2ItemFieldValue"]
    assert fake.calls[-1][1]["itemId"] == ("-F", "I2")

    fake = board_gh("In progress")
    monkeypatch.setattr(GitHub, "gh", fake)
    assert trackers.get(load()).set_status("5", "in_progress") == "#5 open · board already In progress"
    assert "updateProjectV2ItemFieldValue" not in fake.ops()


def test_board_done_closes_the_issue_and_an_unknown_column_changes_nothing(repo, monkeypatch):
    board_cfg(repo)
    fake = board_gh("In progress")
    monkeypatch.setattr(GitHub, "gh", fake)
    tracker = trackers.get(load())
    assert tracker.set_status("5", "done") == "#5 closed · board Done"
    assert (None, ("issue", "close", "5"), None) in fake.calls

    calls = len(fake.calls)
    with pytest.raises(AwError, match=r"no column 'In Review' \(columns: Backlog, Ready, In progress, Done\)"):
        tracker.set_status("5", "in_review")
    assert len(fake.calls) == calls


def test_session_start_never_moves_a_card_backwards(repo, monkeypatch):
    board_cfg(repo)
    for current, moved in (("Done", False), ("In progress", False), ("Ready", True), (None, True)):
        fake = board_gh(current)
        monkeypatch.setattr(GitHub, "gh", fake)
        messages = trackers.get(load()).advance("5", "in_progress")
        assert ("updateProjectV2ItemFieldValue" in fake.ops()) is moved, current
        if not moved:
            assert messages == [f"#5 stays at {current}: a session start moves only from backlog or ready"]
    fake = board_gh("In progress")
    monkeypatch.setattr(GitHub, "gh", fake)
    assert trackers.get(load()).advance("5", "done") == ["#5 closed · board Done"]


def test_jira_session_start_leaves_an_issue_in_review(repo, monkeypatch):
    tracker = trackers.get(jira_cfg(repo, 'status_map = { in_review = "Code Review" }\n'))
    monkeypatch.setattr(Jira, "current_status", lambda self, i: "Code Review")
    monkeypatch.setattr(Jira, "set_status", lambda self, i, s: pytest.fail("moved backwards"))
    assert tracker.advance("PROJ-12", "in_progress") == [
        "PROJ-12 stays at Code Review: a session start moves only from backlog or ready"
    ]


def test_board_create_puts_the_issue_on_the_board_or_names_the_repair(repo, monkeypatch):
    board_cfg(repo)
    context = {"repository": {"id": "R1", "owner": {"__typename": "User"}, "issueTypes": None}}
    fake = board_gh(False, issueTypes=context, createIssue={"createIssue": {"issue": {"number": 5}}})
    monkeypatch.setattr(GitHub, "gh", fake)
    assert trackers.get(load()).create("T", "", None, None) == "5"
    assert fake.ops() == [
        "repositoryOwner",
        "issueTypes",
        "createIssue",
        "projectItems",
        "addProjectV2ItemById",
        "updateProjectV2ItemFieldValue",
    ]

    def refuse(fields):
        raise AwError("gh api graphql: insufficient scopes")

    fake = board_gh(
        False, issueTypes=context, createIssue={"createIssue": {"issue": {"number": 5}}}, addProjectV2ItemById=refuse
    )
    monkeypatch.setattr(GitHub, "gh", fake)
    with pytest.raises(
        AwError,
        match=r"created #5, but it is not on the board as asked: .*insufficient scopes.*"
        r"aw issue set-status 5 backlog`; do not create it again",
    ):
        trackers.get(load()).create("T", "", None, None)


def test_board_without_the_backlog_column_fails_before_create(repo, monkeypatch):
    board_cfg(repo, 'status_map = { backlog = "Icebox" }\n')
    fake = board_gh(False)
    monkeypatch.setattr(GitHub, "gh", fake)
    with pytest.raises(AwError, match="no column 'Icebox'"):
        trackers.get(load()).create("T", "", None, None)
    assert "createIssue" not in fake.ops()


def test_doctor_checks_scope_columns_and_advises_on_workflows(repo, monkeypatch):
    from aw import doctor

    board_cfg(repo, 'status_map = { in_review = "In review" }\n')
    monkeypatch.setattr(GitHub, "gh", board_gh())
    monkeypatch.setattr(doctor, "_gh_scopes", lambda: ["repo"])
    assert doctor.check_board(load()) == [
        ("fail", "gh token lacks the project scope; run `gh auth refresh -s project`")
    ]

    monkeypatch.setattr(doctor, "_gh_scopes", lambda: ["repo", "project"])
    results = doctor.check_board(load())
    assert results[0] == ("ok", "board jvosten/1 (Homelab), field Status")
    assert results[1][0] == "fail" and "in_review → In review" in results[1][1]
    assert results[2] == (
        "info",
        "board workflow 'Item closed' is off: issues closed outside aw finish stay out of Done",
    )

    board_cfg(repo)
    assert doctor.check_board(load())[1] == ("ok", "board columns for backlog, in_progress, done")


def test_session_start_leaves_unmapped_columns_alone_except_jira_to_do(repo, monkeypatch):
    board_cfg(repo)
    fake = board_gh("Blocked")
    monkeypatch.setattr(GitHub, "gh", fake)
    messages = trackers.get(load()).advance("5", "in_progress")
    assert messages[0].startswith("#5 stays at Blocked: a session start moves only from backlog or ready; ")
    assert "status_map.backlog or status_map.ready" in messages[0]
    assert "updateProjectV2ItemFieldValue" not in fake.ops()

    tracker = Jira(jira_cfg(repo))
    for category, moves in (("new", True), ("indeterminate", False)):
        issue = {"fields": {"status": {"name": "Selected", "statusCategory": {"key": category}}}}
        moved = []
        monkeypatch.setattr(tracker, "request", FakeJira({("GET", "/rest/api/3/issue/PROJ-12"): issue}))
        monkeypatch.setattr(Jira, "set_status", lambda self, i, s, moved=moved: moved.append(s) or f"{i} -> {s}")
        tracker._categories = {}
        tracker.advance("PROJ-12", "in_progress")
        assert bool(moved) is moves, category


def test_create_status_puts_the_card_in_a_column_or_none(repo, monkeypatch):
    board_cfg(repo)
    context = {"repository": {"id": "R1", "owner": {"__typename": "User"}, "issueTypes": None}}
    fake = board_gh(False, issueTypes=context, createIssue={"createIssue": {"issue": {"number": 5}}})
    monkeypatch.setattr(GitHub, "gh", fake)
    trackers.get(load()).create("Epic", "", None, None, status="none")
    assert fake.ops()[-1] == "addProjectV2ItemById"  # on the board, no column

    fake = board_gh(False, issueTypes=context, createIssue={"createIssue": {"issue": {"number": 5}}})
    monkeypatch.setattr(GitHub, "gh", fake)
    trackers.get(load()).create("Slice", "", None, None, status="ready")
    assert fake.calls[-1][1]["optionId"] == ("-f", "o-ready")

    github_cfg_path = repo / ".agents/aw.toml"
    github_cfg_path.write_text('tracker = "github"\n')
    with pytest.raises(AwError, match="--status ready needs a board"):
        trackers.get(load()).create("T", "", None, None, status="ready")


def created_board(status=False, **graphql):
    context = {"repository": {"id": "R1", "owner": {"__typename": "User"}, "issueTypes": None}}
    return board_gh(status, issueTypes=context, createIssue={"createIssue": {"issue": {"number": 5}}}, **graphql)


def field_sets(fake):
    return [
        (fields["fieldId"][1], fields["optionId"][1])
        for op, fields, _ in fake.calls
        if op == "updateProjectV2ItemFieldValue"
    ]


def test_create_sets_board_fields_on_the_new_card(repo, monkeypatch):
    board_cfg(repo)
    fake = created_board()
    monkeypatch.setattr(GitHub, "gh", fake)
    assert trackers.get(load()).create("T", "", None, None, fields={"area": "NET", "Priority": "p2"}) == "5"
    assert field_sets(fake) == [("F1", "o-backlog"), ("F2", "a-net"), ("F3", "p-2")]
    assert fake.ops().count("repositoryOwner") == 1


def test_create_with_an_unknown_field_or_option_creates_nothing(repo, monkeypatch):
    board_cfg(repo)
    for fields, error in (
        ({"Team": "x"}, r"no single-select field 'Team' \(fields: Area, Priority\)"),
        ({"Area": "dns"}, r"field 'Area' has no option 'dns' \(options: net, k8s, home lab\)"),
        ({"status": "Done"}, r"Status is the status field; set it with --status"),
    ):
        fake = created_board()
        monkeypatch.setattr(GitHub, "gh", fake)
        with pytest.raises(AwError, match=error):
            trackers.get(load()).create("T", "", None, None, fields=fields)
        assert "createIssue" not in fake.ops()

    github_cfg_path = repo / ".agents/aw.toml"
    github_cfg_path.write_text('tracker = "github"\n')
    with pytest.raises(AwError, match="--field needs a board"):
        trackers.get(load()).create("T", "", None, None, fields={"Area": "net"})


def test_create_names_both_repairs_when_a_field_fails(repo, monkeypatch):
    board_cfg(repo)

    def refuse(fields):
        if fields["fieldId"][1] == "F3":
            raise AwError("gh api graphql: something broke")
        return {}

    fake = created_board(updateProjectV2ItemFieldValue=refuse)
    monkeypatch.setattr(GitHub, "gh", fake)
    with pytest.raises(
        AwError,
        match=r"created #5, but it is not on the board as asked: .*something broke.*"
        r"Run `aw issue set-status 5 backlog` and `aw issue set-field 5 'Area=home lab' Priority=P2`; "
        r"do not create it again",
    ):
        trackers.get(load()).create("T", "", None, None, fields={"Area": "home lab", "Priority": "P2"})


def test_fields_from_flags_and_labels(repo):
    cfg = board_cfg(repo, 'board_fields = { "area/" = "Area", "prio-" = "Priority" }\n')
    assert trackers.board_fields(cfg, ["bug", "Area/net", "area/k8s", "prio-"], []) == {"Area": "net"}
    assert trackers.board_fields(cfg, ["area/net", "prio-P1"], ["area=k8s"]) == {"area": "k8s", "Priority": "P1"}
    assert trackers.board_fields(cfg, ["area/net"], ["Area=k8s"], from_labels=False) == {"Area": "k8s"}
    for bad, error in ((["Area"], "Name=Value"), (["=x"], "Name=Value"), (["Area=a", "area=b"], "twice")):
        with pytest.raises(AwError, match=error):
            trackers.board_fields(cfg, [], bad)


def test_cli_create_and_set_field(repo, monkeypatch, capsys):
    board_cfg(repo, 'board_fields = { "area/" = "Area" }\n')
    fake = created_board()
    monkeypatch.setattr(GitHub, "gh", fake)
    monkeypatch.setattr("sys.stdin", io.StringIO("body"))
    argv = ["issue", "create", "--title", "T", "--body-file", "-", "--label", "area/k8s", "--field", "Priority=P1"]
    assert cli.main([*argv, "--dry-run"]) == 0
    assert "fields=Priority=P1,Area=k8s" in capsys.readouterr().out
    assert fake.calls == []
    monkeypatch.setattr("sys.stdin", io.StringIO("body"))
    created = []
    monkeypatch.setattr(GitHub, "create", lambda self, *a: created.append(a[-1]) or "5")
    assert cli.main(argv) == 0
    assert created == [{"Priority": "P1", "Area": "k8s"}]

    fake = board_gh("Backlog")
    monkeypatch.setattr(GitHub, "gh", fake)
    capsys.readouterr()
    assert cli.main(["issue", "set-field", "#5", "area=K8S", "Priority=p1"]) == 0
    assert capsys.readouterr().out == "#5 board Area k8s · Priority P1\n"
    assert field_sets(fake) == [("F2", "a-k8s"), ("F3", "p-1")]

    fake = board_gh(False)
    monkeypatch.setattr(GitHub, "gh", fake)
    assert cli.main(["issue", "set-field", "5", "Area=net"]) == 1
    assert "not on the board; run `aw issue set-status 5 backlog` first" in capsys.readouterr().err
    assert field_sets(fake) == []


def test_create_refuses_without_a_required_field(repo, monkeypatch, capsys):
    board_cfg(repo, 'board_fields = { "area/" = "Area" }\nboard_required = ["area", "Priority"]\n')
    fake = created_board()
    monkeypatch.setattr(GitHub, "gh", fake)
    monkeypatch.setattr(GitHub, "create", lambda *a: pytest.fail("created"))
    argv = ["issue", "create", "--title", "T", "--body-file", "-", "--label", "area/net"]
    for extra in (["--dry-run"], []):
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))
        assert cli.main([*argv, *extra]) == 1
        assert (
            "board_required: no value for Priority (P1, P2); pass --field Name=Option for each, nothing created"
            in capsys.readouterr().err
        )
    monkeypatch.setattr("sys.stdin", io.StringIO("body"))
    assert cli.main([*argv, "--field", "priority=P2", "--dry-run"]) == 0
    assert "fields=priority=P2,Area=net" in capsys.readouterr().out


def test_doctor_checks_board_required_fields(repo, monkeypatch):
    from aw import doctor

    board_cfg(repo, 'board_required = ["priority", "Team"]\n')
    monkeypatch.setattr(GitHub, "gh", board_gh())
    monkeypatch.setattr(doctor, "_gh_scopes", lambda: ["repo", "project"])
    results = doctor.check_board(load())
    assert ("ok", "board_required: field Priority") in results
    assert ("fail", "board_required: board has no single-select field 'Team' (fields: Area, Priority)") in results


def test_jira_refuses_fields_before_create(repo, monkeypatch, capsys):
    jira_cfg(repo)
    monkeypatch.setattr(Jira, "create", lambda *a, **k: pytest.fail("created"))
    monkeypatch.setattr("sys.stdin", io.StringIO("body"))
    assert cli.main(["issue", "create", "--title", "T", "--body-file", "-", "--field", "Area=net"]) == 1
    assert "--field: tracker 'jira' has no board fields" in capsys.readouterr().err


def test_doctor_checks_board_fields_against_labels(repo, monkeypatch):
    from aw import doctor

    board_cfg(repo, 'board_fields = { "area/" = "Area", "team/" = "Team" }\n')
    fake = board_gh()
    fake.issues["labels"] = [{"name": "area/net"}, {"name": "Area/DNS"}, {"name": "bug"}]
    monkeypatch.setattr(GitHub, "gh", fake)
    monkeypatch.setattr(doctor, "_gh_scopes", lambda: ["repo", "project"])
    results = doctor.check_board(load())
    assert ("fail", "board field Area has no option for label Area/DNS (options: net, k8s, home lab)") in results
    assert ("fail", "board_fields.team/: board has no single-select field 'Team' (fields: Area, Priority)") in results

    board_cfg(repo, 'board_fields = { "area/" = "Area" }\n')
    fake.issues["labels"] = [{"name": "area/net"}]
    assert ("ok", "board field Area for area/ labels (1)") in doctor.check_board(load())


def test_jira_create_moves_to_the_requested_status(repo, monkeypatch):
    fake = FakeJira({("POST", "/rest/api/3/issue"): {"key": "PROJ-20"}})
    tracker = Jira(jira_cfg(repo))
    monkeypatch.setattr(tracker, "request", fake)
    moves = []
    monkeypatch.setattr(Jira, "set_status", lambda self, i, s: moves.append((i, s)))
    assert tracker.create("T", "", None, None, status="ready") == "PROJ-20"
    assert tracker.create("T", "", None, None, status="none") == "PROJ-20"
    assert moves == [("PROJ-20", "ready")]

    def refuse(self, i, s):
        raise AwError("no transition to 'Ready'")

    monkeypatch.setattr(Jira, "set_status", refuse)
    with pytest.raises(AwError, match=r"created PROJ-20, but not moved to ready: .*aw issue set-status PROJ-20 ready"):
        tracker.create("T", "", None, None, status="ready")


# --- complete observations ------------------------------------------------------


def test_github_rollup_never_closes_when_the_sub_issue_lookup_fails(repo, monkeypatch):
    """A failed sub-issue request is not an empty list: the story's close is refused, its status unknown."""
    from aw import rollup

    github_cfg(repo)
    story = {"number": 4, "title": "Story", "state": "OPEN", "issueType": {"name": "Story"}}
    fake = FakeGh(graphql={"body issueType": gh_meta(story)}, issues={"4": gh_issue(4)})

    def gh(self, *args, stdin=None):
        if args[0] == "api" and "sub_issues" in args[-1]:
            raise AwError("gh api: HTTP 502 Bad Gateway")
        return fake(*args, stdin=stdin)

    monkeypatch.setattr(GitHub, "gh", gh)
    tracker = trackers.get(load())
    result = rollup.check(load(), tracker, "5")
    assert rollup.report(tracker, "5", result) == "#4: children unknown (gh api: HTTP 502 Bad Gateway)"
    with pytest.raises(AwError, match=r"children unknown .*; nothing closed"):
        rollup.close(load(), tracker, "5")


def test_github_sub_issues_are_read_from_every_page(repo, monkeypatch):
    github_cfg(repo)
    pages = [
        [{"number": n, "title": f"S{n}", "state": "CLOSED"} for n in range(10, 40)],
        [{"number": 41, "state": "OPEN"}],
    ]
    calls = []

    def gh(self, *args, stdin=None):
        calls.append(args)
        if args[0] == "api":
            return "".join(json.dumps(page) for page in pages)  # gh --paginate prints one array per page
        return json.dumps({"body": ""})

    monkeypatch.setattr(GitHub, "gh", gh)
    rows = trackers.get(load()).native_children("4")
    assert len(rows) == 31 and rows[-1].id == "41"
    assert "--paginate" in calls[0]


def test_github_sub_issues_unavailable_on_the_server_count_as_none(repo, monkeypatch):
    """HTTP 404 on the sub-issues endpoint: the server has no sub-issues for this issue, a complete answer."""
    github_cfg(repo)

    def gh(self, *args, stdin=None):
        raise AwError("gh api: Not Found (HTTP 404)")

    monkeypatch.setattr(GitHub, "gh", gh)
    assert trackers.get(load()).native_children("4") == []


def test_jira_rollup_reads_every_page_of_children(repo, monkeypatch):
    """100 closed children on the first page and an open one on the second: the story stays open."""
    from aw import rollup

    tracker = Jira(jira_cfg(repo))
    story = {"key": "PROJ-1", "fields": {"summary": "Story", "issuetype": {"name": "Story", "hierarchyLevel": 0}}}

    def child(key, category):
        return {"key": key, "fields": {"status": {"name": category, "statusCategory": {"key": category}}}}

    first = {"issues": [child(f"PROJ-{n}", "done") for n in range(100, 200)], "nextPageToken": "t2", "isLast": False}
    second = {"issues": [child("PROJ-300", "indeterminate"), child("PROJ-12", "indeterminate")], "isLast": True}

    def request(method, path, params=None, body=None):
        if path == "/rest/api/3/issue/PROJ-12":
            return {"fields": {"parent": story}}
        assert params
        return second if params.get("nextPageToken") == "t2" else first

    monkeypatch.setattr(tracker, "request", request)
    result = rollup.check(load(), tracker, "PROJ-12")
    assert rollup.report(tracker, "PROJ-12", result) == "PROJ-1 stays open: PROJ-300 open"


def test_hook_placeholders_arrive_as_one_argument_each(repo, tmp_path):
    (repo / ".agents").mkdir(exist_ok=True)
    (repo / ".agents/aw.toml").write_text(
        f"on_issue_status = \"printf '%s|' {{issue}} {{status_name}} > {tmp_path}/args\"\n"
        f'status_map = {{ in_progress = "In Progress; touch {tmp_path}/injected" }}\n'
    )
    trackers.status_hook(load(), "12", "in_progress")
    assert (tmp_path / "args").read_text() == f"12|In Progress; touch {tmp_path}/injected|"
    assert not (tmp_path / "injected").exists()


def test_github_parent_and_sub_issues_in_another_repository_are_never_this_ones(repo, monkeypatch):
    """Sub-issues may live in another repository: other/repo#1 is not this repository's #1."""
    from aw import rollup

    github_cfg(repo)
    parent = {"number": 1, "title": "Elsewhere", "state": "OPEN", "repository": {"nameWithOwner": "other/repo"}}
    api = "https://api.github.com/repos"
    subs = {
        "1": [
            {"number": 3, "title": "Mine", "state": "open", "repository_url": f"{api}/me/proj"},
            {"number": 3, "title": "Theirs", "state": "open", "repository_url": f"{api}/other/repo"},
        ]
    }
    monkeypatch.setattr(GitHub, "gh", FakeGh(graphql={"body issueType": gh_meta(parent)}, subs=subs))
    tracker = trackers.get(load())
    parent_row = tracker.parent("3")
    assert parent_row is not None and parent_row.id == "other/repo#1"
    assert rollup.story(tracker, "3") == (
        None,
        "other/repo#1 is in another repository; the rollup acts on this repository's stories only",
    )
    assert [row.id for row in tracker.native_children("1")] == ["3", "other/repo#3"]


def test_github_graphql_without_data_or_issue_is_an_aw_error(repo, monkeypatch):
    """Report paths turn an AwError into "unknown"; a KeyError would be a traceback instead."""
    github_cfg(repo)
    monkeypatch.setattr(GitHub, "gh", lambda self, *a, stdin=None: json.dumps({"errors": [{"message": "boom"}]}))
    with pytest.raises(AwError, match="boom"):
        trackers.get(load()).parent("3")
    missing = json.dumps({"data": {"repository": {"issue": None}}})
    monkeypatch.setattr(GitHub, "gh", lambda self, *a, stdin=None: missing)
    with pytest.raises(AwError, match="#3 not found"):
        trackers.get(load()).parent("3")
