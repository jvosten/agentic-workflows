"""aw init: detect, prompt, and write <repo>/.agents/aw.toml."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aw import ui
from aw.config import (
    LOCAL_FILE,
    PROJECT_FILE,
    AwError,
    checkout_root,
    dump_toml,
    git,
    load_schema,
    parse_text,
    read_toml,
    repo_root,
    toml_value,
)
from aw.memory import LOG


def _main_branch(root: Path) -> str | None:
    try:
        return git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=root).removeprefix("origin/")
    except AwError:
        return git("branch", "--show-current", cwd=root) or None


def _forge(root: Path) -> str | None:
    try:
        url = git("remote", "get-url", "origin", cwd=root)
    except AwError:
        return "none"
    if "github.com" in url:
        return "github"
    if "gitlab" in url:
        return "gitlab"
    return None


def _instructions_file(root: Path) -> str | None:
    for name in ("AGENTS.md", "CLAUDE.md"):
        if (root / name).is_file():
            return name
    return None


def _changelog_file(root: Path) -> str | None:
    return "CHANGELOG.md" if (root / "CHANGELOG.md").is_file() else None


def _direnv(root: Path) -> bool:
    # .envrc is usually gitignored, so only the primary checkout has it.
    return (root / ".envrc").is_file() or (repo_root(root) / ".envrc").is_file()


def _make_texts(root: Path) -> list[str]:
    """Makefile plus files it includes with literal paths (no make evaluation)."""
    makefile = root / "Makefile"
    if not makefile.is_file():
        return []
    texts = [makefile.read_text(errors="replace")]
    for line in re.findall(r"^-?include\s+(.+)$", texts[0], re.MULTILINE):
        for name in line.split():
            if "$" not in name:
                texts += [p.read_text(errors="replace") for p in root.glob(name) if p.is_file()]
    return texts


def _verify_cmd(root: Path) -> str | None:
    texts = _make_texts(root)
    for target in ("validate", "check", "test"):
        if any(re.search(rf"^{target}\s*:", t, re.MULTILINE) for t in texts):
            return f"make {target}"
    return None


DETECTORS: dict[str, Callable[[Path], Any]] = {
    "main_branch": _main_branch,
    "forge": _forge,
    "changelog_file": _changelog_file,
    "instructions_file": _instructions_file,
    "direnv": _direnv,
    "verify_cmd": _verify_cmd,
}


def detect(root: Path, schema: dict[str, Any]) -> dict[str, Any]:
    found = {}
    for key, spec in schema.items():
        name = spec.get("detect")
        if name and (value := DETECTORS[name](root)) is not None:
            found[key] = value
    return found


def _matches(value: Any, condition: str) -> bool:
    """`when` condition: a value, or `!value` for anything else."""
    return value != condition[1:] if condition.startswith("!") else value == condition


def shown(value: Any) -> str:
    return ", ".join(value) if isinstance(value, list) else toml_value(value).strip('"')


def prompt(key: str, spec: dict, default: Any, source: str = "default") -> Any:
    choices = ui.style(f" ({' / '.join(spec['choices'])})", ui.DIM) if spec["type"] == "choice" else ""
    hint = ui.style(f" {source}", ui.DIM) if source != "default" else ""
    while True:
        answer = input(f"\n  {ui.style(spec['help'], ui.DIM)}{choices}\n  {key} [{shown(default)}]{hint} › ")
        if not answer.strip():
            return default
        try:
            return parse_text(key, spec, answer)
        except AwError as e:
            print(ui.style(f"  {e}", ui.RED))


@dataclass
class Report:
    path: Path
    values: dict[str, Any]  # what was written, without aw_version
    previous: dict[str, Any] | None  # the file before, None when it is new
    sources: dict[str, str]  # --set | answered | kept | detected | default
    ignored: list[str] = field(default_factory=list)  # entries added to .agents/.gitignore
    warnings: list[str] = field(default_factory=list)


def run(assume_yes: bool, sets: list[str]) -> Report:
    full = load_schema()
    schema = full["keys"]
    root = checkout_root()
    path = root / PROJECT_FILE
    existing = read_toml(path) if path.is_file() else {}
    renamed = full.get("renamed", {})
    warnings = [f"renamed {old!r} to {new!r}" for old, new in renamed.items() if old in existing]
    existing = {
        renamed.get(key, key): value
        for key, value in existing.items()
        if not (key in renamed and renamed[key] in existing)
    }
    warnings += [f"dropped unknown key {key!r}" for key in existing if key != "aw_version" and key not in schema]

    overrides: dict[str, Any] = {}
    for item in sets:
        key, sep, text = item.partition("=")
        if not sep or key not in schema:
            raise AwError(f"--set expects KEY=VALUE with a known key: {item!r}")
        overrides[key] = parse_text(key, schema[key], text)

    detected = detect(root, schema)
    interactive = not assume_yes and sys.stdin.isatty()
    if interactive:
        print(f"{ui.style('aw init', ui.BOLD)} {ui.style(ui.home(root), ui.DIM)}")
        print(ui.style("  Enter keeps the value in brackets.", ui.DIM))
    values: dict[str, Any] = {"aw_version": full["version"]}
    sources: dict[str, str] = {}
    for key, spec in schema.items():
        applies = all(_matches(values.get(k, existing.get(k)), v) for k, v in spec.get("when", {}).items())
        if key in overrides:
            values[key], sources[key] = overrides[key], "--set"
        elif spec.get("ask") and applies:
            source = "kept" if key in existing else "detected" if key in detected else "default"
            default = existing.get(key, detected.get(key, spec["default"]))
            values[key] = prompt(key, spec, default, source) if interactive else default
            sources[key] = source if values[key] == default else "answered"
        elif key in existing:
            values[key], sources[key] = existing[key], "kept"
    if interactive:
        print()

    path.parent.mkdir(exist_ok=True)
    path.write_text(dump_toml(values))
    ignore = path.parent / ".gitignore"
    entries = [Path(LOCAL_FILE).name, Path(LOG).name]
    merged = {key: spec["default"] for key, spec in schema.items()} | values
    plans = Path(merged["plan_dir"] or schema["plan_dir"]["default"])
    if merged["plan_scope"] == "local" and plans.parts[:1] == (path.parent.name,):
        entries.append(plans.relative_to(path.parent.name).as_posix() + "/")
    present = ignore.read_text().split() if ignore.is_file() else []
    missing = [entry for entry in entries if entry not in present]
    if missing:
        with ignore.open("a") as f:
            f.write("".join(f"{entry}\n" for entry in missing))
    written = {k: v for k, v in values.items() if k != "aw_version"}
    previous = {k: v for k, v in existing.items() if k != "aw_version"} if existing else None
    return Report(path, written, previous, sources, missing, warnings)
