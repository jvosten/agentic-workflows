import os
import socket
import subprocess
from pathlib import Path

import pytest


def sh(*args: str, cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    """Isolated HOME and git identity; no AW_* overrides or forge and tracker credentials from the caller."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{var}_NAME", "t")
        monkeypatch.setenv(f"GIT_{var}_EMAIL", "t@example.invalid")
    for key in list(os.environ):
        if key.startswith(("AW_", "JIRA_", "GH_", "GITHUB_", "GITLAB_", "GLAB_")):
            monkeypatch.delenv(key)
    return home


@pytest.fixture(autouse=True)
def no_network(tmp_path, monkeypatch):
    """No test reaches Jira, GitHub or GitLab: sockets refuse, gh and glab fail."""
    def refuse(*args, **kwargs):
        raise OSError("no network in tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    bin_dir = tmp_path / "no-network-bin"
    bin_dir.mkdir()
    for cli in ("gh", "glab"):
        (bin_dir / cli).write_text("#!/bin/sh\necho 'no network in tests' >&2\nexit 1\n")
        (bin_dir / cli).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Primary checkout `proj` on main with a bare origin; cwd is the checkout."""
    origin = tmp_path / "origin.git"
    root = tmp_path / "proj"
    sh("git", "init", "-q", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    sh("git", "init", "-q", "-b", "main", str(root), cwd=tmp_path)
    (root / "AGENTS.md").write_text("# agents\n")
    (root / "CHANGELOG.md").write_text("# Changelog\n")
    (root / "Makefile").write_text("validate:\n\ttrue\n")
    sh("git", "add", ".", cwd=root)
    sh("git", "commit", "-qm", "init", cwd=root)
    sh("git", "remote", "add", "origin", str(origin), cwd=root)
    sh("git", "push", "-q", "-u", "origin", "main", cwd=root)
    monkeypatch.chdir(root)
    return root
