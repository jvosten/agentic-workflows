from pathlib import Path

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
    open_request = {"found": None}
    monkeypatch.setattr(forge, "find_open", lambda kind, branch, cwd: open_request["found"])
    cfg, meta = load(), session.read()
    with pytest.raises(AwError, match="no open merge request; open one with `aw mr create`, or pass --pr"):
        finish.run(cfg, meta, None)
    open_request["found"] = forge.MergeRequest("7", "https://x/pull/7")
    assert finish.run(cfg, meta, None)[0] == "merged #7"


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


# --- multi-merge sessions ----------------------------------------------------------


def commit(worktree, name, push=True):
    (worktree / name).write_text(f"{name}\n")
    git("add", ".", cwd=worktree)
    git("commit", "-qm", f"feat: {name}", cwd=worktree)
    if push:
        git("push", "-q", "-u", "origin", git("branch", "--show-current", cwd=worktree), cwd=worktree)


def test_merge_by_hand_keeps_the_session_going_until_finish(started, repo, tmp_path, monkeypatch):
    wt = Path(started["worktree"])
    monkeypatch.chdir(wt)
    hook_log = tmp_path / "merges.log"
    monkeypatch.setenv("AW_ON_MERGE", f"echo {{pr}}:{{final}}:{{slug}}:{{type}} >> {hook_log}")
    (wt / "BACKLOG.md").write_text("# Backlog\n\n## Later\n\nx\n")  # inbox noted mid-session
    monkeypatch.setenv("AW_TRACKER", "github")
    monkeypatch.setenv("AW_BACKLOG_HOME", "tracker")
    cfg = load()
    with pytest.raises(AwError, match="not merged"):
        finish.merge(cfg, session.read(), None)

    merge_by_hand(repo, started["branch"])
    log = finish.merge(cfg, session.read(), None)
    assert f"{started['branch']} is at main's tip; the session goes on" in log
    assert git("rev-parse", "HEAD", cwd=wt) == git("rev-parse", "origin/main", cwd=repo)
    assert (wt / "BACKLOG.md").is_file() and (repo / "new.txt").is_file()
    assert hook_log.read_text() == ":false:thing:feat\n"

    (wt / "BACKLOG.md").unlink()
    commit(wt, "second.txt")  # a fast-forward push: the branch descends from what it pushed before
    merge_by_hand(repo, started["branch"])
    finish.merge(cfg, session.read(), None)
    log = finish.run(cfg, session.read(), None)
    assert log[0] == f"nothing left to merge: {started['branch']} has no changes against main"
    assert str(wt) not in git("worktree", "list", cwd=repo)
    assert (repo / "second.txt").is_file()
    assert hook_log.read_text() == ":false:thing:feat\n" * 2  # nothing merged at finish, so no third run


def test_merge_refuses_commits_the_merge_request_does_not_contain(started, repo, monkeypatch):
    wt = started["worktree"]
    monkeypatch.chdir(wt)
    monkeypatch.setenv("AW_FORGE", "github")
    monkeypatch.setenv("AW_MERGE_METHOD", "squash")
    monkeypatch.setattr(forge, "find_open", lambda kind, branch, cwd: forge.MergeRequest("7", "u"))
    monkeypatch.setattr(forge, "is_merged", lambda kind, pr, cwd: True)
    monkeypatch.setattr(forge, "head", lambda kind, pr, cwd: "0" * 40)
    with pytest.raises(AwError, match=r"merged at another commit .* Push them into a new part first"):
        finish.merge(load(), session.read(), None)


def test_merge_after_a_squash_moves_the_branch_to_main_and_deletes_the_remote(started, repo, monkeypatch):
    wt, branch = started["worktree"], started["branch"]
    monkeypatch.chdir(wt)
    monkeypatch.setenv("AW_FORGE", "github")
    monkeypatch.setenv("AW_MERGE_METHOD", "squash")
    head = git("rev-parse", "HEAD", cwd=wt)

    def squash(kind, pr, method, cwd):
        git("merge", "-q", "--squash", branch, cwd=repo)
        git("commit", "-qm", "feat: thing (#7)", cwd=repo)
        git("push", "-q", "origin", "main", cwd=repo)
        git("reset", "-q", "--hard", "HEAD~1", cwd=repo)

    state = {"merged": False}
    monkeypatch.setattr(forge, "find_open", lambda kind, b, cwd: forge.MergeRequest("7", "u"))
    monkeypatch.setattr(forge, "merge", lambda *a: squash(*a) or state.update(merged=True))
    monkeypatch.setattr(forge, "is_merged", lambda kind, pr, cwd: state["merged"])
    monkeypatch.setattr(forge, "head", lambda kind, pr, cwd: head)
    log = finish.merge(load(), session.read(), None)
    assert log[0] == "merged #7"
    assert f"deleted origin/{branch}; the next `git push -u` recreates it" in log
    assert git("rev-parse", "HEAD", cwd=wt) == git("rev-parse", "origin/main", cwd=repo)
    assert not git("ls-remote", "--heads", "origin", branch, cwd=repo)


def test_start_task_warns_when_the_config_is_not_committed(repo, tmp_path, capsys):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(f'worktree_root = "{tmp_path}/wt"\n')
    start_task.run(load(), "feat", "uncommitted", None)
    assert "warning: .agents/aw.toml is not committed on main" in capsys.readouterr().err


def test_finish_runs_on_merge_after_a_pull_request_merged_outside_aw(started, repo, tmp_path, monkeypatch):
    wt, branch = Path(started["worktree"]), started["branch"]
    monkeypatch.chdir(wt)
    monkeypatch.setenv("AW_FORGE", "github")
    hook_log = tmp_path / "merges.log"
    monkeypatch.setenv("AW_ON_MERGE", f"echo {{pr}}:{{final}} >> {hook_log}")
    merge_by_hand(repo, branch)  # someone pressed merge on GitHub
    git("fetch", "-q", "origin", cwd=wt)
    git("merge", "-q", "--ff-only", "origin/main", cwd=wt)  # the branch has no changes left against main
    git("push", "-q", "origin", branch, cwd=wt)
    head = git("rev-parse", "HEAD", cwd=wt)
    monkeypatch.setattr(forge, "merged", lambda kind, b, cwd: [forge.MergeRequest("7", "u", head=head)])
    log = finish.run(load(), session.read(), None)
    assert log[0] == "#7 was merged outside aw"
    assert hook_log.read_text() == "7:true\n"


def test_finish_skips_on_merge_when_nothing_was_merged_since_the_last_part(started, repo, tmp_path, monkeypatch):
    wt, branch = Path(started["worktree"]), started["branch"]
    monkeypatch.chdir(wt)
    monkeypatch.setenv("AW_FORGE", "github")
    hook_log = tmp_path / "merges.log"
    monkeypatch.setenv("AW_ON_MERGE", f"echo {{pr}}:{{final}} >> {hook_log}")
    merge_by_hand(repo, branch)
    git("fetch", "-q", "origin", cwd=wt)
    git("merge", "-q", "--ff-only", "origin/main", cwd=wt)
    git("push", "-q", "origin", branch, cwd=wt)
    monkeypatch.setattr(forge, "merged", lambda kind, b, cwd: [forge.MergeRequest("6", "u", head="0" * 40)])
    log = finish.run(load(), session.read(), None)
    assert log[0] == f"nothing left to merge: {branch} has no changes against main"
    assert not hook_log.exists()


def test_finish_updates_main_while_the_primary_checkout_is_on_another_branch(started, repo, monkeypatch):
    monkeypatch.chdir(started["worktree"])
    merge_by_hand(repo, started["branch"])
    git("checkout", "-q", "-b", "look-around", cwd=repo)
    log = finish.run(load(), session.read(), None)
    assert "updated main" in log
    assert git("rev-parse", "main", cwd=repo) == git("rev-parse", "origin/main", cwd=repo)
    assert git("branch", "--show-current", cwd=repo) == "look-around"


def stack_on(started, monkeypatch):
    monkeypatch.setenv("AW_FORGE", "github")
    return start_task.run(load(), "feat", "next", None, base=started["branch"])


def test_merge_and_finish_refuse_in_a_stacked_session(started, monkeypatch):
    out = stack_on(started, monkeypatch)
    monkeypatch.chdir(out["worktree"])
    for end in (lambda: finish.merge(load(), session.read(), None), lambda: finish.run(load(), session.read(), None)):
        with pytest.raises(AwError, match=r"stacked on .*; run `aw restack`"):
            end()


def test_merge_warns_about_sessions_stacked_on_the_branch(started, repo, monkeypatch):
    out = stack_on(started, monkeypatch)
    monkeypatch.delenv("AW_FORGE")
    monkeypatch.chdir(started["worktree"])
    merge_by_hand(repo, started["branch"])
    log = finish.merge(load(), session.read(), None)
    assert f"warning: {out['branch']} is stacked on {started['branch']}; run `aw restack` in {out['worktree']}" in log
