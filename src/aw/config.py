"""Layered project configuration.

Resolution order, later wins:
  schema defaults (schema.toml)
  ~/.agents/aw/config.toml        user, all projects
  <checkout>/.agents/aw.toml      project, committed (current checkout or worktree)
  <primary>/.agents/aw.local.toml machine, gitignored (primary checkout only)
  AW_<KEY> environment variables

A trusted key (schema: trusted = true) decides what runs or merges on the host, or where credentials go. Its project
value comes from the primary checkout's .agents/aw.toml, never from a session worktree's: the branch being merged
does not choose its own merge gate, hooks or credential host. An env-only key (env_only = true) describes where aw
runs, not the project: only AW_<KEY> sets it.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tomllib
from dataclasses import dataclass, field
from functools import cached_property
from importlib import resources
from pathlib import Path
from typing import Any

PROJECT_FILE = ".agents/aw.toml"
LOCAL_FILE = ".agents/aw.local.toml"
# Where hooks and direnv print: the process's stderr by descriptor. sys.stderr as stdout= needs its fileno(), which
# a replaced sys.stderr (pytest capsys, an embedding host) lacks. stdout stays free for the key=value contract.
STDERR_FD = 2


class AwError(Exception):
    pass


def load_schema() -> dict[str, Any]:
    return tomllib.loads(resources.files("aw").joinpath("schema.toml").read_text())


def user_file() -> Path:
    return Path.home() / ".agents/aw/config.toml"


NETWORK = {"fetch": 120, "ls-remote": 120, "push": 600}  # seconds; a push may run hooks


def git(*args: str, cwd: Path | str | None = None) -> str:
    if cwd is not None and not Path(cwd).is_dir():  # subprocess would raise FileNotFoundError, past every handler
        raise AwError(f"git {' '.join(args)}: no such directory: {cwd}")
    limit = NETWORK.get(args[0]) if args else None
    env = os.environ | {"GIT_TERMINAL_PROMPT": "0"}
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False, timeout=limit, env=env)
    except subprocess.TimeoutExpired:
        raise AwError(f"git {' '.join(args)}: timed out after {limit} s") from None
    if r.returncode:
        raise AwError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def json_pages(text: str) -> list[Any]:
    """The documents of `gh api --paginate` or `glab api --paginate` output: one JSON value per page, concatenated."""
    decoder, pages, pos = json.JSONDecoder(), [], 0
    while (pos := len(text) - len(text[pos:].lstrip())) < len(text):
        page, pos = decoder.raw_decode(text, pos)
        pages.append(page)
    return pages


def worktrees(root: Path) -> list[dict[str, str]]:
    """`git worktree list --porcelain`, one entry per worktree: worktree (its path), HEAD, branch (a ref).

    A worktree whose directory was deleted without `git worktree remove` stays listed until `git worktree prune`.
    """
    entries = []
    for block in git("worktree", "list", "--porcelain", cwd=root).split("\n\n"):
        entry = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            entry[key] = value
        entries.append(entry)
    return entries


def fast_forward(root: Path, branch: str) -> str:
    """Bring the local branch up to origin's, whatever the primary checkout has checked out.

    Where the branch is checked out (the primary checkout or any worktree), a fast-forward merge there keeps
    that checkout's files in step; elsewhere only the ref moves. A branch ahead of origin stays; one that
    diverged fails, never moves back.
    """
    git("fetch", "--quiet", "origin", branch, cwd=root)
    ref, upstream = f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"
    where = None
    for entry in worktrees(root):
        if entry.get("branch") == ref and Path(entry["worktree"]).is_dir():
            where = entry["worktree"]
    if where:
        try:
            git("merge", "--ff-only", "--quiet", upstream, cwd=where)
        except AwError as e:  # uncommitted changes the update would overwrite; git touched nothing
            raise AwError(
                f"cannot update {branch} in {where}: commit or stash the changes there, then retry\n{e}"
            ) from None
        return f"updated {branch} in {where}"
    local, remote = git("rev-parse", ref, cwd=root), git("rev-parse", upstream, cwd=root)
    if local == remote:
        return f"{branch} up to date"
    if _is_ancestor(root, local, remote):
        git("update-ref", ref, remote, local, cwd=root)
        return f"updated {branch}"
    if _is_ancestor(root, remote, local):
        return f"{branch} is ahead of origin/{branch}; left as it is"
    raise AwError(f"{branch} and origin/{branch} have diverged; reconcile them in {root} first")


def _is_ancestor(root: Path, older: str, newer: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], cwd=root, check=False).returncode == 0


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
        "table": isinstance(value, dict) and all(isinstance(v, str) for v in value.values()),
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
    if kind == "table":
        table = {}
        for item in filter(None, (p.strip() for p in text.split(","))):
            name, sep, value = item.partition("=")
            if not sep or not name.strip():
                raise AwError(f"{key}: expected name=value[,name=value...], got {text!r}")
            table[name.strip()] = value.strip()
        return table
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
    migrated: list[tuple[str, str]] = field(default_factory=list)  # layer, note: migrations applied in memory only
    ignored: list[str] = field(default_factory=list)  # trusted keys the worktree's project file sets differently
    misplaced: list[tuple[str, str]] = field(default_factory=list)  # layer, key: env-only keys set in a file

    @property
    def project(self) -> str:
        return self.root.name

    def get(self, key: str, **placeholders: str) -> Any:
        value = self.values[key]
        return self.expand(value, **placeholders) if isinstance(value, str) else value

    def command(self, key: str, **placeholders: str) -> str:
        """A hook's shell command: every placeholder value shell-quoted, so each arrives as one argument."""
        base = {"project": self.project, "repo_parent": str(self.root.parent)}
        return expand(self.values[key], {k: shlex.quote(v) for k, v in (base | placeholders).items()})

    def expand(self, template: str, **placeholders: str) -> str:
        base = {"project": self.project, "repo_parent": str(self.root.parent)}
        return expand(template, base | placeholders)

    def on_host(self, command: str) -> None:
        """Refuse a command that merges or closes when aw runs sandboxed: the host runs it, with its own config."""
        if self.values["sandboxed"]:
            raise AwError(f"sandboxed: {command} runs on the host; push the branch and run it there")

    def public(self, *texts: str | None) -> None:
        """Refuse a text that names a private term: what aw publishes reaches the tracker, the forge or the repo."""
        for term in self.values["private_terms"]:
            if any(text and term.casefold() in text.casefold() for text in texts):
                raise AwError(
                    f"the text names the private term {term!r} ({self.sources['private_terms']}); reword it, "
                    "nothing was written or sent"
                )

    def inside(self, key: str, path: Path, base: Path | None = None) -> Path:
        """path, built from a path key, if it stays under base (the checkout by default), out of the git dir, and
        through no link out: a committed symlink must not take aw's reads and writes elsewhere. Only an absolute or
        ~ value from the user or local layer or the environment may point anywhere: the user wrote it, no branch.
        (Stopgap: the refactor plan's S4a puts every project file behind one component.)"""
        base = base or self.checkout
        if self.sources.get(key) not in (None, "default", "project") and not path.is_relative_to(base):
            return path
        resolved = path.resolve()
        if not resolved.is_relative_to(base.resolve()):
            raise AwError(f"{key}: {path} resolves outside the repo; aw follows no link out of it")
        if any(resolved.is_relative_to(git_dir) for git_dir in self.git_dirs):
            raise AwError(f"{key}: {path} resolves into the git dir; aw never reads or writes there")
        return path

    @cached_property
    def git_dirs(self) -> tuple[Path, ...]:
        """The checkout's git dir and the repository's common one (they differ in a linked worktree)."""
        dirs = ("--absolute-git-dir", "--git-common-dir")
        return tuple(Path(git("rev-parse", "--path-format=absolute", d, cwd=self.checkout)).resolve() for d in dirs)


def read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise AwError(f"{path}: {e}") from None


QUOTED_PLACEHOLDER = re.compile(r"""(["'])(\{\w+\})\1""")  # "{x}" or '{x}' in a hook


def migrate(data: dict[str, Any], migrations: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    """One config file's data with the pending migrations applied, and a note for each one applied.

    A step renames a key (optionally rewriting its value), or unquotes placeholders in hooks. A new key already set
    in the same file wins over a renamed old one: the old one is dropped.
    """
    data, notes = dict(data), []
    for step in migrations:
        if "unquote" in step:
            for key in step["unquote"]:
                value = data.get(key)
                if isinstance(value, str) and (bare := QUOTED_PLACEHOLDER.sub(r"\2", value)) != value:
                    data[key] = bare
                    notes.append(f"{key}: quotes around placeholders removed, {step['note']}")
            continue
        old, new = step["rename"], step["to"]
        if old not in data:
            continue
        value = data.pop(old)
        notes.append(f"{old} → {new}" + (f", {step['note']}" if step.get("note") else ""))
        if new in data:
            continue
        rewrite = step.get("rewrite")
        data[new] = rewrite.replace("{value}", value) if rewrite and isinstance(value, str) else value
    return data, notes


def load(cwd: Path | str | None = None) -> Config:
    full = load_schema()
    schema, migrations = full["keys"], full.get("migrations", [])
    cfg = Config(root=repo_root(cwd), checkout=checkout_root(cwd), schema=schema)
    for key, spec in schema.items():
        cfg.values[key] = spec["default"]
        cfg.sources[key] = "default"

    layers = [
        ("user", user_file()),
        ("project", cfg.checkout / PROJECT_FILE),
        ("local", cfg.root / LOCAL_FILE),
    ]
    from_primary: set[str] = set()
    for layer, path in layers:
        data, notes = _read_layer(path, migrations)
        cfg.migrated += [(layer, note) for note in notes]
        if layer == "project":
            cfg.file_version = data.get("aw_version")
            if cfg.checkout != cfg.root:  # a session worktree: the trusted keys come from the primary checkout
                data, from_primary = _trust_primary(cfg, data, _read_layer(cfg.root / PROJECT_FILE, migrations)[0])
        for key, value in data.items():
            if key == "aw_version":
                continue
            if key not in schema:
                cfg.unknown.append((layer, key))
                continue
            if schema[key].get("env_only"):
                cfg.misplaced.append((layer, key))
                continue
            if schema[key].get("local_only") and layer == "project":
                raise AwError(
                    f"{key} in {PROJECT_FILE}: a committed value is published; set it in ~/.agents/aw/config.toml or "
                    f"{LOCAL_FILE}"
                )
            cfg.values[key] = coerce(key, schema[key], value)
            cfg.sources[key] = "primary" if layer == "project" and key in from_primary else layer
            if layer == "project" and schema[key].get("path"):
                refuse_outside(cfg, key, value)

    for key, spec in schema.items():
        env = os.environ.get("AW_" + key.upper())
        if env is not None:
            cfg.values[key] = parse_text(key, spec, env)
            cfg.sources[key] = "env"
    return cfg


def refuse_outside(cfg: Config, key: str, value: str | dict[str, str]) -> None:
    """A committed path stays in the repo: a branch can change it, and aw reads, writes and deletes there."""
    named = value.items() if isinstance(value, dict) else [("", value)]
    for name, text in named:
        path = cfg.expand(text)
        if path.startswith("~") or Path(path).is_absolute() or Path(os.path.normpath(path)).parts[:1] == ("..",):
            shown = f"{key}.{name}" if name else key
            raise AwError(
                f"{shown} = {text!r} in project points outside the repo; name a path outside it in the user or "
                f"local config (~/.agents/aw/config.toml, {LOCAL_FILE})"
            )


def _read_layer(path: Path, migrations: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    return migrate(read_toml(path), migrations) if path.is_file() else ({}, [])


def _trust_primary(cfg: Config, branch: dict[str, Any], primary: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """The worktree's project data with every trusted key taken from the primary checkout's, and the keys taken.

    Differences are noted in cfg.ignored.
    """
    data, taken = dict(branch), set()
    for key, spec in cfg.schema.items():
        if not spec.get("trusted"):
            continue
        if branch.get(key, spec["default"]) != primary.get(key, spec["default"]):
            cfg.ignored.append(key)
        data.pop(key, None)
        if key in primary:
            data[key] = primary[key]
            taken.add(key)
    return data, taken


BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def toml_value(value: Any) -> str:
    if isinstance(value, dict):
        items = ", ".join(f"{k if BARE_KEY.match(k) else json.dumps(k)} = {toml_value(v)}" for k, v in value.items())
        return "{ " + items + " }" if items else "{}"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def dump_toml(values: dict[str, Any]) -> str:
    return "".join(f"{k} = {toml_value(v)}\n" for k, v in values.items())
