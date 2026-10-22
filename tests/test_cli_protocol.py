"""The output skills read: pinned byte for byte.

Skills parse `key=value` lines, branch on fixed phrases and read rows by their markers (AGENTS.md: the CLI output is a
contract). A change here is a change to every skill that reads it: update the skills in the same change.
"""

import json
from datetime import date
from pathlib import Path

import pytest
from test_rollup import Board, story

from aw import cli, memory, trackers
from aw.config import AwError, git, load
from aw.trackers import Row


@pytest.fixture
def project(repo, tmp_path):
    """A committed project config, so session worktrees read it too."""
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(f'aw_version = 1\nworktree_root = "{tmp_path}/wt"\n')
    git("add", ".", cwd=repo)
    git("commit", "-qm", "cfg", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    return repo


def out(capsys, *argv: str) -> str:
    assert cli.main(list(argv)) == 0
    return capsys.readouterr().out


# start-task and session: key=value lines, read by aw-start-task and every skill that loads the session


def test_start_task_prints_branch_worktree_and_issue(project, tmp_path, capsys):
    stamp = date.today().strftime("%Y%m%d")
    assert out(capsys, "start-task", "feat", "thing") == (
        f"branch=feat/thing-{stamp}\nworktree={tmp_path}/wt/thing\nissue=\n"
    )
    assert out(capsys, "start-task", "fix", "other", "--issue", "7") == (
        f"branch=fix/other-{stamp}\nworktree={tmp_path}/wt/7-other\nissue=7\n"
    )


def test_session_prints_its_metadata_as_key_value_lines(project, tmp_path, monkeypatch, capsys):
    out(capsys, "start-task", "feat", "thing", "--issue", "7")
    today = date.today()
    monkeypatch.chdir(tmp_path / "wt/7-thing")
    assert out(capsys, "session") == (
        f"issue=7\ntype=feat\nslug=thing\nstarted={today.isoformat()}\n"
        f"branch=feat/thing-{today.strftime('%Y%m%d')}\nworktree={tmp_path}/wt/7-thing\n"
    )


# plan path and plan state: read by aw-plan, aw-plan-story, aw-start-task and aw-to-subtasks


def test_plan_path_prints_one_path_and_plan_state_key_value_lines(project, capsys):
    stamp = date.today().isoformat()
    assert out(capsys, "plan", "path", "12", "--slug", "thing") == f"{project}/.agents/plans/12-thing-{stamp}.md\n"
    assert out(capsys, "plan", "state", "12") == "issue=12\nplan=none\nsubtasks=\n"
    found = project / f".agents/plans/12-thing-{stamp}.md"
    found.parent.mkdir(parents=True)
    found.write_text("# plan\n")
    assert out(capsys, "plan", "path", "12") == f"{found}\n"
    assert out(capsys, "plan", "state", "12") == f"issue=12\nplan={found}\nsubtasks=\n"


# issue rows: read by aw-backlog-item, aw-plan-story and aw-to-subtasks ([text link], [elsewhere: …])


class Searchable(Board):
    def dupes(self, parent, terms, limit, tree_only=False):
        return [
            Row("2", "T2", "Done", "Task", scope="tree"),
            Row("5", "Five", "Backlog", parent="8", scope="elsewhere"),
            Row("6", "Six", scope="elsewhere"),
            Row("7", "Seven", scope="elsewhere"),
        ]


def test_issue_rows_mark_text_links_and_hits_elsewhere(project, monkeypatch, capsys):
    issues = story("In Progress", **{"2": "Done"}) | {"3": {"status": "", "type": "", "parent": "1", "link": "text"}}
    board = Searchable(load(), issues)
    monkeypatch.setattr(trackers, "get", lambda cfg: board)
    assert out(capsys, "issue", "children", "1") == "- [Done] 2 (Task) T2\n- 3 T3 [text link]\n"
    assert out(capsys, "issue", "children", "2") == "no issues\n"
    assert out(capsys, "issue", "dupes", "1", "--terms", "x", "--limit", "3") == (
        "- [Done] 2 (Task) T2\n"
        "- [Backlog] 5 Five [elsewhere: parent 8]\n"
        "- 6 Six [elsewhere: no parent]\n"
        "… 1 more elsewhere, matching fewer terms (--limit raises the cap)\n"
    )


# issue rollup: aw finish prints these lines; aw-finalize branches on the JSON `decision` (below)


def test_rollup_prints_one_of_four_lines(project, monkeypatch, capsys):
    cfg = load()
    board = Board(cfg, story("In Progress", **{"2": "Done", "3": "In Progress"}))
    monkeypatch.setattr(trackers, "get", lambda cfg: board)
    assert out(capsys, "issue", "rollup", "3") == "1 can close: no child open besides 3 (children: 2, 3)\n"
    assert out(capsys, "issue", "rollup", "2") == "1 stays open: 3 open\n"
    assert out(capsys, "issue", "rollup", "1") == "9 is an epic; epics close by decision, not by rollup\n"

    def unreadable(issue):
        raise AwError("sub-issues request failed")

    monkeypatch.setattr(board, "children", unreadable)
    assert out(capsys, "issue", "rollup", "3") == "1: children unknown (sub-issues request failed)\n"


def test_rollup_json_names_the_decision_aw_finalize_branches_on(project, monkeypatch, capsys):
    cfg = load()
    board = Board(cfg, story("In Progress", **{"2": "Done", "3": "In Progress"}))
    monkeypatch.setattr(trackers, "get", lambda cfg: board)

    def rollup_json(issue):
        return json.loads(out(capsys, "issue", "rollup", issue, "--json"))

    assert rollup_json("3") == {
        "decision": "can_close",
        "story": "1",
        "children": ["2", "3"],
        "open": [],
        "unsplit": [],
        "reason": None,
        "line": "1 can close: no child open besides 3 (children: 2, 3)",
    }
    assert rollup_json("2") == {
        "decision": "stays_open",
        "story": "1",
        "children": ["2", "3"],
        "open": ["3"],
        "unsplit": [],
        "reason": None,
        "line": "1 stays open: 3 open",
    }
    assert rollup_json("1") == {
        "decision": "no_story",
        "story": None,
        "children": None,
        "open": None,
        "unsplit": None,
        "reason": "9 is an epic; epics close by decision, not by rollup",
        "line": "9 is an epic; epics close by decision, not by rollup",
    }

    def unreadable(issue):
        raise AwError("sub-issues request failed")

    monkeypatch.setattr(board, "children", unreadable)
    assert rollup_json("3") == {  # a failed listing is never an empty one
        "decision": "unknown",
        "story": "1",
        "children": None,
        "open": None,
        "unsplit": None,
        "reason": "sub-issues request failed",
        "line": "1: children unknown (sub-issues request failed)",
    }

    def no_parent(issue):
        raise AwError("parent request failed")

    monkeypatch.setattr(board, "parent", no_parent)  # fails before check() can decide anything
    assert rollup_json("3") == {
        "decision": "unknown",
        "story": None,
        "children": None,
        "open": None,
        "unsplit": None,
        "reason": "parent request failed",
        "line": "3: parent story unknown (parent request failed)",
    }
    with pytest.raises(SystemExit) as refused:
        cli.main(["issue", "rollup", "3", "--json", "--close"])
    assert refused.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_rollup_json_names_unsplit_plan_sections_and_keeps_text_unescaped(project, monkeypatch, capsys):
    board = Board(load(), story("In Progress", **{"2": "Done", "3": "In Progress"}))
    monkeypatch.setattr(trackers, "get", lambda cfg: board)
    plans = project / ".agents/plans/9-epic"
    plans.mkdir(parents=True)
    (plans / "1-story-2026-10-06.md").write_text(
        "# 1 Plan\n\n## Implementation sections\n\n### S1 — Part one\n\n**Subtask:** #2\n\n"
        "### S2 — Part two\n\n**Steps**\n\n1. x\n\n## Session order\n"
    )
    assert json.loads(out(capsys, "issue", "rollup", "3", "--json"))["unsplit"] == ["S2"]

    def unreadable(issue):
        raise AwError("sub-issues — page 2 failed")

    monkeypatch.setattr(board, "children", unreadable)
    text = out(capsys, "issue", "rollup", "3", "--json")
    assert "1: children unknown (sub-issues — page 2 failed)" in text  # not escaped as \\u2014


# backlog list and memory find --compact: read by aw-finalize, aw-backlog-item and aw-remember


def test_backlog_list_prints_titles_or_no_items(project, capsys):
    assert out(capsys, "backlog", "list") == "no items\n"
    (project / "BACKLOG.md").write_text("# Backlog\n\n## Items\n\n### [LOW] One\n\nx\n\n### [HIGH] Two\n\ny\n")
    assert out(capsys, "backlog", "list") == "[LOW] One\n[HIGH] Two\n"


def test_memory_find_compact_prints_id_and_title(project, capsys):
    assert out(capsys, "memory", "find", "--compact") == "no entries\n"
    (project / ".agents/memory").mkdir()
    (project / ".agents/memory/tags.toml").write_text('git = "git"\n')
    memory.add(load(), "gotcha", "Git lies sometimes", "## Symptom\n\nx\n", ["git"], None)
    memory.add(load(), "decision", "Use worktrees", "x\n", [], None, intent=True)
    assert out(capsys, "memory", "find", "--compact") == (
        "- git-lies-sometimes · Git lies sometimes\n- use-worktrees · Use worktrees (intent: accepted, not built yet)\n"
    )


# Phrases skills branch on: each must stay in the code that prints it and in the skill that reads it


PHRASES = {
    # phrase in the output: (source file that prints it, skills that read it)
    "can_close": ("src/aw/rollup.py", ["aw-finalize"]),
    "no items": ("src/aw/cli.py", ["aw-finalize"]),
    "[text link]": ("src/aw/trackers/__init__.py", ["aw-backlog-item", "aw-to-subtasks"]),
    "[elsewhere: parent ": ("src/aw/trackers/__init__.py", ["aw-backlog-item"]),
    "[elsewhere: no parent]": ("src/aw/trackers/__init__.py", ["aw-backlog-item"]),
    "no checks yet": ("src/aw/cli.py", ["aw-checkpoint", "aw-finalize"]),
    "ignored from the branch: ": ("src/aw/finish.py", ["aw-checkpoint", "aw-finalize"]),
    "sandboxed: ": ("src/aw/config.py", ["aw-checkpoint", "aw-finalize"]),
    "the next request is ": ("src/aw/cli.py", ["aw-finalize"]),
    " opened, not ": ("src/aw/cli.py", ["aw-finalize"]),
    " does not close ": ("src/aw/cli.py", ["aw-merge-request"]),
    " also closes #": ("src/aw/cli.py", ["aw-merge-request"]),
}


@pytest.mark.parametrize("phrase", PHRASES)
def test_a_phrase_skills_branch_on_is_still_printed_and_still_read(phrase):
    root = Path(__file__).parents[1]
    source, readers = PHRASES[phrase]
    assert phrase in (root / source).read_text(), f"{source} no longer prints {phrase!r}"
    for skill in readers:
        text = (root / "skills" / skill / "SKILL.md").read_text()
        assert phrase.strip() in text, f"{skill} no longer reads {phrase!r}"
