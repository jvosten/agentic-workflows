import os
import shutil
from datetime import date
from pathlib import Path

import pytest

from aw import cli, session, start_task
from aw.config import AwError, git, load


@pytest.fixture
def configured(repo, tmp_path):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(
        f'worktree_root = "{tmp_path}/wt"\non_start = "echo hook-{{issue}} > hook.txt"\n'
    )
    return repo


def test_names_hook_and_output(configured, tmp_path):
    out = start_task.run(load(), "fix", "pbs-auth", "#42")
    today = date.today().strftime("%Y%m%d")
    assert out == {
        "branch": f"fix/pbs-auth-{today}",
        "worktree": str(tmp_path / "wt/42-pbs-auth"),
        "issue": "42",
    }
    assert (tmp_path / "wt/42-pbs-auth/hook.txt").read_text() == "hook-42\n"
    meta = session.read(tmp_path / "wt/42-pbs-auth")
    assert (meta["branch"], meta["issue"], meta["slug"]) == (out["branch"], "42", "pbs-auth")
    assert "session" not in meta
    assert not (configured / ".git/aw-last-session").exists()


def fake_direnv(tmp_path, monkeypatch, script):
    """A `direnv` first on PATH; script None: no direnv on PATH at all (git stays reachable)."""
    bin_dir = tmp_path / "direnv-bin"
    bin_dir.mkdir()
    if script is None:
        (bin_dir / "git").symlink_to(shutil.which("git"))
        monkeypatch.setenv("PATH", str(bin_dir))
    else:
        (bin_dir / "direnv").write_text(f"#!/bin/sh\n{script}\n")
        (bin_dir / "direnv").chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


@pytest.mark.parametrize("script", [None, "echo broken >&2; exit 1"], ids=["missing", "failing"])
def test_direnv_trouble_is_a_warning_and_the_start_goes_on(configured, tmp_path, monkeypatch, capfd, script):
    monkeypatch.setenv("AW_DIRENV", "true")
    fake_direnv(tmp_path, monkeypatch, script)
    out = start_task.run(load(), "docs", "one", None)
    assert (Path(out["worktree"]) / "hook.txt").read_text() == "hook-\n"
    assert "warning: direnv allow" in capfd.readouterr().err


def test_a_tracked_envrc_is_never_overwritten(configured, tmp_path, monkeypatch):
    (configured / ".envrc").write_text("export PROJECT=own\n")
    git("add", ".envrc", cwd=configured)
    git("commit", "-qm", "envrc", cwd=configured)
    git("push", "-q", "origin", "main", cwd=configured)
    monkeypatch.setenv("AW_DIRENV", "true")
    fake_direnv(tmp_path, monkeypatch, "exit 0")
    out = start_task.run(load(), "docs", "one", None)
    assert (Path(out["worktree"]) / ".envrc").read_text() == "export PROJECT=own\n"
    assert not git("status", "--porcelain", ".envrc", cwd=out["worktree"])


def test_without_an_issue_the_worktree_is_the_slug(configured, tmp_path):
    first = start_task.run(load(), "docs", "one", None)
    assert first["worktree"] == str(tmp_path / "wt/one")
    assert (Path(first["worktree"]) / "hook.txt").read_text() == "hook-\n"  # on_start runs without an issue too
    git("branch", "-q", "-m", first["branch"], "docs/one-earlier", cwd=configured)
    with pytest.raises(AwError, match=f"path exists: {tmp_path}/wt/one"):
        start_task.run(load(), "docs", "one", None)


def test_from_inside_worktree(configured, tmp_path, monkeypatch):
    first = start_task.run(load(), "docs", "one", None)
    monkeypatch.chdir(first["worktree"])
    second = start_task.run(load(), "docs", "two", None)
    assert (Path(first["worktree"]).name, Path(second["worktree"]).name) == ("one", "two")


@pytest.mark.parametrize("key", ["worktree_name", "branch_name", "on_start"])
def test_a_config_with_the_session_number_is_refused(configured, tmp_path, monkeypatch, key):
    monkeypatch.setenv(f"AW_{key.upper()}", "s{n}-{slug}")
    with pytest.raises(AwError, match=f"{key} uses {{n}}, the session number, which is gone"):
        start_task.run(load(), "docs", "one", None)
    assert not (tmp_path / "wt").exists()


def test_an_old_session_file_with_a_number_still_reads(configured, tmp_path):
    out = start_task.run(load(), "docs", "one", None)
    session.update(out["worktree"], session=7)
    assert session.read(out["worktree"])["session"] == 7


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("wip", "x", None), "type 'wip'"),
        (("feat", "Bad_Slug", None), "kebab-case"),
        (("feat", "x", "a b"), "invalid none issue id"),
    ],
)
def test_rejects_bad_input(configured, args, message):
    with pytest.raises(AwError, match=message):
        start_task.run(load(), *args)


def push_to_origin(tmp_path, name):
    """A commit on origin's main from another clone, which the local main does not have yet."""
    other = tmp_path / "other"
    if not other.exists():
        git("clone", "-q", str(tmp_path / "origin.git"), str(other), cwd=tmp_path)
    git("pull", "-q", cwd=other)
    (other / name).write_text(f"{name}\n")
    git("add", ".", cwd=other)
    git("commit", "-qm", name, cwd=other)
    git("push", "-q", "origin", "main", cwd=other)


def test_starts_while_the_primary_checkout_is_on_another_branch(configured, tmp_path):
    git("checkout", "-q", "-b", "look-around", cwd=configured)
    push_to_origin(tmp_path, "upstream.txt")
    out = start_task.run(load(), "feat", "x", None)
    assert (tmp_path / "wt/x/upstream.txt").is_file()  # the session starts from origin's main
    assert git("branch", "--show-current", cwd=configured) == "look-around"
    assert git("rev-parse", "main", cwd=configured) == git("rev-parse", "origin/main", cwd=configured)
    assert out["branch"].startswith("feat/x-")


def test_main_checked_out_in_another_worktree_is_merged_there(configured, tmp_path):
    git("checkout", "-q", "-b", "look-around", cwd=configured)
    holder = tmp_path / "holder"
    git("worktree", "add", "-q", str(holder), "main", cwd=configured)
    push_to_origin(tmp_path, "upstream.txt")
    start_task.run(load(), "feat", "x", None)
    assert (holder / "upstream.txt").is_file()  # that checkout's files follow the moved branch
    assert git("status", "--porcelain", cwd=holder) == ""


def test_local_main_ahead_stays_and_a_diverged_main_fails(configured, tmp_path):
    (configured / "local.txt").write_text("x\n")
    git("add", "local.txt", cwd=configured)
    git("commit", "-qm", "local", cwd=configured)
    ahead = git("rev-parse", "main", cwd=configured)
    start_task.run(load(), "feat", "x", None)
    assert git("rev-parse", "main", cwd=configured) == ahead

    git("checkout", "-q", "-b", "look-around", cwd=configured)
    push_to_origin(tmp_path, "upstream.txt")
    with pytest.raises(AwError, match="main and origin/main have diverged"):
        start_task.run(load(), "feat", "y", None)
    assert git("rev-parse", "main", cwd=configured) == ahead


def test_existing_branch(configured):
    today = date.today().strftime("%Y%m%d")
    git("branch", f"feat/x-{today}", cwd=configured)
    with pytest.raises(AwError, match="branch exists"):
        start_task.run(load(), "feat", "x", None)


def push_base(repo, name="feat/a"):
    """A pending base branch on origin with one commit main lacks; returns its tip."""
    git("checkout", "-q", "-b", name, cwd=repo)
    (repo / "base.txt").write_text("base\n")
    git("add", "base.txt", cwd=repo)
    git("commit", "-qm", "base", cwd=repo)
    git("push", "-q", "-u", "origin", name, cwd=repo)
    git("checkout", "-q", "main", cwd=repo)
    return git("rev-parse", name, cwd=repo)


def test_stacked_start_forks_from_the_base_and_records_it(configured, tmp_path, monkeypatch):
    monkeypatch.setenv("AW_FORGE", "github")
    tip = push_base(configured)
    out = start_task.run(load(), "feat", "b", None, base="feat/a")
    assert git("rev-parse", "HEAD", cwd=out["worktree"]) == tip
    meta = session.read(out["worktree"])
    assert (meta["base"], meta["fork_point"]) == ("feat/a", tip)


@pytest.mark.parametrize(
    ("forge_kind", "base", "message"),
    [
        ("none", "feat/a", "--base needs a forge"),
        ("github", "main", "already starts from main"),
        ("github", "feat/missing", "origin has no branch feat/missing"),
    ],
)
def test_stacked_start_refuses(configured, monkeypatch, forge_kind, base, message):
    monkeypatch.setenv("AW_FORGE", forge_kind)
    push_base(configured)
    with pytest.raises(AwError, match=message):
        start_task.run(load(), "feat", "b", None, base=base)
    assert not (configured.parent / "wt").exists()


def test_on_start_placeholders_are_quoted(repo, tmp_path):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(
        f'worktree_root = "{tmp_path}/wt"\non_start = "printf \'%s|\' {{issue}} {{slug}} > hook.txt"\n'
    )
    out = start_task.run(load(), "docs", "quoted", None)
    assert (Path(out["worktree"]) / "hook.txt").read_text() == "|quoted|"  # the empty issue is still an argument


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('session = "six"\n', "session must be a whole number"),
        ("session = 6\nissue = 12\n", "issue must be a string"),
        ('session = 6\nbase = "feat/x"\n', "base needs fork_point"),
        ("session = [\n", "aw-session.toml"),
    ],
)
def test_a_malformed_session_file_names_the_file_and_field(configured, text, message):
    worktree = Path(start_task.run(load(), "docs", "one", None)["worktree"])
    meta = Path(git("rev-parse", "--absolute-git-dir", cwd=worktree)) / "aw-session.toml"
    meta.write_text(text)
    with pytest.raises(AwError, match=message) as e:
        session.read(worktree)
    assert str(meta) in str(e.value)


def test_a_malformed_session_is_never_read_as_no_session(configured, monkeypatch):
    """The merge request target falls back to main only outside a session, never on a file it cannot read."""
    worktree = Path(start_task.run(load(), "docs", "one", None)["worktree"])
    (Path(git("rev-parse", "--absolute-git-dir", cwd=worktree)) / "aw-session.toml").write_text("base = 1\n")
    monkeypatch.chdir(worktree)
    with pytest.raises(AwError, match="base must be a string"):
        cli._target(load())


def test_hooks_run_when_sys_stderr_is_not_a_file(configured, capsys):
    """Hook and direnv output goes to file descriptor 2, not to the sys.stderr object: replaced (capsys, an embedding
    host), that object has no fileno and subprocess would fail before the hook runs."""
    out = start_task.run(load(), "docs", "one", None)
    assert (Path(out["worktree"]) / "hook.txt").read_text() == "hook-\n"
