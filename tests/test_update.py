import subprocess
from pathlib import Path

import pytest

from aw import cli, update
from aw.config import AwError, git


def push_upstream(repo, tmp_path, name):
    """Someone else pushes a commit to the clone's origin."""
    other = tmp_path / "other"
    if not other.exists():
        git("clone", "-q", str(tmp_path / "origin.git"), str(other), cwd=tmp_path)
    git("pull", "-q", cwd=other)
    (other / name).write_text("x\n")
    git("add", ".", cwd=other)
    git("commit", "-qm", f"feat: {name}", cwd=other)
    git("push", "-q", "origin", "main", cwd=other)


def test_an_editable_clone_fast_forwards_its_default_branch(repo, tmp_path):
    before = git("rev-parse", "HEAD", cwd=repo)
    push_upstream(repo, tmp_path, "one.txt")
    push_upstream(repo, tmp_path, "two.txt")
    after = git("rev-parse", "origin/main", cwd=tmp_path / "other")
    log = update.update_clone(repo)
    assert log[0] == f"updated main in {repo}"
    assert log[1] == f"{before[:7]}..{after[:7]}: 2 commits"
    assert log[2:] == ["  feat: two.txt", "  feat: one.txt"]
    assert (repo / "two.txt").is_file()
    assert update.update_clone(repo) == ["main up to date"]


def test_a_clone_on_another_branch_moves_main_and_says_which_code_runs(repo, tmp_path):
    git("switch", "-q", "-c", "wip", cwd=repo)
    push_upstream(repo, tmp_path, "one.txt")
    log = update.update_clone(repo)
    assert log[0] == "updated main"
    assert log[-1] == f"warning: {repo} has wip checked out; the installed aw runs that, not main"
    assert not (repo / "one.txt").exists()


def test_a_diverged_clone_is_refused(repo, tmp_path):
    push_upstream(repo, tmp_path, "theirs.txt")
    (repo / "mine.txt").write_text("x\n")
    git("add", ".", cwd=repo)
    git("commit", "-qm", "mine", cwd=repo)
    with pytest.raises(AwError, match="diverged"):
        update.update_clone(repo)


def test_a_packaged_install_upgrades_with_uv(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs.get("timeout")))
        return subprocess.CompletedProcess(args, 0, "", "Updated agentic-workflows v0.1.12 -> v0.1.13\n")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    assert update.upgrade_tool() == ["Updated agentic-workflows v0.1.12 -> v0.1.13"]
    assert calls == [(["uv", "tool", "upgrade", "agentic-workflows"], update.UV_TIMEOUT)]


def test_a_failed_upgrade_is_an_error(monkeypatch):
    monkeypatch.setattr(
        update.subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 2, "", "error: no such tool\n")
    )
    with pytest.raises(AwError, match="uv tool upgrade agentic-workflows: error: no such tool"):
        update.upgrade_tool()


def test_update_relinks_and_checks_the_project_with_the_new_aw(repo, env, monkeypatch, capsys):
    calls = env / "calls.log"
    exe = env / ".agents/bin/aw"
    exe.parent.mkdir(parents=True)
    exe.write_text(f'#!/bin/sh\necho "$PWD $*" >> {calls}\n[ "$1" = init ] && exit 1\nexit 0\n')
    exe.chmod(0o755)
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text("aw_version = 1\n")
    monkeypatch.setattr(update, "update_code", lambda: ["main up to date"])
    assert cli.main(["update"]) == 0
    assert capsys.readouterr().out.splitlines()[:2] == ["aw update", "  main up to date"]
    assert calls.read_text().splitlines() == [f"{Path.cwd()} install --agent claude", f"{repo} init --check"]


def test_update_outside_a_project_only_relinks(env, tmp_path, monkeypatch):
    calls = env / "calls.log"
    exe = env / ".agents/bin/aw"
    exe.parent.mkdir(parents=True)
    exe.write_text(f'#!/bin/sh\necho "$*" >> {calls}\n')
    exe.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(update, "update_code", lambda: [])
    assert cli.main(["update"]) == 0
    assert calls.read_text().splitlines() == ["install --agent claude"]
