import os
import socket
import subprocess

import pytest


def test_no_network():
    with pytest.raises(OSError, match="no network in tests"):
        socket.create_connection(("example.com", 443), timeout=1)


def test_no_forge_or_tracker_credentials():
    leaked = [k for k in os.environ if k.startswith(("JIRA_", "GH_", "GITHUB_", "GITLAB_", "GLAB_"))]
    assert leaked == []


@pytest.mark.parametrize("cli", ["gh", "glab"])
def test_forge_clis_never_run(cli):
    r = subprocess.run([cli, "api", "user"], capture_output=True, text=True, check=False)
    assert r.returncode != 0 and "no network in tests" in r.stderr
