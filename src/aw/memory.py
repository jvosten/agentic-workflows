"""Project memory: committed decisions and gotchas, one file per kind."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from aw.config import AwError, Config

KINDS = {
    "decision": ("decisions.md", "Decisions", "What this project settled, and why. Newest last."),
    "gotcha": ("gotchas.md", "Gotchas", "Non-obvious constraints that cost someone time. Newest last."),
}


def file(cfg: Config, kind: str) -> Path:
    if kind not in KINDS:
        raise AwError(f"unknown memory kind: {kind} (known: {', '.join(KINDS)})")
    return cfg.checkout / cfg.get("memory_dir") / KINDS[kind][0]


def add(cfg: Config, kind: str, title: str, text: str, ref: str | None) -> Path:
    path = file(cfg, kind)
    if not path.is_file():
        _, heading, intro = KINDS[kind]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {heading}\n\n{intro}\n")
    stamp = " · ".join(filter(None, (date.today().isoformat(), ref)))
    entry = f"\n## {title}\n\n_{stamp}_\n\n{text.strip()}\n"
    with path.open("a") as handle:
        handle.write(entry)
    return path


SUPERSEDED = "## Superseded"


def supersede(cfg: Config, kind: str, title: str, reason: str) -> Path:
    """Move one entry to the end of its file, below the Superseded heading."""
    path = file(cfg, kind)
    if not path.is_file():
        raise AwError(f"{path} does not exist")
    lines = path.read_text().splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.strip() == f"## {title}"), None)
    if start is None:
        raise AwError(f"{path}: no entry titled {title!r}")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    entry = "".join(lines[start + 1:end]).strip()
    kept = "".join(lines[:start] + lines[end:]).rstrip() + "\n"
    if SUPERSEDED not in kept:
        kept += f"\n{SUPERSEDED}\n"
    path.write_text(f"{kept}\n### {title}\n\n{entry}\n\n_Superseded: {reason}_\n")
    return path
