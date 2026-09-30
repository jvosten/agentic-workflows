import tomllib

import pytest

from aw.config import AwError, dump_toml, load


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
    (repo / ".agents/aw.local.toml").write_text('direnv = false\n')
    monkeypatch.setenv("AW_BRANCH_TYPES", "feat, fix")

    cfg = load()
    assert (cfg.get("plan_dir"), cfg.sources["plan_dir"]) == ("user", "user")
    assert (cfg.get("verify_cmd"), cfg.sources["verify_cmd"]) == ("project", "project")
    assert (cfg.get("direnv"), cfg.sources["direnv"]) == (False, "local")
    assert (cfg.get("branch_types"), cfg.sources["branch_types"]) == (["feat", "fix"], "env")
    assert cfg.file_version == 1


def test_invalid_values(repo):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('tracker = "jira"\n')
    with pytest.raises(AwError, match="tracker: expected choice"):
        load()


def test_unknown_keys_reported(repo):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('bogus = "x"\n')
    assert load().unknown == [("project", "bogus")]


def test_dump_roundtrip():
    values = {"a": 'quote " and \\ back', "b": True, "c": ["x", "y"], "d": ""}
    assert tomllib.loads(dump_toml(values)) == values
