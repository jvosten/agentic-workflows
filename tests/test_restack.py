import json
import subprocess
from pathlib import Path

import pytest

from aw import cli, forge, restack, session, start_task
from aw.config import AwError, git, load


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
    wt = tmp_path / "wt/b"
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
    head, meta = git("rev-parse", "HEAD", cwd=stacked), session.read()
    assert restack.run(load(), session.read()).state == "up_to_date"
    assert git("rev-parse", "HEAD", cwd=stacked) == head and session.read() == meta


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
@pytest.mark.parametrize("cleanup", [False, True])
def test_restack_after_the_base_merged_lands_on_main_and_retargets(stacked, repo, monkeypatch, method, cleanup):
    base_commit(repo, "more.txt")  # merged at a tip the stacked branch never saw
    merge_base_into_main(repo, method)
    if cleanup:
        _remove_base(repo)
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


def _remove_base(repo: Path) -> None:
    worktree = repo.parent / "base-worktree"
    git("worktree", "add", "-q", str(worktree), "feat/a", cwd=repo)
    git("worktree", "remove", str(worktree), cwd=repo)
    git("branch", "-D", "feat/a", cwd=repo)
    git("push", "-q", "origin", "--delete", "feat/a", cwd=repo)


@pytest.mark.parametrize("method", ["merge", "squash", "rebase"])
def test_restack_after_manual_rebase(stacked: Path, repo: Path, monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    merge_base_into_main(repo, method)
    _remove_base(repo)
    monkeypatch.setattr(forge, "merged", lambda kind, branch, cwd: [forge.MergeRequest("4", "u")])
    git("fetch", "-q", "origin", "main", cwd=stacked)
    onto = git("rev-parse", "origin/main", cwd=stacked)
    fork_point = session.read()["fork_point"]
    session.update(stacked, restack_onto=onto)
    git("rebase", "--quiet", "--onto", onto, fork_point, cwd=stacked)
    head = git("rev-parse", "HEAD", cwd=stacked)

    result = restack.run(load(), session.read())

    assert result.state == "restacked" and result.commits == 1
    assert own_commits(stacked, "origin/main") == ["own.txt"]
    meta = session.read()
    assert meta["fork_point"] == onto and meta["base"] == "" and meta["restack_onto"] == ""
    assert git("rev-parse", "HEAD", cwd=stacked) == head
    assert git("rev-parse", "@{upstream}", cwd=stacked) == head
    assert restack.run(load(), session.read()).state == "not_stacked"
    assert session.read() == meta
    assert git("rev-parse", "HEAD", cwd=stacked) == head


@pytest.mark.parametrize("method", ["merge", "squash", "rebase"])
def test_recover_after_merged_conflict(stacked: Path, repo: Path, monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    base_commit(repo, "own.txt", "theirs\n")
    merge_base_into_main(repo, method)
    _remove_base(repo)
    monkeypatch.setattr(forge, "merged", lambda kind, branch, cwd: [forge.MergeRequest("4", "u")])
    assert restack.run(load(), session.read()).state == "conflict"
    meta = session.read()
    with pytest.raises(AwError, match="rebase in progress"):
        restack.run(load(), meta)
    assert session.read() == meta

    (stacked / "own.txt").write_text("resolved\n", encoding="utf-8")
    git("add", "own.txt", cwd=stacked)
    git("-c", "core.editor=true", "rebase", "--continue", cwd=stacked)
    head = git("rev-parse", "HEAD", cwd=stacked)
    result = restack.run(load(), session.read())

    assert result.state == "restacked" and result.commits == 1
    assert own_commits(stacked, "origin/main") == ["own.txt"]
    assert git("rev-parse", "HEAD", cwd=stacked) == head
    assert git("rev-parse", "@{upstream}", cwd=stacked) == head
    meta = session.read()
    assert meta["base"] == "" and meta["restack_onto"] == ""
    assert meta["fork_point"] == git("rev-parse", "origin/main", cwd=stacked)


@pytest.mark.parametrize("method", ["merge", "squash", "rebase"])
def test_base_merges_during_restack(stacked: Path, repo: Path, monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    base_commit(repo, "own.txt", "theirs\n")
    assert restack.run(load(), session.read()).state == "conflict"
    merge_base_into_main(repo, method)
    _remove_base(repo)
    monkeypatch.setattr(forge, "merged", lambda kind, branch, cwd: [forge.MergeRequest("4", "u")])
    (stacked / "own.txt").write_text("resolved\n", encoding="utf-8")
    git("add", "own.txt", cwd=stacked)
    git("-c", "core.editor=true", "rebase", "--continue", cwd=stacked)
    before, head = session.read(), git("rev-parse", "HEAD", cwd=stacked)
    remote = git("rev-parse", "@{upstream}", cwd=stacked)
    preview = restack.run(load(), before, dry_run=True)
    assert preview.commits == 1 and preview.log[0].startswith("DRY RUN: git rebase --onto origin/main ")
    assert session.read() == before and git("rev-parse", "HEAD", cwd=stacked) == head
    assert git("rev-parse", "@{upstream}", cwd=stacked) == remote

    result = restack.run(load(), session.read())

    assert result.state == "restacked" and result.commits == 1 and result.base_merged
    assert git("merge-base", "--is-ancestor", "origin/main", "HEAD", cwd=stacked) == ""
    assert own_commits(stacked, "origin/main") == ["own.txt"]
    assert git("rev-parse", "HEAD", cwd=stacked) == git("rev-parse", "@{upstream}", cwd=stacked)
    meta = session.read()
    assert meta["base"] == "" and meta["restack_onto"] == ""
    assert meta["fork_point"] == git("rev-parse", "origin/main", cwd=stacked)


def test_recovered_rebase_can_abort(stacked: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    git("checkout", "-q", "feat/a", cwd=repo)
    git("reset", "--hard", "main", cwd=repo)
    commit(repo, "base.txt", "new base\n")
    onto = commit(repo, "own.txt", "theirs\n")
    git("push", "-q", "--force", "origin", "feat/a", cwd=repo)
    git("checkout", "-q", "main", cwd=repo)
    assert restack.run(load(), session.read()).state == "conflict"
    (stacked / "own.txt").write_text("resolved\n", encoding="utf-8")
    git("add", "own.txt", cwd=stacked)
    git("-c", "core.editor=true", "rebase", "--continue", cwd=stacked)
    head = git("rev-parse", "HEAD", cwd=stacked)
    merge_base_into_main(repo, "squash")
    commit(repo, "own.txt", "main changed\n")
    git("push", "-q", "origin", "main", cwd=repo)
    _remove_base(repo)
    monkeypatch.setattr(forge, "merged", lambda kind, branch, cwd: [forge.MergeRequest("4", "u")])

    assert restack.run(load(), session.read()).state == "conflict"
    assert session.read()["fork_point"] == onto
    git("rebase", "--abort", cwd=stacked)
    assert git("rev-parse", "HEAD", cwd=stacked) == head
    assert restack.run(load(), session.read()).state == "conflict"
    assert session.read()["base"] == "feat/a" and session.read()["fork_point"] == onto


@pytest.mark.parametrize("merged", [False, True])
def test_recovery_preview_preserves_state(
    stacked: Path, repo: Path, monkeypatch: pytest.MonkeyPatch, merged: bool
) -> None:
    onto = base_commit(repo, "more.txt")
    if merged:
        merge_base_into_main(repo, "squash")
        _remove_base(repo)
        git("fetch", "-q", "origin", "main", cwd=stacked)
        onto = git("rev-parse", "origin/main", cwd=stacked)
        monkeypatch.setattr(forge, "merged", lambda kind, branch, cwd: [forge.MergeRequest("4", "u")])
    meta = session.read()
    branch = meta["branch"]
    monkeypatch.setattr(
        forge, "find_open", lambda kind, name, cwd: forge.MergeRequest("9", "u") if name == branch else None
    )
    monkeypatch.setattr(forge, "target", lambda kind, number, cwd: "feat/a")
    retargeted: list[str] = []
    monkeypatch.setattr(forge, "retarget", lambda kind, number, target, cwd: retargeted.append(target))
    session.update(stacked, restack_onto=onto)
    git("rebase", "--quiet", "--onto", onto, meta["fork_point"], cwd=stacked)
    meta, head = session.read(), git("rev-parse", "HEAD", cwd=stacked)
    remote = git("ls-remote", "origin", f"refs/heads/{branch}", cwd=stacked)

    result = restack.run(load(), meta, dry_run=True)

    assert result.dry_run and result.state == "restacked" and result.commits == 1
    assert result.log[0].startswith("DRY RUN:")
    assert session.read() == meta and git("rev-parse", "HEAD", cwd=stacked) == head
    assert git("ls-remote", "origin", f"refs/heads/{branch}", cwd=stacked) == remote
    assert retargeted == []


@pytest.mark.parametrize("merged", [False, True])
def test_retry_after_push_failure(stacked: Path, repo: Path, monkeypatch: pytest.MonkeyPatch, merged: bool) -> None:
    onto = base_commit(repo, "more.txt")
    if merged:
        merge_base_into_main(repo, "squash")
        _remove_base(repo)
        onto = git("rev-parse", "origin/main", cwd=repo)
        monkeypatch.setattr(forge, "merged", lambda kind, branch, cwd: [forge.MergeRequest("4", "u")])
    before = session.read()
    hook = repo.parent / "origin.git/hooks/pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    with pytest.raises(AwError, match="git push"):
        restack.run(load(), before)

    meta = session.read()
    assert meta["fork_point"] == before["fork_point"] and meta["base"] == "feat/a"
    assert meta.get("restack_onto") == onto
    assert git("merge-base", "--is-ancestor", onto, "HEAD", cwd=stacked) == ""
    head = git("rev-parse", "HEAD", cwd=stacked)
    assert git("rev-parse", "@{upstream}", cwd=stacked) != head
    hook.unlink()
    rebase_hook = repo / ".git/hooks/pre-rebase"
    rebase_hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    rebase_hook.chmod(0o755)

    result = restack.run(load(), session.read())

    assert result.state == "restacked" and result.commits == 1
    assert git("rev-parse", "HEAD", cwd=stacked) == head
    assert git("rev-parse", "@{upstream}", cwd=stacked) == head
    meta = session.read()
    assert meta["fork_point"] == onto and meta["restack_onto"] == ""
    assert meta["base"] == ("" if merged else "feat/a")
    assert restack.run(load(), meta).state == ("not_stacked" if merged else "up_to_date")


@pytest.mark.parametrize("failure", ["target", "retarget"])
def test_retry_after_retarget_failure(stacked: Path, repo: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    merge_base_into_main(repo, "squash")
    _remove_base(repo)
    branch = session.read()["branch"]
    monkeypatch.setattr(
        forge, "merged", lambda kind, name, cwd: [forge.MergeRequest("4", "u")] if name == "feat/a" else []
    )
    monkeypatch.setattr(
        forge, "find_open", lambda kind, name, cwd: forge.MergeRequest("9", "u") if name == branch else None
    )
    failing = True
    retargeted: list[str] = []

    def read_target(kind: str, number: str, cwd: Path) -> str:
        if failing and failure == "target":
            raise AwError("forge unavailable")
        return "feat/a"

    def retarget(kind: str, number: str, target: str, cwd: Path) -> None:
        if failing and failure == "retarget":
            raise AwError("forge unavailable")
        retargeted.append(target)

    monkeypatch.setattr(forge, "target", read_target)
    monkeypatch.setattr(forge, "retarget", retarget)
    with pytest.raises(AwError, match="forge unavailable"):
        restack.run(load(), session.read())

    meta = session.read()
    assert meta["base"] == "feat/a" and meta["restack_onto"] == git("rev-parse", "origin/main", cwd=stacked)
    head = git("rev-parse", "HEAD", cwd=stacked)
    assert git("rev-parse", "@{upstream}", cwd=stacked) == head
    rebase_hook = repo / ".git/hooks/pre-rebase"
    rebase_hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    rebase_hook.chmod(0o755)
    failing = False

    result = restack.run(load(), session.read())

    assert result.state == "restacked" and result.retargeted == "#9"
    assert retargeted == ["main"]
    assert git("rev-parse", "HEAD", cwd=stacked) == head
    meta = session.read()
    assert meta["base"] == "" and meta["restack_onto"] == ""
    assert meta["fork_point"] == git("rev-parse", "origin/main", cwd=stacked)
    assert restack.run(load(), meta).state == "not_stacked"
    assert retargeted == ["main"]


def test_retry_preserves_remote_work(stacked: Path, repo: Path) -> None:
    onto = base_commit(repo, "more.txt")
    branch = session.read()["branch"]
    peer = repo.parent / "peer"
    git("clone", "-q", "--branch", branch, str(repo.parent / "origin.git"), str(peer), cwd=repo)
    remote_head = commit(peer, "peer.txt")
    git("push", "-q", "origin", branch, cwd=peer)

    with pytest.raises(AwError, match="git push"):
        restack.run(load(), session.read())
    head = git("rev-parse", "HEAD", cwd=stacked)
    meta = session.read()
    assert meta["base"] == "feat/a" and meta["restack_onto"] == onto
    with pytest.raises(AwError, match="git push"):
        restack.run(load(), meta)
    assert git("ls-remote", "origin", f"refs/heads/{branch}", cwd=stacked).split()[0] == remote_head
    assert git("rev-parse", "HEAD", cwd=stacked) == head and session.read() == meta


@pytest.mark.parametrize("merged", [False, True])
def test_aborted_restack_can_restart(stacked: Path, repo: Path, monkeypatch: pytest.MonkeyPatch, merged: bool) -> None:
    base_commit(repo, "own.txt", "theirs\n")
    if merged:
        merge_base_into_main(repo, "squash")
        _remove_base(repo)
        monkeypatch.setattr(forge, "merged", lambda kind, branch, cwd: [forge.MergeRequest("4", "u")])
    before, head = session.read(), git("rev-parse", "HEAD", cwd=stacked)
    assert restack.run(load(), before).state == "conflict"
    git("rebase", "--abort", cwd=stacked)
    assert git("rev-parse", "HEAD", cwd=stacked) == head
    assert session.read()["fork_point"] == before["fork_point"]
    assert restack.run(load(), session.read()).state == "conflict"
    assert session.read()["fork_point"] == before["fork_point"]
    assert git("rev-parse", f"origin/{before['branch']}", cwd=stacked) == head


@pytest.mark.parametrize("failure", ["merged", "find_open"])
def test_unknown_merge_preserves_state(
    stacked: Path, repo: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    base_commit(repo, "more.txt")
    monkeypatch.setattr(forge, "merged", lambda kind, branch, cwd: [forge.MergeRequest("4", "u")])

    def refuse(kind: str, branch: str, cwd: Path) -> None:
        raise AwError("forge unavailable")

    monkeypatch.setattr(forge, failure, refuse)
    meta, head = session.read(), git("rev-parse", "HEAD", cwd=stacked)
    with pytest.raises(AwError, match="forge unavailable"):
        restack.run(load(), meta)
    assert session.read() == meta and git("rev-parse", "HEAD", cwd=stacked) == head
    assert git("rev-parse", "@{upstream}", cwd=stacked) == head


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
    assert result.commits == 2
    meta = session.read()
    assert meta["fork_point"] == tip and meta["restack_onto"] == ""
    assert git("rev-parse", "HEAD", cwd=stacked) == git("rev-parse", "@{upstream}", cwd=stacked)


@pytest.mark.parametrize("json_output", [False, True])
def test_cli_reports_recovered_commits(
    stacked: Path, repo: Path, capsys: pytest.CaptureFixture[str], json_output: bool
) -> None:
    """Conflict recovery reports only the stacked commit."""
    tip = base_commit(repo, "own.txt", "theirs\n")
    assert cli.main(["restack"]) == 1
    capsys.readouterr()

    (stacked / "own.txt").write_text("resolved\n", encoding="utf-8")
    git("add", "own.txt", cwd=stacked)
    subprocess.run(
        ["git", "-c", "core.editor=true", "rebase", "--continue"], cwd=stacked, check=True, capture_output=True
    )
    branch = session.read()["branch"]
    assert cli.main(["restack", "--json"] if json_output else ["restack"]) == 0
    out = capsys.readouterr().out
    summary = f"restacked {branch}: 1 commit onto feat/a"
    if json_output:
        data = json.loads(out)
        assert data["state"] == "restacked" and data["commits"] == 1
        assert data["summary"] == summary
    else:
        assert out.splitlines() == [f"pushed {branch} (--force-with-lease)", summary]
    assert own_commits(stacked, tip) == ["own.txt"]
    meta = session.read()
    assert meta["fork_point"] == tip and meta["restack_onto"] == ""
    assert git("rev-parse", "HEAD", cwd=stacked) == git("rev-parse", "@{upstream}", cwd=stacked)


@pytest.mark.parametrize("method", ["rewrite", "squash", "rebase"])
def test_recovery_accepts_rewritten_history(
    stacked: Path, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], method: str
) -> None:
    base_commit(repo, "own.txt", "theirs\n")
    if method == "rewrite":
        git("checkout", "-q", "feat/a", cwd=repo)
        git("reset", "--soft", "main", cwd=repo)
        git("commit", "-qm", "rewritten base", cwd=repo)
        git("push", "-q", "--force-with-lease", "origin", "feat/a", cwd=repo)
        git("checkout", "-q", "main", cwd=repo)
        upstream = "origin/feat/a"
    else:
        merge_base_into_main(repo, method)
        monkeypatch.setattr(forge, "merged", lambda kind, branch, cwd: [forge.MergeRequest("4", "u")])
        upstream = "origin/main"
    assert cli.main(["restack"]) == 1
    capsys.readouterr()
    pending = session.read()["restack_onto"]
    assert pending == git("rev-parse", upstream, cwd=stacked)
    (stacked / "own.txt").write_text("resolved\n", encoding="utf-8")
    git("add", "own.txt", cwd=stacked)
    subprocess.run(
        ["git", "-c", "core.editor=true", "rebase", "--continue"], cwd=stacked, check=True, capture_output=True
    )
    meta = session.read()
    assert meta["fork_point"] not in git("rev-list", "HEAD", cwd=stacked).splitlines()

    assert cli.main(["restack", "--dry-run"]) == 0
    assert session.read() == meta
    capsys.readouterr()
    assert cli.main(["restack"]) == 0

    assert capsys.readouterr().out.splitlines()[-1].startswith(f"restacked {meta['branch']}: 1 commit onto ")
    assert own_commits(stacked, pending) == ["own.txt"]
    meta = session.read()
    assert meta["fork_point"] == pending and meta["restack_onto"] == ""
    assert meta["base"] == ("feat/a" if method == "rewrite" else "")
    assert git("rev-parse", "HEAD", cwd=stacked) == git("rev-parse", "@{upstream}", cwd=stacked)


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("base_merged", [False, True])
def test_dry_run_preserves_recovery(
    stacked: Path,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    json_output: bool,
    base_merged: bool,
) -> None:
    base_commit(repo, "own.txt", "theirs\n")
    branch = session.read()["branch"]
    retargeted: list[tuple[str, str]] = []
    if base_merged:
        merge_base_into_main(repo, "squash")
        monkeypatch.setattr(forge, "merged", lambda kind, b, cwd: [forge.MergeRequest("4", "u")])
        monkeypatch.setattr(
            forge, "find_open", lambda kind, b, cwd: forge.MergeRequest("9", "u") if b == branch else None
        )
        monkeypatch.setattr(forge, "target", lambda kind, ref, cwd: "feat/a")
        monkeypatch.setattr(forge, "retarget", lambda kind, ref, to, cwd: retargeted.append((ref, to)))
    assert cli.main(["restack"]) == 1
    capsys.readouterr()
    (stacked / "own.txt").write_text("resolved\n", encoding="utf-8")
    git("add", "own.txt", cwd=stacked)
    subprocess.run(
        ["git", "-c", "core.editor=true", "rebase", "--continue"], cwd=stacked, check=True, capture_output=True
    )
    meta = session.read()
    head = git("rev-parse", "HEAD", cwd=stacked)
    remote_ref = f"refs/heads/{meta['branch']}"
    remote = git("ls-remote", "origin", remote_ref, cwd=stacked)

    args = ["restack", "--dry-run"] + (["--json"] if json_output else [])
    assert cli.main(args) == 0

    assert git("ls-remote", "origin", remote_ref, cwd=stacked) == remote
    assert session.read() == meta
    assert git("rev-parse", "HEAD", cwd=stacked) == head
    assert retargeted == []
    out = capsys.readouterr().out
    onto = "main (base feat/a merged)" if base_merged else "feat/a"
    summary = f"would restack {branch}: 1 commit onto {onto}"
    if json_output:
        data = json.loads(out)
        assert data["dry_run"] and data["commits"] == 1
        assert data["summary"] == summary
    else:
        assert out.splitlines()[-1] == summary
        assert "pushed" not in out


def test_cli_reports_lines_a_summary_and_json(stacked, repo, capsys):
    base_commit(repo, "more.txt")
    head = git("rev-parse", "HEAD", cwd=stacked)
    meta = session.read()
    branch = meta["branch"]
    assert cli.main(["restack", "--dry-run"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("DRY RUN") and git("rev-parse", "HEAD", cwd=stacked) == head
    assert out[-1] == f"would restack {branch}: 1 commit onto feat/a"
    assert session.read() == meta
    assert git("rev-parse", "@{upstream}", cwd=stacked) == head

    assert cli.main(["restack"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[-1] == f"restacked {branch}: 1 commit onto feat/a"
    assert len(out) <= 6

    assert cli.main(["restack", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["state"] == "up_to_date" and data["base"] == "feat/a" and "summary" in data


def test_cli_conflict_names_files_and_next_step(stacked, repo, capsys):
    commit(stacked, "base.txt", "ours\n")
    git("push", "-q", "origin", "HEAD", cwd=stacked)
    base_commit(repo, "base.txt", "theirs\n")
    assert cli.main(["restack"]) == 1
    out = capsys.readouterr().out
    assert "base.txt" in out and "git rebase --continue" in out and "aw restack" in out


@pytest.mark.parametrize("pending", [False, True])
def test_restack_refuses_a_fork_point_outside_the_branch(stacked: Path, repo: Path, pending: bool) -> None:
    tip = base_commit(repo, "more.txt")
    session.update(stacked, fork_point=tip, restack_onto=tip if pending else "")
    meta, head = session.read(), git("rev-parse", "HEAD", cwd=stacked)
    with pytest.raises(AwError, match=r"fork point .* is not in"):
        restack.run(load(), session.read())
    assert session.read() == meta and git("rev-parse", "HEAD", cwd=stacked) == head
