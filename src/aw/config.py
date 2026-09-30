"""Layered project configuration.

Resolution order, later wins:
  schema defaults (schema.toml)
  ~/.agents/aw/config.toml        user, all projects
  <checkout>/.agents/aw.toml      project, committed (current checkout or worktree)
  <primary>/.agents/aw.local.toml machine, gitignored (primary checkout only)
  AW_<KEY> environment variables
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

PROJECT_FILE = ".agents/aw.toml"
LOCAL_FILE = ".agents/aw.local.toml"


class AwError(Exception):
    pass


def load_schema() -> dict[str, Any]:
    return tomllib.loads(resources.files("aw").joinpath("schema.toml").read_text())


def user_file() -> Path:
    return Path.home() / ".agents/aw/config.toml"


def git(*args: str, cwd: Path | str | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if r.returncode:
        raise AwError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def repo_root(cwd: Path | str | None = None) -> Path:
    """Primary checkout of the repo, also when called from a linked worktree."""
    try:
        common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd)
    except AwError:
        raise AwError("not inside a git repository") from None
    return Path(common).parent


def checkout_root(cwd: Path | str | None = None) -> Path:
    """Top level of the current checkout (the primary one or a linked worktree)."""
    return Path(git("rev-parse", "--show-toplevel", cwd=cwd))


def coerce(key: str, spec: dict, value: Any) -> Any:
    kind = spec["type"]
    ok = {
        "str": isinstance(value, str),
        "choice": isinstance(value, str) and value in spec.get("choices", []),
        "bool": isinstance(value, bool),
        "list": isinstance(value, list) and all(isinstance(v, str) for v in value),
    }[kind]
    if not ok:
        extra = f" (one of {', '.join(spec['choices'])})" if kind == "choice" else ""
        raise AwError(f"{key}: expected {kind}{extra}, got {value!r}")
    return value


def parse_text(key: str, spec: dict, text: str) -> Any:
    """Parse a value given as text (env var, --set, prompt answer)."""
    kind = spec["type"]
    if kind == "bool":
        low = text.strip().lower()
        if low in ("true", "yes", "y", "1"):
            return True
        if low in ("false", "no", "n", "0"):
            return False
        raise AwError(f"{key}: expected true/false, got {text!r}")
    if kind == "list":
        return [v for v in re.split(r"[,\s]+", text.strip()) if v]
    return coerce(key, spec, text.strip())


def expand(value: str, placeholders: dict[str, str]) -> str:
    for name, sub in placeholders.items():
        value = value.replace("{" + name + "}", sub)
    if value == "~" or value.startswith("~/"):
        value = str(Path.home()) + value[1:]
    return value


@dataclass
class Config:
    root: Path
    checkout: Path
    schema: dict[str, Any]
    values: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    file_version: int | None = None
    unknown: list[tuple[str, str]] = field(default_factory=list)

    @property
    def project(self) -> str:
        return self.root.name

    def get(self, key: str, **placeholders: str) -> Any:
        value = self.values[key]
        if not isinstance(value, str):
            return value
        base = {"project": self.project, "repo_parent": str(self.root.parent)}
        return expand(value, base | placeholders)


def read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise AwError(f"{path}: {e}") from None


def load(cwd: Path | str | None = None) -> Config:
    full = load_schema()
    schema = full["keys"]
    cfg = Config(root=repo_root(cwd), checkout=checkout_root(cwd), schema=schema)
    for key, spec in schema.items():
        cfg.values[key] = spec["default"]
        cfg.sources[key] = "default"

    layers = [
        ("user", user_file()),
        ("project", cfg.checkout / PROJECT_FILE),
        ("local", cfg.root / LOCAL_FILE),
    ]
    for layer, path in layers:
        if not path.is_file():
            continue
        data = read_toml(path)
        if layer == "project":
            cfg.file_version = data.get("aw_version")
        for key, value in data.items():
            if key == "aw_version":
                continue
            if key not in schema:
                cfg.unknown.append((layer, key))
                continue
            cfg.values[key] = coerce(key, schema[key], value)
            cfg.sources[key] = layer

    for key, spec in schema.items():
        env = os.environ.get("AW_" + key.upper())
        if env is not None:
            cfg.values[key] = parse_text(key, spec, env)
            cfg.sources[key] = "env"
    return cfg


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def dump_toml(values: dict[str, Any]) -> str:
    return "".join(f"{k} = {toml_value(v)}\n" for k, v in values.items())
