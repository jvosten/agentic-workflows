"""aw install: link skills and the CLI into ~/.agents, and skills into agent-specific dirs.

~/.agents/skills/<skill> -> <source>/skills/<skill>
~/.agents/bin/aw         -> the installed aw executable
~/.claude/skills/<skill> -> ~/.agents/skills/<skill>   (Claude Code does not read ~/.agents/skills)
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
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


@dataclass
class Change:
    action: str  # new | updated | unchanged | removed
    path: Path


@dataclass
class Report:
    changes: list[Change] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _link(dest: Path, target: Path) -> Change:
    action = "new"
    if dest.is_symlink():
        if dest.resolve() == target.resolve():
            return Change("unchanged", dest)
        dest.unlink()
        action = "updated"
    elif dest.exists():
        raise AwError(f"{dest} exists and is not a symlink; remove it first")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(target)
    return Change(action, dest)


def _prune(directory: Path, owned: Path) -> list[Change]:
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
                    removed.append(Change("removed", entry))
    return removed


def run(agents: list[str], exe: Path | None = None) -> Report:
    unknown = set(agents) - AGENT_DIRS.keys()
    if unknown:
        raise AwError(f"unknown agent(s): {', '.join(sorted(unknown))} (known: {', '.join(AGENT_DIRS)})")
    home = agents_home()
    report = Report()

    skills_dir = home / "skills"
    report.changes += _prune(skills_dir, skills_source())
    for skill in source_skills():
        dest = skills_dir / skill.name
        report.changes.append(_link(dest, skill))
        for agent in agents:
            report.changes.append(_link(Path.home() / AGENT_DIRS[agent] / skill.name, dest))
    for agent in agents:
        report.changes += _prune(Path.home() / AGENT_DIRS[agent], skills_dir)

    exe = exe or (Path(p) if (p := shutil.which("aw")) else None)
    bin_link = home / "bin/aw"
    if exe is None:
        report.warnings.append("aw executable not found; run `uv tool install --editable .` first")
        return report
    if exe.resolve() == bin_link.resolve() and bin_link.is_symlink():
        report.changes.append(Change("unchanged", bin_link))
    else:
        report.changes.append(_link(bin_link, exe.resolve()))
    if not shutil.which("aw"):
        report.warnings.append(
            "`aw` is not on your PATH; skills still work through ~/.agents/bin/aw.\n"
            "  For your shell: `uv tool update-shell`, then open a new terminal."
        )
    return report
