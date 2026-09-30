import tomllib

import pytest

from aw import init
from aw.config import AwError


def read(repo):
    return tomllib.loads((repo / ".agents/aw.toml").read_text())


def test_detects_defaults(repo):
    init.run(assume_yes=True, sets=[])
    data = read(repo)
    assert data == {
        "aw_version": 1,
        "main_branch": "main",
        "tracker": "none",  # local bare origin: neither github nor gitlab
        "instructions_file": "AGENTS.md",
        "session_log": "SESSIONS.md",
        "direnv": False,
        "verify_cmd": "make validate",
        "plan_dir": "",
    }
    assert (repo / ".agents/.gitignore").read_text() == "aw.local.toml\n"


def test_rerun_keeps_answers_and_set_overrides(repo):
    init.run(True, ["plan_dir=docs/plans", "on_issue_start=echo {issue}"])
    init.run(True, ["direnv=yes"])
    data = read(repo)
    assert data["plan_dir"] == "docs/plans"
    assert data["on_issue_start"] == "echo {issue}"
    assert data["direnv"] is True
    assert (repo / ".agents/.gitignore").read_text() == "aw.local.toml\n"


def test_tracker_detection(repo):
    from aw.config import git

    git("remote", "set-url", "origin", "git@github.com:someone/proj.git", cwd=repo)
    assert init.detect(repo, {"tracker": {"detect": "tracker"}}) == {"tracker": "github"}


def test_prompt_reasks_on_invalid(monkeypatch):
    answers = iter(["maybe", "y"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert init.prompt("direnv", {"type": "bool", "help": "h"}, False) is True


def test_bad_set(repo):
    with pytest.raises(AwError, match="known key"):
        init.run(True, ["nope=1"])


def test_detects_included_make_target_and_ignored_envrc(repo, tmp_path):
    from aw.config import git

    (repo / "Makefile").write_text("include mk/validate.mk\n")
    (repo / "mk").mkdir()
    (repo / "mk/validate.mk").write_text("check : lint\n")
    (repo / ".gitignore").write_text(".envrc\n")
    (repo / ".envrc").write_text("")
    git("add", ".", cwd=repo)
    git("commit", "-qm", "mk", cwd=repo)
    wt = tmp_path / "wt"
    git("worktree", "add", "-q", "--detach", str(wt), cwd=repo)
    schema = {"verify_cmd": {"detect": "verify_cmd"}, "direnv": {"detect": "direnv"}}
    assert init.detect(wt, schema) == {"verify_cmd": "make check", "direnv": True}
