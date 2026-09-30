from datetime import date

import pytest

from aw import start_task
from aw.config import AwError, git, load


@pytest.fixture
def configured(repo, tmp_path):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(
        'session_log = "SESSIONS.md"\n'
        f'worktree_root = "{tmp_path}/wt"\n'
        'on_issue_start = "echo hook-{issue} > hook.txt"\n'
    )
    return repo


def test_numbering_hook_and_output(configured, tmp_path):
    git("worktree", "add", "-q", "-b", "other", str(tmp_path / "wt/s15-parallel"), cwd=configured)
    out = start_task.run(load(), "fix", "pbs-auth", "#42")
    today = date.today().strftime("%Y%m%d")
    assert out == {
        "session": "16",
        "branch": f"fix/pbs-auth-{today}",
        "worktree": str(tmp_path / "wt/s16-pbs-auth"),
        "issue": "42",
    }
    assert (tmp_path / "wt/s16-pbs-auth/hook.txt").read_text() == "hook-42\n"


def test_from_inside_worktree(configured, tmp_path, monkeypatch):
    first = start_task.run(load(), "docs", "one", None)
    monkeypatch.chdir(first["worktree"])
    second = start_task.run(load(), "docs", "two", None)
    assert (first["session"], second["session"]) == ("13", "14")


@pytest.mark.parametrize("args, message", [
    (("wip", "x", None), "type 'wip'"),
    (("feat", "Bad_Slug", None), "kebab-case"),
    (("feat", "x", "abc"), "issue must be a number"),
])
def test_rejects_bad_input(configured, args, message):
    with pytest.raises(AwError, match=message):
        start_task.run(load(), *args)


def test_requires_main(configured):
    git("checkout", "-q", "-b", "elsewhere", cwd=configured)
    with pytest.raises(AwError, match="expected 'main'"):
        start_task.run(load(), "feat", "x", None)


def test_existing_branch(configured):
    today = date.today().strftime("%Y%m%d")
    git("branch", f"feat/x-{today}", cwd=configured)
    with pytest.raises(AwError, match="branch exists"):
        start_task.run(load(), "feat", "x", None)


def test_custom_name_pattern(repo, tmp_path):
    assert start_task._name_pattern("{project}-{n}-{slug}").match("proj-7-abc").group(1) == "7"
