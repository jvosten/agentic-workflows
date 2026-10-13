import pytest

from aw import cli, finish, rollup, session, start_task, trackers
from aw.config import AwError, git, load
from aw.trackers import Row, Tracker


class Board(Tracker):
    """A tracker with states and native parent links, held in memory."""

    name = "board"

    def __init__(self, cfg, issues):
        super().__init__(cfg)
        self.issues = issues  # id -> {"status", "type", "parent", "link"}
        self.moves, self.comments = [], []
        self.started: dict[str, str] = {}  # the start-task output, set by fixtures that start a session

    def _row(self, issue):
        data = self.issues[issue]
        return Row(issue, f"T{issue}", data["status"], data.get("type", ""), link=data.get("link", "native"))

    def parent(self, issue):
        parent = self.issues[issue].get("parent")
        return (
            Row(
                parent,
                self.issues[parent].get("title", ""),
                type=self.issues[parent].get("type", ""),
                link=self.issues[issue].get("link", "native"),
            )
            if parent
            else None
        )

    def children(self, issue):
        return [self._row(i) for i, d in self.issues.items() if d.get("parent") == issue]

    def has_states(self):
        return True

    def current_status(self, issue):
        return self.issues[issue]["status"]

    def set_status(self, issue, status):
        self.moves.append((issue, status))
        self.issues[issue]["status"] = trackers.status_name(self.cfg, status)
        return f"{issue} -> {status}"

    def comment(self, issue, body):
        self.comments.append((issue, body))


def story(status="Backlog", **children):
    """Story 1 under epic 9, with children 2, 3, … in the given states."""
    issues = {"9": {"status": "", "type": "Epic"}, "1": {"status": status, "type": "Story", "parent": "9"}}
    issues |= {child: {"status": state, "type": "Task", "parent": "1"} for child, state in children.items()}
    return issues


@pytest.fixture
def cfg(repo):
    return load()


def test_session_start_moves_the_story_out_of_backlog_or_ready(cfg):
    for status, moved in (("Backlog", True), ("Ready", True), ("In Review", False), ("Done", False)):
        board = Board(cfg, story(status, **{"2": "Backlog"}))
        messages = rollup.start(board, "2")
        assert (("1", "in_progress") in board.moves) is moved, status
        if not moved:
            assert messages == [f"1 stays at {status}: a session start moves only from backlog or ready"]


def test_session_start_never_moves_an_epic(cfg):
    board = Board(cfg, story(**{"2": "Backlog"}))
    assert rollup.start(board, "1") == []  # a story started directly: its parent is the epic
    assert board.moves == []
    assert rollup.story(board, "1") == (None, "9 is an epic; epics close by decision, not by rollup")


def test_no_rollup_without_a_native_parent_or_without_states(cfg, monkeypatch):
    issues = story(**{"2": "Backlog"})
    issues["2"]["link"] = "text"
    board = Board(cfg, issues)
    assert rollup.start(board, "2") == [] and board.moves == []
    assert "parent by text only" in rollup.story(board, "2")[1]
    assert rollup.story(board, "9") == (None, "9 has no parent")

    board = Board(cfg, story(**{"2": "Backlog"}))
    monkeypatch.setattr(board, "has_states", lambda: False)
    assert rollup.start(board, "2") == [] and board.moves == []
    assert rollup.story(Tracker(cfg), "2") == (None, "none has no parent links")


def test_check_counts_the_finishing_subtask_as_closed(cfg):
    board = Board(cfg, story("In Progress", **{"2": "Done", "3": "In Progress"}))
    assert rollup.report(board, "3", rollup.check(cfg, board, "3")) == (
        "1 can close: no child open besides 3 (children: 2, 3)"
    )
    assert rollup.report(board, "2", rollup.check(cfg, board, "2")) == "1 stays open: 3 open"


def test_a_plan_section_without_a_subtask_keeps_the_story_open(cfg, repo):
    board = Board(cfg, story("In Progress", **{"2": "Done", "3": "In Progress"}))
    plans = repo / ".agents/plans/9-epic"
    plans.mkdir(parents=True)
    (plans / "1-story-2026-10-06.md").write_text(
        "# 1 Plan\n\n## Implementation sections\n\n### S1 — One\n\n**Subtask:** #2\n\n"
        "### S2 — Two\n\n**Subtask:** #3\n\n### S3 — Three\n\n**Subtask:** none yet\n\n"
        "### S4 — Four\n\n**Steps**\n\n1. x\n\n## Session order\n"
    )
    result = rollup.check(cfg, board, "3")
    assert isinstance(result, rollup.Blocked)
    assert result.left == ("plan section S3 has no subtask", "plan section S4 has no subtask")


def test_close_closes_the_story_with_a_comment_and_runs_the_hook(repo, tmp_path):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(f'on_issue_status = "echo {{issue}} {{status}} >> {tmp_path}/hook"\n')
    cfg = load()
    board = Board(cfg, story("In Progress", **{"2": "Done", "3": "Done"}))
    assert rollup.close(cfg, board, "3") == [
        "1 -> done",
        f"on_issue_status: echo 1 done >> {tmp_path}/hook",
        "commented on 1",
    ]
    assert board.comments == [("1", "All children are closed (2, 3); closed after 3.")]
    assert (tmp_path / "hook").read_text() == "1 done\n"


def test_close_refuses_while_a_child_is_open_and_never_closes_an_epic(cfg):
    board = Board(cfg, story("In Progress", **{"2": "In Progress", "3": "Done"}))
    with pytest.raises(AwError, match=r"^1 stays open: 2 open; nothing closed$"):
        rollup.close(cfg, board, "3")
    with pytest.raises(AwError, match="9 is an epic"):
        rollup.close(cfg, board, "1")
    assert board.moves == [] and board.comments == []


def test_cli_rollup_reports_and_closes(cfg, monkeypatch, capsys):
    board = Board(cfg, story("In Progress", **{"2": "Done", "3": "In Progress"}))
    monkeypatch.setattr(trackers, "get", lambda cfg: board)
    assert cli.main(["issue", "rollup", "3"]) == 0
    assert capsys.readouterr().out == "1 can close: no child open besides 3 (children: 2, 3)\n"
    assert board.moves == []
    assert cli.main(["issue", "rollup", "3", "--close"]) == 0
    assert board.moves == [("1", "done")]
    assert cli.main(["issue", "rollup", "2", "--close"]) == 1  # 3 is still open on the board
    assert "1 stays open: 3 open; nothing closed" in capsys.readouterr().err


def test_a_session_moves_the_story_and_finish_closes_it_on_request(repo, tmp_path, monkeypatch):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(f'worktree_root = "{tmp_path}/wt"\nforge = "none"\n')
    git("add", ".", cwd=repo)
    git("commit", "-qm", "cfg", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    board = Board(load(), story("Backlog", **{"2": "Backlog", "3": "Done"}))
    monkeypatch.setattr(trackers, "get", lambda cfg: board)

    out = start_task.run(load(), "feat", "thing", "2")
    assert board.moves == [("2", "in_progress"), ("1", "in_progress")]
    wt = out["worktree"]
    (tmp_path / "wt/s1-thing/f.txt").write_text("x")
    git("add", ".", cwd=wt)
    git("commit", "-qm", "feat: x", cwd=wt)
    git("push", "-q", "-u", "origin", out["branch"], cwd=wt)
    git("merge", "-q", "--no-ff", "-m", "m", out["branch"], cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    monkeypatch.chdir(wt)

    meta = session.read()
    with pytest.raises(AwError, match="--close-parent needs a session with an issue"):
        finish.run(load(), {**meta, "issue": ""}, None, close_parent=True)
    log = finish.run(load(), meta, None, close_parent=True)
    assert board.moves[2:] == [("2", "done"), ("1", "done")]
    assert "commented on 1" in log
    assert board.comments == [("1", "All children are closed (2, 3); closed after 2.")]
