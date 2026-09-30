import pytest

from aw import finish, forge, session, start_task
from aw.config import AwError, git, load


@pytest.fixture
def started(repo, tmp_path):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(f'worktree_root = "{tmp_path}/wt"\nverify_cmd = "test -f AGENTS.md"\n')
    git("add", ".", cwd=repo)
    git("commit", "-qm", "cfg", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    out = start_task.run(load(), "feat", "thing", None)
    wt = out["worktree"]
    (tmp_path / "wt/s1-thing/new.txt").write_text("x\n")
    git("add", ".", cwd=wt)
    git("commit", "-qm", "feat: thing", cwd=wt)
    git("push", "-q", "-u", "origin", out["branch"], cwd=wt)
    return out


def merge_by_hand(repo, branch):
    git("merge", "-q", "--no-ff", "-m", "merge", branch, cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    git("reset", "-q", "--hard", "HEAD~1", cwd=repo)  # primary lags behind origin, as after a forge merge


def test_verify_runs_in_checkout(started, monkeypatch):
    monkeypatch.chdir(started["worktree"])
    assert finish.verify(load()) == 0
    monkeypatch.setenv("AW_VERIFY_CMD", "false")
    assert finish.verify(load()) == 1


def test_finish_without_forge(started, repo, monkeypatch):
    monkeypatch.chdir(started["worktree"])
    cfg, meta = load(), session.read()
    with pytest.raises(AwError, match="not merged"):
        finish.run(cfg, meta, None)
    merge_by_hand(repo, started["branch"])
    log = finish.run(cfg, meta, None)
    assert f"deleted origin/{started['branch']}" in log
    assert not git("branch", "--list", started["branch"], cwd=repo)
    assert (repo / "new.txt").is_file()
    assert started["worktree"] not in git("worktree", "list", cwd=repo)


def test_finish_with_forge_merges_first(started, repo, monkeypatch):
    monkeypatch.chdir(started["worktree"])
    monkeypatch.setenv("AW_FORGE", "github")
    merged = {"state": False}

    def fake_merge(kind, pr, method, cwd):
        assert (kind, pr, method) == ("github", "7", "merge")
        merge_by_hand(repo, started["branch"])
        merged["state"] = True

    monkeypatch.setattr(forge, "merge", fake_merge)
    monkeypatch.setattr(forge, "is_merged", lambda kind, pr, cwd: merged["state"])
    cfg, meta = load(), session.read()
    with pytest.raises(AwError, match="--pr"):
        finish.run(cfg, meta, None)
    assert finish.run(cfg, meta, "7")[0] == "merged 7"


def test_finish_refuses_dirty_or_unpushed(started, monkeypatch):
    wt = started["worktree"]
    monkeypatch.chdir(wt)
    cfg, meta = load(), session.read()
    (cfg.checkout / "dirty.txt").write_text("x")
    with pytest.raises(AwError, match="uncommitted"):
        finish.run(cfg, meta, None)
    git("add", ".", cwd=wt)
    git("commit", "-qm", "more", cwd=wt)
    with pytest.raises(AwError, match="unpushed"):
        finish.run(cfg, meta, None)


def test_session_outside_worktree(repo):
    with pytest.raises(AwError, match="not in a session worktree"):
        session.read()
