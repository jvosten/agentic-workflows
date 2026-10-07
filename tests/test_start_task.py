from datetime import date
from pathlib import Path

import pytest

from aw import session, start_task
from aw.config import AwError, git, load


@pytest.fixture
def configured(repo, tmp_path):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(
        f'worktree_root = "{tmp_path}/wt"\n'
        'on_start = "echo hook-{issue} > hook.txt"\n'
    )
    return repo


def test_numbering_hook_and_output(configured, tmp_path):
    (configured / ".git/aw-last-session").write_text("12\n")
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
    assert (configured / ".git/aw-last-session").read_text() == "16\n"
    meta = session.read(tmp_path / "wt/s16-pbs-auth")
    assert (meta["session"], meta["branch"], meta["issue"], meta["slug"]) == (16, out["branch"], "42", "pbs-auth")


def test_counter_survives_removed_worktrees(configured):
    first = start_task.run(load(), "docs", "one", None)
    assert (Path(first["worktree"]) / "hook.txt").read_text() == "hook-\n"  # on_start runs without an issue too
    git("worktree", "remove", "--force", first["worktree"], cwd=configured)
    assert start_task.run(load(), "docs", "two", None)["session"] == "2"


def test_number_override_never_lowers_counter(configured):
    assert start_task.run(load(), "docs", "one", None, number=79)["session"] == "79"
    assert start_task.run(load(), "docs", "two", None, number=5)["session"] == "5"
    assert (configured / ".git/aw-last-session").read_text() == "79\n"


def test_from_inside_worktree(configured, tmp_path, monkeypatch):
    first = start_task.run(load(), "docs", "one", None)
    monkeypatch.chdir(first["worktree"])
    second = start_task.run(load(), "docs", "two", None)
    assert (first["session"], second["session"]) == ("1", "2")


@pytest.mark.parametrize("args, message", [
    (("wip", "x", None), "type 'wip'"),
    (("feat", "Bad_Slug", None), "kebab-case"),
    (("feat", "x", "a b"), "invalid none issue id"),
])
def test_rejects_bad_input(configured, args, message):
    with pytest.raises(AwError, match=message):
        start_task.run(load(), *args)


def push_to_origin(tmp_path, name):
    """A commit on origin's main from another clone, which the local main does not have yet."""
    other = tmp_path / "other"
    if not other.exists():
        git("clone", "-q", str(tmp_path / "origin.git"), str(other), cwd=tmp_path)
    git("pull", "-q", cwd=other)
    (other / name).write_text(f"{name}\n")
    git("add", ".", cwd=other)
    git("commit", "-qm", name, cwd=other)
    git("push", "-q", "origin", "main", cwd=other)


def test_starts_while_the_primary_checkout_is_on_another_branch(configured, tmp_path):
    git("checkout", "-q", "-b", "look-around", cwd=configured)
    push_to_origin(tmp_path, "upstream.txt")
    out = start_task.run(load(), "feat", "x", None)
    assert (tmp_path / "wt/s1-x/upstream.txt").is_file()  # the session starts from origin's main
    assert git("branch", "--show-current", cwd=configured) == "look-around"
    assert git("rev-parse", "main", cwd=configured) == git("rev-parse", "origin/main", cwd=configured)
    assert out["branch"].startswith("feat/x-")


def test_main_checked_out_in_another_worktree_is_merged_there(configured, tmp_path):
    git("checkout", "-q", "-b", "look-around", cwd=configured)
    holder = tmp_path / "holder"
    git("worktree", "add", "-q", str(holder), "main", cwd=configured)
    push_to_origin(tmp_path, "upstream.txt")
    start_task.run(load(), "feat", "x", None)
    assert (holder / "upstream.txt").is_file()  # that checkout's files follow the moved branch
    assert git("status", "--porcelain", cwd=holder) == ""


def test_local_main_ahead_stays_and_a_diverged_main_fails(configured, tmp_path):
    (configured / "local.txt").write_text("x\n")
    git("add", "local.txt", cwd=configured)
    git("commit", "-qm", "local", cwd=configured)
    ahead = git("rev-parse", "main", cwd=configured)
    start_task.run(load(), "feat", "x", None)
    assert git("rev-parse", "main", cwd=configured) == ahead

    git("checkout", "-q", "-b", "look-around", cwd=configured)
    push_to_origin(tmp_path, "upstream.txt")
    with pytest.raises(AwError, match="main and origin/main have diverged"):
        start_task.run(load(), "feat", "y", None)
    assert git("rev-parse", "main", cwd=configured) == ahead


def test_existing_branch(configured):
    today = date.today().strftime("%Y%m%d")
    git("branch", f"feat/x-{today}", cwd=configured)
    with pytest.raises(AwError, match="branch exists"):
        start_task.run(load(), "feat", "x", None)


def test_custom_name_pattern(repo, tmp_path):
    assert start_task._name_pattern("{project}-{n}-{slug}").match("proj-7-abc").group(1) == "7"
