from pathlib import Path

import pytest
from test_rollup import Board, story

from aw import finish, forge, session, start_task, trackers
from aw.config import AwError, git, load


@pytest.fixture
def board(repo, tmp_path, monkeypatch):
    """Story 1 with subtasks 2 (backlog) and 3; a session started on 2 moved 2 and its story to in progress."""
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(f'worktree_root = "{tmp_path}/wt"\nforge = "none"\n')
    git("add", ".", cwd=repo)
    git("commit", "-qm", "cfg", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    board = Board(load(), story("Backlog", **{"2": "Backlog", "3": "Backlog"}))
    monkeypatch.setattr(trackers, "get", lambda cfg: board)
    out = start_task.run(load(), "feat", "thing", "2")
    monkeypatch.chdir(out["worktree"])
    board.started = out
    return board


def test_an_empty_session_goes_away_and_its_issue_goes_back(board, repo):
    wt, branch = board.started["worktree"], board.started["branch"]
    log = finish.abandon(load(), session.read())
    assert board.moves[-1] == ("2", "backlog")
    assert board.issues["1"]["status"] == "In Progress"  # the story keeps its other work in progress
    assert not Path(wt).exists() and not git("branch", "--list", branch, cwd=repo)
    assert log[-2:] == [f"removed {wt}", f"deleted branch {branch}"]


def test_work_only_on_the_branch_is_never_dropped_silently(board, repo):
    wt = Path(board.started["worktree"])
    branch = board.started["branch"]
    (wt / "draft.txt").write_text("x\n")
    with pytest.raises(AwError, match="has uncommitted changes; pass --discard"):
        finish.abandon(load(), session.read())
    git("add", ".", cwd=wt)
    git("commit", "-qm", "wip", cwd=wt)
    git("push", "-q", "-u", "origin", branch, cwd=wt)
    with pytest.raises(AwError, match=r"has 1 commit\(s\) main lacks; pass --discard"):
        finish.abandon(load(), session.read())
    assert wt.exists() and board.moves[-1] == ("1", "in_progress")  # nothing touched

    finish.abandon(load(), session.read(), discard=True, status="ready")
    assert board.moves[-1] == ("2", "ready")
    assert not git("ls-remote", "--heads", "origin", branch, cwd=repo)
    assert not wt.exists()


def test_a_remote_branch_that_only_ends_alike_is_not_the_session_branch(board, repo):
    wt, branch = Path(board.started["worktree"]), board.started["branch"]
    git("push", "-q", "origin", f"HEAD:refs/heads/a/{branch}", cwd=wt)
    finish.abandon(load(), session.read())
    assert not wt.exists() and git("ls-remote", "origin", f"refs/heads/a/{branch}", cwd=repo)


@pytest.mark.parametrize("listing", ["open", "failed"])
def test_abandon_refuses_while_a_request_is_stacked_on_the_branch(board, repo, monkeypatch, listing):
    """Deleting the remote branch closes every request into it, and that work belongs to another session."""
    wt, branch = Path(board.started["worktree"]), board.started["branch"]
    git("push", "-q", "-u", "origin", branch, cwd=wt)
    monkeypatch.setenv("AW_FORGE", "github")
    monkeypatch.setattr(forge, "find_open", lambda kind, b, cwd: None)

    def stacked_on(kind, b, cwd):
        if listing == "failed":
            raise AwError("gh pr list: HTTP 502")
        return [forge.MergeRequest("9", "u")]

    monkeypatch.setattr(forge, "stacked_on", stacked_on)
    expected = "HTTP 502" if listing == "failed" else rf"#9 targets {branch}; .*deleting {branch} would close"
    with pytest.raises(AwError, match=expected):
        finish.abandon(load(), session.read(), discard=True)
    assert wt.exists() and git("ls-remote", "origin", f"refs/heads/{branch}", cwd=repo)


def test_an_issue_someone_moved_on_stays_where_it_is(board):
    board.issues["2"]["status"] = "In Review"
    moves = len(board.moves)
    log = finish.abandon(load(), session.read())
    assert "2 stays at In Review: only an issue in progress goes back" in log
    assert len(board.moves) == moves
