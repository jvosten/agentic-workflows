"""aw init: detect, prompt, and write <repo>/.agents/aw.toml."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

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


def _main_branch(root: Path) -> str | None:
    try:
        return git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=root).removeprefix("origin/")
    except AwError:
        return git("branch", "--show-current", cwd=root) or None


def _tracker(root: Path) -> str | None:
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


def _session_log(root: Path) -> str | None:
    return "SESSIONS.md" if (root / "SESSIONS.md").is_file() else None


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
    "tracker": _tracker,
    "instructions_file": _instructions_file,
    "session_log": _session_log,
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


def prompt(key: str, spec: dict, default: Any) -> Any:
    shown = ", ".join(default) if isinstance(default, list) else toml_value(default).strip('"')
    choices = f" ({'/'.join(spec['choices'])})" if spec["type"] == "choice" else ""
    while True:
        answer = input(f"{spec['help']}{choices}\n  {key} [{shown}]: ")
        if not answer.strip():
            return default
        try:
            return parse_text(key, spec, answer)
        except AwError as e:
            print(f"  {e}", file=sys.stderr)


def run(assume_yes: bool, sets: list[str]) -> Path:
    full = load_schema()
    schema = full["keys"]
    root = checkout_root()
    path = root / PROJECT_FILE
    existing = read_toml(path) if path.is_file() else {}
    for key in existing:
        if key != "aw_version" and key not in schema:
            print(f"warning: dropping unknown key {key!r} from {path}", file=sys.stderr)

    overrides: dict[str, Any] = {}
    for item in sets:
        key, sep, text = item.partition("=")
        if not sep or key not in schema:
            raise AwError(f"--set expects KEY=VALUE with a known key: {item!r}")
        overrides[key] = parse_text(key, schema[key], text)

    detected = detect(root, schema)
    interactive = not assume_yes and sys.stdin.isatty()
    values: dict[str, Any] = {"aw_version": full["version"]}
    for key, spec in schema.items():
        if key in overrides:
            values[key] = overrides[key]
        elif spec.get("ask"):
            default = existing.get(key, detected.get(key, spec["default"]))
            values[key] = prompt(key, spec, default) if interactive else default
        elif key in existing:
            values[key] = existing[key]

    path.parent.mkdir(exist_ok=True)
    path.write_text(dump_toml(values))
    ignore = path.parent / ".gitignore"
    local_name = Path(LOCAL_FILE).name
    if not ignore.is_file() or local_name not in ignore.read_text().split():
        with ignore.open("a") as f:
            f.write(f"{local_name}\n")
    return path
