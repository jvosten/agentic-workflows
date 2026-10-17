import tomllib
from pathlib import Path

import pytest

from aw import doctor, init, start_task
from aw.config import AwError, load


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
    assert (repo / ".agents/.gitignore").read_text() == "aw.local.toml\ngotchas-experiment.log\n"


def test_rerun_keeps_answers_and_set_overrides(repo):
    init.run(True, ["plan_dir=docs/plans", "on_start=echo {issue}"])
    init.run(True, ["direnv=yes"])
    data = read(repo)
    assert data["plan_dir"] == "docs/plans"
    assert data["on_start"] == "echo {issue}"
    assert data["direnv"] is True
    assert (repo / ".agents/.gitignore").read_text() == "aw.local.toml\ngotchas-experiment.log\n"


def test_local_plans_are_gitignored(repo):
    init.run(True, ["plan_scope=local"])
    init.run(True, [])
    assert (repo / ".agents/.gitignore").read_text() == "aw.local.toml\ngotchas-experiment.log\nplans/\n"


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


def test_a_migration_renames_rewrites_and_keeps_the_old_behaviour(repo, tmp_path):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(
        f'aw_version = 1\nworktree_root = "{tmp_path}/wt"\non_issue_start = "touch started"\n'
    )
    cfg = load()
    assert cfg.get("on_start") == "[ -n {issue} ] && touch started"
    assert cfg.migrated == [("project", "on_issue_start → on_start, run only with an issue as before")]
    assert cfg.unknown == []
    assert (
        "warn",
        "project: pending migration on_issue_start → on_start, run only with an issue as before; `aw init` applies it",
    ) in doctor.check_config(cfg)

    without = start_task.run(load(), "docs", "no-issue", None)
    assert not (Path(without["worktree"]) / "started").exists()  # the old hook ran only with an issue
    with_issue = start_task.run(load(), "docs", "with-issue", "7")
    assert (Path(with_issue["worktree"]) / "started").exists()

    report = init.run(True, [])
    assert "migrated on_issue_start → on_start, run only with an issue as before" in report.warnings
    data = read(repo)
    assert data["on_start"] == "[ -n {issue} ] && touch started" and "on_issue_start" not in data
    assert load().migrated == []


def test_quotes_around_placeholders_are_migrated_away(repo, tmp_path):
    """aw quotes placeholder values itself: quotes written around a placeholder would become part of the value."""
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(
        "aw_version = 1\n"
        "on_issue_status = 'sync.sh \"{status_name}\" {issue}'\n"
        "on_merge = \"deploy '{pr}'\"\n"
        "on_issue_start = 'touch \"{slug}\"'\n"
    )
    cfg = load()
    assert cfg.values["on_issue_status"] == "sync.sh {status_name} {issue}"
    assert cfg.values["on_merge"] == "deploy {pr}"
    assert cfg.values["on_start"] == "[ -n {issue} ] && touch {slug}"  # renamed first, then unquoted
    assert len(cfg.migrated) == 4
    assert cfg.command("on_issue_status", status_name="In Progress", issue="7") == "sync.sh 'In Progress' 7"

    init.run(True, [])
    data = read(repo)
    assert (data["on_issue_status"], data["on_merge"]) == ("sync.sh {status_name} {issue}", "deploy {pr}")
    assert load().migrated == []  # applied once, nothing pending


def test_doctor_flags_a_placeholder_inside_a_quoted_string(repo):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text("aw_version = 1\non_merge = 'notify \"merged {pr} into main\"'\n")
    warnings = [message for level, message in doctor.check_config(load()) if level == "warn"]
    assert any("on_merge: a placeholder inside quotes" in m for m in warnings)


def test_an_env_only_key_cannot_be_set_in_the_project_file(repo):
    with pytest.raises(AwError, match="environment only"):
        init.run(True, ["sandboxed=true"])
