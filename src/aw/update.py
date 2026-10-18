"""aw update: bring the installed aw up to date, relink its skills, and say what the current project needs.

editable install  the source clone's default branch fast-forwards (git pull --ff-only, whatever is checked out)
packaged install  uv tool upgrade agentic-workflows

The relink and the project check run in a new process: this one still holds the modules from before the update.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from aw import install, ui
from aw.config import PROJECT_FILE, AwError, checkout_root, fast_forward, git

PACKAGE = "agentic-workflows"
UV_TIMEOUT = 300  # seconds; uv resolves and downloads the package
SHOWN_COMMITS = 20


def source_clone() -> Path | None:
    """The git clone an editable install runs from; None for a packaged install (skills in aw/_skills)."""
    skills = install.skills_source()
    clone = skills.parent
    return clone if skills.name == "skills" and (clone / ".git").exists() else None


def default_branch(clone: Path) -> str:
    try:
        return git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=clone).removeprefix("origin/")
    except AwError:
        return "main"


def update_clone(clone: Path) -> list[str]:
    """Fast-forward the clone's default branch from origin; the commits it gained, and which branch the install runs."""
    branch = default_branch(clone)
    ref = f"refs/heads/{branch}"
    before = git("rev-parse", ref, cwd=clone)
    moved = fast_forward(clone, branch)
    after = git("rev-parse", ref, cwd=clone)
    if before == after:
        log = [f"{branch} up to date" if moved.startswith("updated") else moved]
    else:
        count = int(git("rev-list", "--count", f"{before}..{after}", cwd=clone))
        subjects = git("log", "--format=%s", f"-{SHOWN_COMMITS}", f"{before}..{after}", cwd=clone).splitlines()
        log = [moved, f"{before[:7]}..{after[:7]}: {ui.plural(count, 'commit')}"]
        log += [f"  {subject}" for subject in subjects]
        if count > SHOWN_COMMITS:
            log.append(f"  … and {count - SHOWN_COMMITS} more")
    current = git("branch", "--show-current", cwd=clone)
    if current != branch:
        log.append(
            f"warning: {clone} has {current or 'a detached HEAD'} checked out; the installed aw runs that, not {branch}"
        )
    return log


def upgrade_tool() -> list[str]:
    """uv tool upgrade for a packaged install; uv's report lines."""
    args = ["uv", "tool", "upgrade", PACKAGE]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=UV_TIMEOUT, check=False)
    except FileNotFoundError:
        raise AwError("uv not found; aw update upgrades a packaged install with `uv tool upgrade`") from None
    except subprocess.TimeoutExpired:
        raise AwError(f"{' '.join(args)}: no answer within {UV_TIMEOUT}s") from None
    if r.returncode:
        raise AwError(f"{' '.join(args)}: {r.stderr.strip()}")
    return [line for line in (r.stdout + r.stderr).splitlines() if line.strip()]


def update_code() -> list[str]:
    clone = source_clone()
    return update_clone(clone) if clone else upgrade_tool()


def executable() -> Path:
    """The aw that skills call: ~/.agents/bin/aw, else the one on PATH."""
    link = install.agents_home() / "bin/aw"
    if link.exists():
        return link
    if found := shutil.which("aw"):
        return Path(found)
    raise AwError("aw executable not found; run `make install` in the source clone first")


def relink(exe: Path, agents: list[str]) -> int:
    """aw install in the updated code: links new skills, prunes removed ones. Its output passes through."""
    flags = [arg for agent in agents for arg in ("--agent", agent)]
    return subprocess.run([str(exe), "install", *flags], check=False).returncode


def project_root() -> Path | None:
    """The current checkout, when it has an aw project file."""
    try:
        root = checkout_root()
    except AwError:
        return None
    return root if (root / PROJECT_FILE).is_file() else None


def check_project(exe: Path, root: Path) -> int:
    """aw init --check in the updated code: what aw init would change. Exit 1 means changes are pending."""
    return subprocess.run([str(exe), "init", "--check"], cwd=root, check=False).returncode
