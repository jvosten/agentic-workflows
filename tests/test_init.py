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
        "forge": "none",  # local bare origin: neither github nor gitlab
        "tracker": "none",
        "instructions_file": "AGENTS.md",
        "direnv": False,
        "verify_cmd": "make validate",
        "changelog_file": "CHANGELOG.md",
        "merge_method": "merge",
        "merge_gate": "approve",
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


def test_local_plans_are_gitignored(repo):
    init.run(True, ["plan_scope=local"])
    init.run(True, [])
    assert (repo / ".agents/.gitignore").read_text() == "aw.local.toml\nplans/\n"


def test_tracker_detection(repo):
    from aw.config import git

    git("remote", "set-url", "origin", "git@github.com:someone/proj.git", cwd=repo)
    assert init.detect(repo, {"tracker": {"detect": "forge"}}) == {"tracker": "github"}


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


def test_jira_keys_asked_only_for_jira(repo, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    asked = []

    def fake_input(prompt_text):
        key = prompt_text.rsplit("\n  ", 1)[-1].split(" [")[0]
        asked.append(key)
        return {"tracker": "jira", "jira_base_url": "https://x.atlassian.net", "jira_project": "PROJ"}.get(key, "")

    monkeypatch.setattr("builtins.input", fake_input)
    init.run(False, ["jira_fields=acceptance_criteria=customfield_1, story_points=customfield_2"])
    data = read(repo)
    assert asked.index("tracker") < asked.index("jira_base_url") < asked.index("jira_project")
    assert asked.index("tracker") < asked.index("backlog_home")
    assert "subtask_type" in asked
    assert (data["tracker"], data["jira_project"]) == ("jira", "PROJ")
    assert data["jira_fields"] == {"acceptance_criteria": "customfield_1", "story_points": "customfield_2"}

    asked.clear()
    monkeypatch.setattr("builtins.input", lambda p: asked.append(p) or ("none" if "tracker [" in p else ""))
    init.run(False, [])
    assert not any("jira_base_url" in p for p in asked)
    assert not any("backlog_home" in p for p in asked)


def test_init_reports_what_it_wrote(repo, capsys):
    from aw import cli

    assert cli.main(["init", "--yes"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "aw init"
    assert out[1].split()[:3] == [".agents/aw.toml", "created", "·"] and "detected" in out[1]
    assert out[-1].startswith("next: review and commit .agents/aw.toml")

    assert cli.main(["init", "--yes"]) == 0
    assert capsys.readouterr().out.splitlines()[1:] == ["  .agents/aw.toml     up to date"]

    assert cli.main(["init", "--yes", "--set", "verify_cmd=make test", "--set", "plan_scope=local"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[1].split() == [".agents/aw.toml", "updated", "·", "1", "changed,", "1", "new"]
    assert out[2].split() == ["verify_cmd", "make", "validate", "→", "make", "test"]
    assert out[3].split() == ["plan_scope", "local", "(new)"]
    assert out[4].split() == [".agents/.gitignore", "added", "plans/"]

    assert cli.main(["init", "--yes", "-v"]) == 0
    rows = {line.split()[0]: line.split()[1:] for line in capsys.readouterr().out.splitlines()[2:]}
    assert rows["verify_cmd"] == ["make", "test", "kept"]
    assert rows["changelog_file"] == ["CHANGELOG.md", "kept"]
