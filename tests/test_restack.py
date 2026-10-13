import subprocess

import pytest

from aw import forge, restack, session, start_task
from aw.config import git, load


def commit(cwd, name, text=None):
    (cwd / name).write_text(text or f"{name}\n")
    git("add", name, cwd=cwd)
    git("commit", "-qm", name, cwd=cwd)
    return git("rev-parse", "HEAD", cwd=cwd)


@pytest.fixture
def stacked(repo, tmp_path, monkeypatch):
    """Base feat/a pushed with one commit; a stacked session on it with one pushed commit of its own."""
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(f'worktree_root = "{tmp_path}/wt"\n')
    monkeypatch.setenv("AW_FORGE", "github")
    git("checkout", "-q", "-b", "feat/a", cwd=repo)
    commit(repo, "base.txt")
    git("push", "-q", "-u", "origin", "feat/a", cwd=repo)
    git("checkout", "-q", "main", cwd=repo)
    out = start_task.run(load(), "feat", "b", None, base="feat/a")
    wt = tmp_path / "wt/s1-b"
    commit(wt, "own.txt")
    git("push", "-q", "-u", "origin", out["branch"], cwd=wt)
    monkeypatch.chdir(wt)
    monkeypatch.setattr(forge, "merged", lambda kind, branch, cwd: [])
    monkeypatch.setattr(forge, "find_open", lambda kind, branch, cwd: None)
    return wt


def base_commit(repo, name, text=None):
    """A new commit on origin's feat/a, made from the primary checkout."""
    git("checkout", "-q", "feat/a", cwd=repo)
    tip = commit(repo, name, text)
    git("push", "-q", "origin", "feat/a", cwd=repo)
    git("checkout", "-q", "main", cwd=repo)
    return tip


def own_commits(wt, upstream):
    return git("log", "--format=%s", f"{upstream}..HEAD", cwd=wt).splitlines()


def test_restack_follows_new_base_commits(stacked, repo):
    tip = base_commit(repo, "more.txt")
    result = restack.run(load(), session.read())
    assert result.state == "restacked"
    assert own_commits(stacked, "origin/feat/a") == ["own.txt"]
    assert git("merge-base", "--is-ancestor", tip, "HEAD", cwd=stacked) == ""
    assert session.read()["fork_point"] == tip
    assert git("rev-parse", "HEAD", cwd=stacked) == git("rev-parse", "@{upstream}", cwd=stacked)


def merge_base_into_main(repo, method):
    """What the forge does when it merges feat/a's request into main."""
    git("checkout", "-q", "main", cwd=repo)
    git("fetch", "-q", "origin", cwd=repo)
    commit(repo, "elsewhere.txt")  # main moved on, so rebased commits get new ids
    if method == "merge":
        git("merge", "-q", "--no-ff", "-m", "merge feat/a", "origin/feat/a", cwd=repo)
    elif method == "squash":
        git("merge", "-q", "--squash", "origin/feat/a", cwd=repo)
        git("commit", "-qm", "feat/a squashed", cwd=repo)
    else:
        for sha in git("rev-list", "--reverse", "main..origin/feat/a", cwd=repo).splitlines():
            git("cherry-pick", sha, cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    if method != "merge":
        assert subprocess.run(
            ["git", "merge-base", "--is-ancestor", "origin/feat/a", "main"], cwd=repo, check=False
        ).returncode


@pytest.mark.parametrize("method", ["merge", "squash", "rebase"])
def test_restack_after_the_base_merged_lands_on_main_and_retargets(stacked, repo, monkeypatch, method):
    base_commit(repo, "more.txt")  # merged at a tip the stacked branch never saw
    merge_base_into_main(repo, method)
    branch = session.read()["branch"]
    monkeypatch.setattr(forge, "merged", lambda kind, b, cwd: [forge.MergeRequest("4", "u")] if b == "feat/a" else [])
    monkeypatch.setattr(forge, "find_open", lambda kind, b, cwd: forge.MergeRequest("9", "u") if b == branch else None)
    monkeypatch.setattr(forge, "target", lambda kind, ref, cwd: "feat/a")
    retargeted = []
    monkeypatch.setattr(forge, "retarget", lambda kind, ref, to, cwd: retargeted.append((ref, to)))

    result = restack.run(load(), session.read())

    assert result.state == "restacked" and result.base_merged
    assert own_commits(stacked, "origin/main") == ["own.txt"]
    assert retargeted == [("9", "main")]
    meta = session.read()
    assert meta["base"] == "" and meta["fork_point"] == git("rev-parse", "origin/main", cwd=stacked)


def test_restack_without_base_changes_does_nothing(stacked):
    head = git("rev-parse", "HEAD", cwd=stacked)
    assert restack.run(load(), session.read()).state == "up_to_date"
    assert git("rev-parse", "HEAD", cwd=stacked) == head


def test_restack_outside_a_stack(stacked):
    session.update(stacked, base="")
    assert restack.run(load(), session.read()).state == "not_stacked"


def test_conflict_leaves_the_rebase_and_a_rerun_finishes_it(stacked, repo):
    commit(stacked, "base.txt", "ours\n")
    git("push", "-q", "origin", "HEAD", cwd=stacked)
    tip = base_commit(repo, "base.txt", "theirs\n")

    result = restack.run(load(), session.read())
    assert result.state == "conflict" and result.conflicts == ["base.txt"]
    assert session.read()["restack_onto"] == tip
    with pytest.raises(Exception, match="rebase in progress"):
        restack.run(load(), session.read())

    (stacked / "base.txt").write_text("resolved\n")
    git("add", "base.txt", cwd=stacked)
    subprocess.run(
        ["git", "-c", "core.editor=true", "rebase", "--continue"], cwd=stacked, check=True, capture_output=True
    )
    result = restack.run(load(), session.read())
    assert result.state == "restacked"
    meta = session.read()
    assert meta["fork_point"] == tip and meta["restack_onto"] == ""
    assert git("rev-parse", "HEAD", cwd=stacked) == git("rev-parse", "@{upstream}", cwd=stacked)


def test_cli_reports_lines_a_summary_and_json(stacked, repo, capsys):
    import json

    from aw import cli

    base_commit(repo, "more.txt")
    head = git("rev-parse", "HEAD", cwd=stacked)
    assert cli.main(["restack", "--dry-run"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("DRY RUN") and git("rev-parse", "HEAD", cwd=stacked) == head

    assert cli.main(["restack"]) == 0
    out = capsys.readouterr().out.splitlines()
    branch = session.read()["branch"]
    assert out[-1] == f"restacked {branch}: 1 commit onto feat/a"
    assert len(out) <= 6

    assert cli.main(["restack", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["state"] == "up_to_date" and data["base"] == "feat/a" and "summary" in data


def test_cli_conflict_names_files_and_next_step(stacked, repo, capsys):
    from aw import cli

    commit(stacked, "base.txt", "ours\n")
    git("push", "-q", "origin", "HEAD", cwd=stacked)
    base_commit(repo, "base.txt", "theirs\n")
    assert cli.main(["restack"]) == 1
    out = capsys.readouterr().out
    assert "base.txt" in out and "git rebase --continue" in out and "aw restack" in out


def test_restack_refuses_a_fork_point_outside_the_branch(stacked, repo):
    session.update(stacked, fork_point=base_commit(repo, "more.txt"))
    with pytest.raises(Exception, match=r"fork point .* is not in"):
        restack.run(load(), session.read())
