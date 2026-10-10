from pathlib import Path

import pytest
from test_rollup import Board, story

from aw import finish, session, start_task, trackers
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


def test_an_issue_someone_moved_on_stays_where_it_is(board):
    board.issues["2"]["status"] = "In Review"
    moves = len(board.moves)
    log = finish.abandon(load(), session.read())
    assert "2 stays at In Review: only an issue in progress goes back" in log
    assert len(board.moves) == moves
