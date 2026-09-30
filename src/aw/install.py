"""aw install: link skills and the CLI into ~/.agents, and skills into agent-specific dirs.

~/.agents/skills/<skill> -> <source>/skills/<skill>
~/.agents/bin/aw         -> the installed aw executable
~/.claude/skills/<skill> -> ~/.agents/skills/<skill>   (Claude Code does not read ~/.agents/skills)
"""

from __future__ import annotations

import shutil
from pathlib import Path

from aw.config import AwError

# Agents that need links; agents reading ~/.agents/skills natively (Codex, Cursor, ...) need none.
AGENT_DIRS = {"claude": ".claude/skills"}


def agents_home() -> Path:
    return Path.home() / ".agents"


def skills_source() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here.parents[1] / "skills", here / "_skills"):
        if candidate.is_dir():
            return candidate
    raise AwError("skill sources not found")


def source_skills() -> list[Path]:
    return sorted(p.parent for p in skills_source().glob("*/SKILL.md"))


def _link(dest: Path, target: Path) -> str:
    if dest.is_symlink():
        if dest.resolve() == target.resolve():
            return "unchanged"
        dest.unlink()
    elif dest.exists():
        raise AwError(f"{dest} exists and is not a symlink; remove it first")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(target)
    return "linked"


def _prune(directory: Path, owned: Path) -> list[str]:
    """Remove dangling symlinks in directory that point into owned."""
    removed = []
    if directory.is_dir():
        for entry in directory.iterdir():
            if entry.is_symlink() and not entry.exists():
                target = Path(entry.readlink())
                if not target.is_absolute():
                    target = entry.parent / target
                if target.parent == owned:
                    entry.unlink()
                    removed.append(f"removed {entry}")
    return removed


def run(agents: list[str], exe: Path | None = None) -> list[str]:
    unknown = set(agents) - AGENT_DIRS.keys()
    if unknown:
        raise AwError(f"unknown agent(s): {', '.join(sorted(unknown))} (known: {', '.join(AGENT_DIRS)})")
    home = agents_home()
    log: list[str] = []

    skills_dir = home / "skills"
    log += _prune(skills_dir, skills_source())
    for skill in source_skills():
        dest = skills_dir / skill.name
        log.append(f"{_link(dest, skill)} {dest}")
        for agent in agents:
            agent_dest = Path.home() / AGENT_DIRS[agent] / skill.name
            log.append(f"{_link(agent_dest, dest)} {agent_dest}")
    for agent in agents:
        log += _prune(Path.home() / AGENT_DIRS[agent], skills_dir)

    exe = exe or (Path(p) if (p := shutil.which("aw")) else None)
    bin_link = home / "bin/aw"
    if exe is None:
        log.append("warning: aw executable not on PATH; run `uv tool install --editable .` first")
    elif exe.resolve() != bin_link.resolve() or not bin_link.is_symlink():
        log.append(f"{_link(bin_link, exe.resolve())} {bin_link}")
    return log
