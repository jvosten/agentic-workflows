import tomllib
from pathlib import Path

import pytest

from aw import start_task
from aw.config import AwError, dump_toml, git, load


def test_defaults_and_placeholders(repo):
    cfg = load()
    assert cfg.project == "proj"
    assert cfg.get("worktree_root") == f"{repo.parent}/proj.worktrees"
    assert cfg.sources["main_branch"] == "default"


def test_layers_and_env_override(repo, env, monkeypatch):
    (env / ".agents/aw").mkdir(parents=True)
    (env / ".agents/aw/config.toml").write_text('verify_cmd = "user"\nplan_dir = "user"\n')
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('aw_version = 1\nverify_cmd = "project"\ndirenv = true\n')
    (repo / ".agents/aw.local.toml").write_text("direnv = false\n")
    monkeypatch.setenv("AW_BRANCH_TYPES", "feat, fix")

    cfg = load()
    assert (cfg.get("plan_dir"), cfg.sources["plan_dir"]) == ("user", "user")
    assert (cfg.get("verify_cmd"), cfg.sources["verify_cmd"]) == ("project", "project")
    assert (cfg.get("direnv"), cfg.sources["direnv"]) == (False, "local")
    assert (cfg.get("branch_types"), cfg.sources["branch_types"]) == (["feat", "fix"], "env")
    assert cfg.file_version == 1


def test_invalid_values(repo):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('tracker = "bugzilla"\n')
    with pytest.raises(AwError, match="tracker: expected choice"):
        load()


def test_unknown_keys_reported(repo):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('bogus = "x"\n')
    assert load().unknown == [("project", "bogus")]


def test_dump_roundtrip():
    values = {"a": 'quote " and \\ back', "b": True, "c": ["x", "y"], "d": ""}
    assert tomllib.loads(dump_toml(values)) == values


def test_keys_that_run_on_the_host_come_from_the_primary_checkout_not_the_session(repo, tmp_path, monkeypatch):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(f'worktree_root = "{tmp_path}/wt"\nmerge_gate = "approve"\n')
    git("add", ".", cwd=repo)
    git("commit", "-qm", "cfg", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    wt = Path(start_task.run(load(), "feat", "thing", None)["worktree"])
    (wt / ".agents/aw.toml").write_text(
        f'worktree_root = "{tmp_path}/wt"\nmerge_gate = "auto"\non_merge = "touch marker"\nverify_cmd = "branch"\n'
    )
    monkeypatch.chdir(wt)
    cfg = load()
    assert (cfg.get("merge_gate"), cfg.get("on_merge")) == ("approve", "")
    assert cfg.get("verify_cmd") == "branch"  # not trusted: verifying runs the branch's own code anyway
    assert cfg.ignored == ["merge_gate", "on_merge"]
    assert (cfg.sources["merge_gate"], cfg.sources["verify_cmd"]) == ("primary", "project")
    monkeypatch.chdir(repo)
    assert load().ignored == []


# --- paths a committed config may name -----------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        'backlog_file = "~/.zshrc"',
        'backlog_file = "../../.zshrc"',
        'memory_dir = "/etc"',
        'plan_dir = "{repo_parent}/plans"',
        'instructions_file = "~/notes.md"',
        'templates = { mr = "~/private.txt" }',
    ],
)
def test_a_committed_path_outside_the_repo_is_refused(repo, line):
    """A branch's .agents/aw.toml must not point aw at a file outside the repo: reproduced 2026-10-24, aw template mr
    printed ~/private.txt and aw backlog add, then pop, wrote into and deleted ~/.zshrc."""
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(line + "\n")
    key = line.split(" ")[0]
    with pytest.raises(AwError, match=rf"{key}.* in project points outside the repo; .* user or local config"):
        load()


def test_a_path_outside_the_repo_is_fine_from_the_user_or_local_layer(repo, env, tmp_path):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.local.toml").write_text(f'templates = {{ mr = "{tmp_path}/shared/mr.md" }}\n')
    (env / ".agents/aw").mkdir(parents=True)
    (env / ".agents/aw/config.toml").write_text('plan_dir = "~/plans"\n')
    cfg = load()
    assert cfg.get("plan_dir") == f"{env}/plans"
    assert cfg.get("templates") == {"mr": f"{tmp_path}/shared/mr.md"}


def test_a_committed_symlink_out_of_the_repo_is_refused_where_aw_writes(repo, tmp_path, capsys):
    """The value stays in the repo, the file it names does not: aw follows no link out of the repo."""
    from aw import backlog, cli

    outside = tmp_path / "rc"
    outside.write_text("export PATH=x\n")
    (repo / "BACKLOG.md").symlink_to(outside)
    with pytest.raises(AwError, match=r"BACKLOG\.md resolves outside the repo"):
        backlog.add(load(), "x", "body\n")
    assert outside.read_text() == "export PATH=x\n"
    (repo / ".agents/memory").mkdir(parents=True)
    (repo / ".agents/memory/tags.toml").write_text('git = "git"\n')
    (repo / ".agents/memory/gotchas").symlink_to(tmp_path, target_is_directory=True)
    assert cli.main(["memory", "add", "gotcha", "--title", "T", "--tags", "git", "--body-file", "/dev/null"]) == 1
    assert "resolves outside the repo" in capsys.readouterr().err


def test_where_jira_credentials_go_is_the_primary_checkouts_choice(repo, tmp_path, monkeypatch):
    """A branch that sets jira_base_url would decide which host gets the Basic-auth header."""
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(
        f'worktree_root = "{tmp_path}/wt"\njira_base_url = "https://example.atlassian.net"\n'
    )
    git("add", ".", cwd=repo)
    git("commit", "-qm", "cfg", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    wt = Path(start_task.run(load(), "feat", "thing", None)["worktree"])
    (wt / ".agents/aw.toml").write_text(
        f'worktree_root = "{tmp_path}/wt"\njira_base_url = "https://collector.example"\n'
    )
    monkeypatch.chdir(wt)
    cfg = load()
    assert cfg.get("jira_base_url") == "https://example.atlassian.net"
    assert cfg.ignored == ["jira_base_url"]
