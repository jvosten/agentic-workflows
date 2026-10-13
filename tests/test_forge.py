import json
import subprocess

import pytest

from aw import cli, forge, session
from aw.config import AwError, git, load


def project(repo, text):
    (repo / ".agents").mkdir(exist_ok=True)
    (repo / ".agents/aw.toml").write_text(text)


# --- templates ------------------------------------------------------------------


def test_mr_template_comes_from_override_then_forge_then_bundle(repo, capsys):
    project(repo, 'forge = "gitlab"\n')
    assert cli.main(["template", "mr"]) == 0
    out = capsys.readouterr()
    assert "## Merge danger" in out.out and out.err == "template: bundled mr\n"

    templates_dir = repo / ".gitlab/merge_request_templates"
    templates_dir.mkdir(parents=True)
    (templates_dir / "default.md").write_text("## What does this MR do?\n")
    (templates_dir / "Bug.md").write_text("## Bug\n")
    assert cli.main(["template", "mr"]) == 0
    out = capsys.readouterr()
    assert (
        out.out == "## What does this MR do?\n" and out.err == "template: .gitlab/merge_request_templates/default.md\n"
    )

    project(repo, 'forge = "gitlab"\nmr_template = "bug"\n')
    assert cli.main(["template", "mr"]) == 0
    assert capsys.readouterr().out == "## Bug\n"

    project(repo, 'forge = "gitlab"\nmr_template = "Feature"\n')
    assert cli.main(["template", "mr"]) == 1
    err = capsys.readouterr().err
    assert "mr_template 'Feature'" in err and "(available: Bug, default)" in err

    (repo / "docs").mkdir()
    (repo / "docs/mr.md").write_text("ours\n")
    project(repo, 'forge = "gitlab"\nmr_template = "Feature"\ntemplates = { mr = "docs/mr.md" }\n')
    assert cli.main(["template", "mr"]) == 0
    assert capsys.readouterr().out == "ours\n"


def test_github_template_file_and_named_templates(repo, capsys):
    project(repo, 'forge = "github"\n')
    (repo / ".github/PULL_REQUEST_TEMPLATE").mkdir(parents=True)
    (repo / ".github/pull_request_template.md").write_text("## Why\n")
    (repo / ".github/PULL_REQUEST_TEMPLATE/release.md").write_text("## Release\n")
    assert cli.main(["template", "mr"]) == 0
    assert capsys.readouterr().out == "## Why\n"
    project(repo, 'forge = "github"\nmr_template = "release"\n')
    assert cli.main(["template", "mr"]) == 0
    assert capsys.readouterr().out == "## Release\n"


def test_doctor_reports_a_missing_named_template(repo):
    from aw import doctor

    project(repo, 'forge = "gitlab"\nmr_template = "Default"\n')
    results = doctor.check_config(load())
    assert ("fail", "mr_template 'Default': no .gitlab/merge_request_templates/Default.md (available: none)") in results


# --- aw mr create -------------------------------------------------------------------


@pytest.fixture
def branch(repo, monkeypatch):
    project(repo, 'forge = "github"\ntracker = "github"\n')
    git("checkout", "-qb", "feat/retries", cwd=repo)
    monkeypatch.setattr(forge, "merged", lambda kind, b, cwd: [])
    return repo


def test_create_appends_the_closing_line_and_refuses_unpushed_work(branch, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(session, "read", lambda: {"issue": "12"})
    body = tmp_path / "body.md"
    body.write_text("## Summary\n\nRetries.\n")
    assert cli.main(["mr", "create", "--title", "feat: retries", "--body-file", str(body), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("DRY RUN (github): feat/retries → main title='feat: retries' draft=False\n")
    assert out.endswith("Retries.\n\nFixes #12\n")

    body.write_text("Closes #12 already.\n")
    assert cli.main(["pr", "create", "--title", "t", "--body-file", str(body), "--dry-run"]) == 0
    assert "Fixes #12" not in capsys.readouterr().out

    assert cli.main(["mr", "create", "--title", "t", "--body-file", str(body)]) == 1
    assert "has no upstream; push it first: git push -u origin feat/retries" in capsys.readouterr().err


def test_create_never_opens_a_second_request(branch, tmp_path, monkeypatch, capsys):
    git("push", "-qu", "origin", "feat/retries", cwd=branch)
    body = tmp_path / "body.md"
    body.write_text("x\n")
    created = []
    monkeypatch.setattr(forge, "find_open", lambda kind, b, cwd: forge.MergeRequest("7", "https://x/pull/7"))
    monkeypatch.setattr(forge, "create", lambda *a: created.append(a))
    assert cli.main(["mr", "create", "--title", "t", "--body-file", str(body)]) == 0
    assert capsys.readouterr().out == "#7 already open: https://x/pull/7 (aw mr update changes it)\n"
    assert created == []

    monkeypatch.setattr(forge, "find_open", lambda kind, b, cwd: None)
    monkeypatch.setattr(
        forge, "create", lambda kind, b, base, title, text, draft, cwd: forge.MergeRequest("8", "https://x/pull/8")
    )
    assert cli.main(["mr", "create", "--title", "t", "--body-file", str(body)]) == 0
    assert capsys.readouterr().out == "#8 https://x/pull/8\n"


def test_create_in_a_stacked_session_targets_the_base(branch, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(session, "read", lambda: {"issue": "", "base": "feat/a"})
    body = tmp_path / "body.md"
    body.write_text("x\n")
    assert cli.main(["mr", "create", "--title", "t", "--body-file", str(body), "--dry-run"]) == 0
    assert capsys.readouterr().out.startswith("DRY RUN (github): feat/retries → feat/a ")

    git("push", "-qu", "origin", "feat/retries", cwd=branch)
    targets = []
    monkeypatch.setattr(forge, "find_open", lambda kind, b, cwd: None)
    monkeypatch.setattr(
        forge,
        "create",
        lambda kind, b, base, title, text, draft, cwd: targets.append(base) or forge.MergeRequest("9", "u"),
    )
    assert cli.main(["mr", "create", "--title", "t", "--body-file", str(body)]) == 0
    assert targets == ["feat/a"]


def test_mr_needs_a_forge(repo, capsys):
    project(repo, 'forge = "none"\n')
    assert cli.main(["mr", "view"]) == 1
    assert "forge = none: no merge requests" in capsys.readouterr().err


# --- GitHub, recorded responses ---------------------------------------------------------

REAL_RUN = subprocess.run


class FakeProcess:
    """Stands in for subprocess.run: canned results for gh and glab, keyed by the leading arguments.

    git runs for real.
    """

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(
        self, args, cwd=None, input=None, capture_output=False, text=False, check=False, stdout=None, stderr=None
    ):
        if args[0] not in ("gh", "glab"):
            return REAL_RUN(
                args,
                cwd=cwd,
                input=input,
                capture_output=capture_output,
                text=text,
                check=check,
                stdout=stdout,
                stderr=stderr,
            )
        self.calls.append(args)
        for prefix, (code, out, err) in self.answers.items():
            if tuple(args[: len(prefix)]) == prefix:
                return subprocess.CompletedProcess(args, code, out, err)
        raise AssertionError(f"unexpected call: {args}")


def test_github_checks_watch_quietly_and_sort_into_buckets(repo, monkeypatch, capsys):
    project(repo, 'forge = "github"\n')
    rows = [
        {"name": "test", "bucket": "pass"},
        {"name": "lint", "bucket": "fail"},
        {"name": "deploy", "bucket": "skipping"},
        {"name": "e2e", "bucket": "pending"},
    ]
    fake = FakeProcess(
        {
            ("gh", "pr", "checks", "5", "--watch"): (1, "lots of progress output", ""),
            ("gh", "pr", "checks", "5", "--json"): (1, json.dumps(rows), ""),
        }
    )
    monkeypatch.setattr(forge.subprocess, "run", fake)
    assert cli.main(["mr", "checks", "5", "--watch"]) == 1
    assert capsys.readouterr().out == (
        "1 passed · 1 failed: lint · 1 pending · 1 skipped\n  fail    lint\n  pending e2e\n"
    )
    assert fake.calls[0][:5] == ["gh", "pr", "checks", "5", "--watch"]

    fake.answers = {("gh", "pr", "checks"): (8, json.dumps(rows[3:]), "")}
    assert cli.main(["mr", "checks", "5"]) == 2
    fake.answers = {("gh", "pr", "checks"): (1, "", "no checks reported on the 'x' branch")}
    assert cli.main(["mr", "checks", "5"]) == 0
    assert capsys.readouterr().out.endswith("no checks\n")


def test_gh_reporting_no_checks_on_a_repo_with_workflows_is_not_green(repo, monkeypatch, capsys):
    project(repo, 'forge = "github"\n')
    (repo / ".github/workflows").mkdir(parents=True)
    (repo / ".github/workflows/ci.yml").write_text("on: pull_request\n")
    fake = FakeProcess({("gh", "pr", "checks"): (1, "", "no checks reported on the 'x' branch")})
    monkeypatch.setattr(forge.subprocess, "run", fake)
    assert cli.main(["mr", "checks", "5"]) == 2
    assert capsys.readouterr().out == "no checks yet: .github/workflows is configured, none reported\n"


@pytest.mark.parametrize("kind", ["github", "gitlab"])
def test_no_checks_yet_with_ci_configured_is_not_green(repo, monkeypatch, capsys, kind):
    """Right after a request opens, CI may not have reported its first check: that is no green light."""
    project(repo, f'forge = "{kind}"\n')
    ci = ".github/workflows" if kind == "github" else ".gitlab-ci.yml"
    if kind == "github":
        (repo / ci).mkdir(parents=True)
        (repo / ci / "ci.yml").write_text("on: pull_request\n")
    else:
        (repo / ci).write_text("test:\n  script: make check\n")
    answers = [[], [], [forge.Check("test", "pass")]]
    monkeypatch.setattr(forge, "_checks", lambda kind, ref, cwd, watch: answers.pop(0) if answers else [])
    sleeps = []
    monkeypatch.setattr(forge.time, "sleep", sleeps.append)

    assert cli.main(["mr", "checks", "5", "--watch"]) == 0
    assert capsys.readouterr().out == "1 passed\n"
    assert len(sleeps) == 2

    sleeps.clear()
    assert cli.main(["mr", "checks", "5", "--watch"]) == 2
    assert capsys.readouterr().out == f"no checks yet: {ci} is configured, none reported\n"
    assert len(sleeps) == forge.CHECKS_APPEAR

    sleeps.clear()
    assert cli.main(["mr", "checks", "5"]) == 2
    assert sleeps == []


def test_no_checks_without_ci_configured_is_final(repo, monkeypatch, capsys):
    project(repo, 'forge = "github"\n')
    monkeypatch.setattr(forge, "_checks", lambda kind, ref, cwd, watch: [])
    monkeypatch.setattr(forge.time, "sleep", lambda s: pytest.fail("no CI configured: nothing to wait for"))
    assert cli.main(["mr", "checks", "5", "--watch"]) == 0
    assert capsys.readouterr().out == "no checks\n"


def test_github_comments_and_view(repo, monkeypatch, capsys):
    project(repo, 'forge = "github"\n')
    threads = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "isResolved": False,
                                "path": "src/a.py",
                                "line": 12,
                                "comments": {
                                    "nodes": [
                                        {"author": {"login": "ann"}, "body": "Off by one?"},
                                        {"author": {"login": "bob"}, "body": "Fixed in 3f2a."},
                                    ]
                                },
                            },
                            {"isResolved": True, "path": "src/b.py", "line": 3, "comments": {"nodes": []}},
                        ]
                    },
                    "comments": {"nodes": [{"author": {"login": "ann"}, "body": "Looks good otherwise."}]},
                }
            }
        }
    }
    view = {
        "number": 5,
        "url": "https://x/pull/5",
        "title": "feat: retries",
        "state": "OPEN",
        "isDraft": False,
        "reviewDecision": "CHANGES_REQUESTED",
        "changedFiles": 3,
        "additions": 40,
        "deletions": 2,
        "mergeable": "MERGEABLE",
    }
    fake = FakeProcess(
        {
            ("gh", "api", "graphql"): (0, json.dumps(threads), ""),
            ("gh", "pr", "view"): (0, json.dumps(view), ""),
            ("gh", "pr", "checks"): (0, json.dumps([{"name": "test", "bucket": "pass"}]), ""),
        }
    )
    monkeypatch.setattr(forge.subprocess, "run", fake)
    assert cli.main(["mr", "comments", "5"]) == 0
    assert capsys.readouterr().out == (
        "1 unresolved thread · 1 resolved · 1 comment\n\nsrc/a.py:12\n  ann: Off by one?\n  bob: Fixed in 3f2a.\n"
        "\nComments\n  ann: Looks good otherwise.\n"
    )
    assert cli.main(["mr", "view", "5"]) == 0
    assert capsys.readouterr().out == (
        "#5 feat: retries\nhttps://x/pull/5\nstate    open · mergeable: mergeable\ncloses   nothing\n"
        "checks   1 passed\n"
        "review   changes requested · 1 unresolved thread\ndiff     3 files · +40 −2\n"
    )


# --- GitLab, from the API documentation ------------------------------------------------


def test_gitlab_discussions_split_into_threads_and_comments(repo, monkeypatch):
    discussions = [
        {"notes": [{"system": True, "body": "added 1 commit"}]},
        {"notes": [{"resolvable": False, "author": {"username": "ann"}, "body": "Thanks!"}]},
        {
            "notes": [
                {
                    "resolvable": True,
                    "resolved": False,
                    "author": {"username": "bob"},
                    "body": "Rename?",
                    "position": {"new_path": "app.py", "new_line": 4},
                }
            ]
        },
        {"notes": [{"resolvable": True, "resolved": True, "author": {"username": "bob"}, "body": "Typo"}]},
    ]
    fake = FakeProcess({("glab", "api"): (0, json.dumps(discussions), "")})
    monkeypatch.setattr(forge.subprocess, "run", fake)
    threads, general, resolved = forge.comments("gitlab", "9", repo)
    assert [(t.path, t.line, t.comments) for t in threads] == [("app.py", 4, [("bob", "Rename?")])]
    assert (general, resolved) == ([("ann", "Thanks!")], 1)
    assert fake.calls[0] == ["glab", "api", "--paginate", "projects/:id/merge_requests/9/discussions"]


def test_gitlab_checks_report_jobs_of_the_head_pipeline(repo, monkeypatch):
    mr = {"iid": 9, "head_pipeline": {"id": 77, "status": "failed"}}
    jobs = [{"name": "test", "status": "success"}, {"name": "lint", "status": "failed"}]
    fake = FakeProcess({("glab", "mr", "view"): (0, json.dumps(mr), ""), ("glab", "api"): (0, json.dumps(jobs), "")})
    monkeypatch.setattr(forge.subprocess, "run", fake)
    assert [(c.name, c.bucket) for c in forge.checks("gitlab", "9", repo)] == [("test", "pass"), ("lint", "fail")]
    with pytest.raises(AwError, match="no merge requests"):
        forge.checks("none", "9", repo)


def test_parts_reference_the_issue_without_closing_it(branch, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(session, "read", lambda: {"issue": "12"})
    monkeypatch.setattr(
        forge, "merged", lambda kind, b, cwd: [forge.MergeRequest("314", "u"), forge.MergeRequest("315", "u")]
    )
    body = tmp_path / "body.md"
    body.write_text("## Summary\n\nPart three.\n")
    assert cli.main(["mr", "create", "--title", "t", "--body-file", str(body), "--part", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "part=3" in out.splitlines()[0]
    assert out.endswith("Part three.\n\nRefs #12 (part 3)\n") and "Fixes" not in out

    assert cli.main(["mr", "create", "--title", "t", "--body-file", str(body), "--dry-run"]) == 0
    assert capsys.readouterr().out.endswith("Part three.\n\nFixes #12\nEarlier parts: #314, #315\n")


@pytest.mark.parametrize(
    ("kind", "view", "answer", "edit"),
    [
        ("github", ("gh", "pr", "view", "5"), {"baseRefName": "feat/a"}, ["gh", "pr", "edit", "5", "--base", "main"]),
        (
            "gitlab",
            ("glab", "mr", "view", "5"),
            {"target_branch": "feat/a"},
            ["glab", "mr", "update", "5", "--target-branch", "main"],
        ),
    ],
)
def test_target_and_retarget(repo, monkeypatch, kind, view, answer, edit):
    fake = FakeProcess({view: (0, json.dumps(answer), ""), tuple(edit[:3]): (0, "", "")})
    monkeypatch.setattr(forge.subprocess, "run", fake)
    assert forge.target(kind, "5", repo) == "feat/a"
    forge.retarget(kind, "5", "main", repo)
    assert fake.calls[-1] == edit


def page(threads, has_next):
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {"pageInfo": {"hasNextPage": has_next, "endCursor": "c"}, "nodes": threads},
                    "comments": {"nodes": [{"author": {"login": "ann"}, "body": "general"}]},
                }
            }
        }
    }


def test_github_review_threads_are_read_from_every_page(repo, monkeypatch):
    """An unresolved thread on the second page of review threads still stops the merge gate."""
    resolved = [{"isResolved": True, "path": "a.py", "line": n, "comments": {"nodes": []}} for n in range(100)]
    late = {"isResolved": False, "path": "z.py", "line": 1, "comments": {"nodes": [{"body": "Still wrong"}]}}
    pages = json.dumps(page(resolved, True)) + json.dumps(page([late], False))  # gh --paginate: one object per page
    fake = FakeProcess({("gh", "api", "graphql"): (0, pages, "")})
    monkeypatch.setattr(forge.subprocess, "run", fake)
    threads, general, resolved_count = forge.comments("github", "5", repo)
    assert [(t.path, t.comments) for t in threads] == [("z.py", [("?", "Still wrong")])]
    assert (general, resolved_count) == ([("ann", "general")], 100)
    assert "--paginate" in fake.calls[0]


def test_gitlab_jobs_and_discussions_are_read_from_every_page(repo, monkeypatch):
    """A failing job on the second page of jobs makes the checks fail."""
    mr = {"iid": 9, "head_pipeline": {"id": 77, "status": "running"}}
    jobs = json.dumps([{"name": f"job{n}", "status": "success"} for n in range(20)])
    jobs += json.dumps([{"name": "late", "status": "failed"}])
    fake = FakeProcess({("glab", "mr", "view"): (0, json.dumps(mr), ""), ("glab", "api"): (0, jobs, "")})
    monkeypatch.setattr(forge.subprocess, "run", fake)
    checks = forge.checks("gitlab", "9", repo)
    assert len(checks) == 21 and ("late", "fail") in [(c.name, c.bucket) for c in checks]
    assert fake.calls[-1][:3] == ["glab", "api", "--paginate"]


# --- what a request closes -------------------------------------------------------------


def test_the_closing_line_needs_a_closing_phrase_for_exactly_this_issue(branch, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(session, "read", lambda: {"issue": "12"})
    body = tmp_path / "body.md"
    for text, appended in (
        ("Follow-up to #123.\n", True),  # #12 is not #123
        ("See #12 for the background.\n", True),  # a mention closes nothing
        ("Closes #12 already.\n", False),
        ("fixed: #12\n", False),
    ):
        body.write_text(text)
        assert cli.main(["mr", "create", "--title", "t", "--body-file", str(body), "--dry-run"]) == 0
        assert capsys.readouterr().out.endswith("\nFixes #12\n") is appended, text


def test_update_keeps_the_closing_line_or_the_part_reference(branch, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(session, "read", lambda: {"issue": "12"})
    sent = []
    monkeypatch.setattr(forge, "update", lambda kind, ref, title, text, cwd: sent.append(text))
    monkeypatch.setattr(forge, "closes", lambda kind, ref, cwd: ["12"])
    body = tmp_path / "body.md"
    body.write_text("## Summary\n\nRewritten.\n")
    monkeypatch.setattr(forge, "body", lambda kind, ref, cwd: "Old.\n\nFixes #12\n")
    assert cli.main(["mr", "update", "--body-file", str(body)]) == 0
    assert sent[-1].endswith("Rewritten.\n\nFixes #12\n")

    monkeypatch.setattr(forge, "body", lambda kind, ref, cwd: "Old.\n\nRefs #12 (part 2)\n")
    monkeypatch.setattr(forge, "closes", lambda kind, ref, cwd: [])
    assert cli.main(["mr", "update", "--body-file", str(body)]) == 0
    assert sent[-1].endswith("Rewritten.\n\nRefs #12 (part 2)\n") and "Fixes" not in sent[-1]


def test_create_and_update_check_what_the_request_closes(branch, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(session, "read", lambda: {"issue": "12"})
    git("push", "-qu", "origin", "feat/retries", cwd=branch)
    monkeypatch.setattr(forge, "find_open", lambda kind, b, cwd: None)
    monkeypatch.setattr(forge, "create", lambda *a: forge.MergeRequest("8", "https://x/pull/8"))
    body = tmp_path / "body.md"
    body.write_text("Closed: #162, with a comment.\n")
    closes = {"now": ["12", "162"]}
    monkeypatch.setattr(forge, "closes", lambda kind, ref, cwd: closes["now"])
    assert cli.main(["mr", "create", "--title", "t", "--body-file", str(body)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("#8 https://x/pull/8\n")
    assert "warning: #8 also closes #162; reword the phrase that names it" in captured.err

    closes["now"] = ["162"]
    monkeypatch.setattr(forge, "body", lambda kind, ref, cwd: "Old.\n")
    monkeypatch.setattr(forge, "update", lambda *a: None)
    assert cli.main(["mr", "update", "8", "--body-file", str(body)]) == 1
    assert "8 does not close #12" in capsys.readouterr().err


def test_view_shows_what_the_request_closes(repo, monkeypatch, capsys):
    project(repo, 'forge = "github"\n')
    view = {
        "number": 5,
        "url": "https://x/pull/5",
        "title": "fix: retries",
        "state": "OPEN",
        "isDraft": False,
        "reviewDecision": "",
        "changedFiles": 1,
        "additions": 1,
        "deletions": 0,
        "mergeable": "MERGEABLE",
        "closingIssuesReferences": [{"number": 12}, {"number": 162}],
    }
    empty = {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": []}, "comments": {"nodes": []}}}}}
    fake = FakeProcess(
        {
            ("gh", "api", "graphql"): (0, json.dumps(empty), ""),
            ("gh", "pr", "view"): (0, json.dumps(view), ""),
            ("gh", "pr", "checks"): (0, "[]", ""),
        }
    )
    monkeypatch.setattr(forge.subprocess, "run", fake)
    assert cli.main(["mr", "view", "5"]) == 0
    assert "\ncloses   #12, #162\n" in capsys.readouterr().out


def test_a_missing_forge_tool_is_an_aw_error(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))
    for call in (
        lambda: forge.is_merged("github", "1", repo),
        lambda: forge.checks("github", "1", repo),
        lambda: forge.create("github", "b", "main", "t", "body", False, repo),
        lambda: forge.update("github", "1", "t", "body", repo),
    ):
        with pytest.raises(AwError, match="gh not found"):
            call()
