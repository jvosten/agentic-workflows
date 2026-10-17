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
