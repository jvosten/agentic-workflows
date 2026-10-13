"""Project memory: decisions and gotchas, one committed file per entry.

  <memory_dir>/gotchas/<slug>.md      external tool behavior: symptom, cause, fix
  <memory_dir>/decisions/<slug>.md    what the project settled, and why
  <memory_dir>/tags.toml              the tag vocabulary: tag = "what it covers"

The slug is the permanent id. Numbers of imported entries live on as aliases, so old citations resolve.
Entries are retired, never deleted. Frontmatter values are JSON, which is valid YAML: GitHub renders it.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from aw.config import AwError, Config

KINDS = {"gotcha": "gotchas", "decision": "decisions"}
STATUSES = ("active", "retired")
FIELDS = ("title", "tags", "status", "superseded_by", "aliases", "date", "issue")
LOG = ".agents/gotchas-experiment.log"
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # what slugify produces: the file name, so never a path
KNOWN_GOTCHAS = "## Known gotchas"


@dataclass
class Entry:
    kind: str
    slug: str
    title: str
    tags: list[str] = field(default_factory=list)
    status: str = "active"
    superseded_by: str = ""
    aliases: list[str] = field(default_factory=list)
    date: str = ""
    issue: str = ""
    body: str = ""

    def text(self) -> str:
        meta = {
            "title": self.title,
            "tags": self.tags,
            "status": self.status,
            "superseded_by": self.superseded_by,
            "aliases": self.aliases,
            "date": self.date,
            "issue": self.issue,
        }
        lines = [
            f"{key}: {json.dumps(meta[key], ensure_ascii=False)}"
            for key in FIELDS
            if meta[key] or key in ("title", "tags", "status")
        ]
        return "---\n" + "\n".join(lines) + "\n---\n\n" + self.body.strip() + "\n"

    def compact(self) -> str:
        retired = f" (retired → {self.superseded_by or 'nothing'})" if self.status == "retired" else ""
        return f"{self.slug} · {self.title}{retired}"


def directory(cfg: Config, kind: str) -> Path:
    if kind not in KINDS:
        raise AwError(f"unknown memory kind: {kind} (known: {', '.join(KINDS)})")
    return cfg.checkout / cfg.get("memory_dir") / KINDS[kind]


def slugify(title: str) -> str:
    words = re.findall(r"[a-z0-9]+", title.casefold())
    slug = ""
    for word in words:
        if len(slug) + len(word) + 1 > 60:
            break
        slug = f"{slug}-{word}" if slug else word
    if not slug:
        raise AwError(f"no slug from title {title!r}")
    return slug


def _entry(kind: str, slug: str, meta: dict[str, Any], body: str) -> Entry:
    """An entry from decoded frontmatter or an import line. A field of the wrong type raises ValueError naming it:
    a YAML list (`tags: [git, gh]`) is text, and read as a list it would split into characters."""

    def text(key: str, numbers: bool = False) -> str:
        value = meta.get(key)
        if value is None:
            return ""
        if numbers and isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string, not {value!r}")
        return value

    def strings(key: str, numbers: bool = False) -> list[str]:
        value = meta.get(key) or []
        kinds = (str, int) if numbers else (str,)
        if not isinstance(value, list) or not all(isinstance(v, kinds) and not isinstance(v, bool) for v in value):
            raise ValueError(f'{key} must be a JSON list of strings, like ["git", "gh"], not {value!r}')
        return [str(v) for v in value]

    title = text("title") or slug
    status = text("status") or "active"
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}, not {status!r}")
    return Entry(
        kind=kind,
        slug=slug,
        title=title,
        tags=strings("tags"),
        status=status,
        superseded_by=text("superseded_by"),
        aliases=strings("aliases", numbers=True),
        date=text("date"),
        issue=text("issue", numbers=True),
        body=body.strip(),
    )


def parse(path: Path, kind: str) -> Entry:
    text = path.read_text()
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise AwError(f"{path}: no frontmatter")
    head, body = text[4:].split("\n---\n", 1)
    meta: dict[str, Any] = {}
    for line in head.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in FIELDS:
            try:
                meta[key.strip()] = json.loads(value.strip())
            except json.JSONDecodeError:
                meta[key.strip()] = value.strip()  # an unquoted title is text; the field check catches a YAML list
    try:
        return _entry(kind, path.stem, meta, body)
    except ValueError as e:
        raise AwError(f"{path}: {e}") from None


def entries(cfg: Config, kind: str | None = None) -> list[Entry]:
    found = []
    for name in [kind] if kind else KINDS:
        root = directory(cfg, name)
        found += [parse(p, name) for p in sorted(root.glob("*.md"))] if root.is_dir() else []
    return found


def vocabulary(cfg: Config) -> dict[str, str]:
    path = cfg.checkout / cfg.get("memory_dir") / "tags.toml"
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise AwError(f"{path}: {e}") from None
    return {str(k): str(v) for k, v in data.items()}


def resolve(cfg: Config, ref: str) -> Entry:
    """An entry by slug or alias (a number like 95, an id like D15). A slug in both kinds is refused, never picked."""
    wanted = ref.strip().removeprefix("#").casefold()
    every = entries(cfg)
    same = sorted((e for e in every if e.slug.casefold() == wanted), key=lambda e: e.kind)
    if len(same) > 1:
        raise AwError(f"{same[0].slug} is both a {same[0].kind} and a {same[1].kind}; rename one, aw doctor lists it")
    if same:
        return same[0]
    hits = [e for e in every if wanted in (a.casefold() for a in e.aliases)]
    if not hits:
        raise AwError(f"no memory entry {ref!r} (slug or alias)")
    if len(hits) > 1:
        raise AwError(f"alias {ref!r} is claimed by {', '.join(e.slug for e in hits)}; aw doctor lists it")
    return hits[0]


def _check_tags(cfg: Config, kind: str, tags: list[str]) -> None:
    vocab = vocabulary(cfg)
    if kind == "gotcha" and not tags:
        raise AwError("a gotcha needs at least one tag: the tool it is about (--tags)")
    unknown = [t for t in tags if t not in vocab]
    if unknown:
        where = cfg.get("memory_dir") + "/tags.toml"
        raise AwError(f"unknown tag(s): {', '.join(unknown)}; add them to {where} first, with a one-line description")


def _taken(cfg: Config, slug: str) -> str | None:
    """The kind that already holds this slug: slugs are unique across decisions and gotchas."""
    return next((kind for kind in KINDS if (directory(cfg, kind) / f"{slug}.md").exists()), None)


def add(cfg: Config, kind: str, title: str, text: str, tags: list[str], issue: str | None) -> Path:
    _check_tags(cfg, kind, tags)
    slug = slugify(title)
    path = directory(cfg, kind) / f"{slug}.md"
    if (taken := _taken(cfg, slug)) == kind:
        raise AwError(f"{path.name} exists: same subject? `aw memory supersede {slug}`, or a more specific title")
    if taken:
        raise AwError(f"{slug} exists as a {taken}; slugs are unique across kinds: a more specific title")
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = Entry(kind, slug, title, tags, date=date.today().isoformat(), issue=issue or "", body=text)
    with path.open("x") as handle:  # exclusive: never overwrite an entry written in the meantime
        handle.write(entry.text())
    return path


def find(cfg: Config, kind: str | None, tags: list[str], terms: list[str], retired: bool) -> list[Entry]:
    """Entries with any of the tags and all of the terms (case-insensitive, title, body, tags and aliases)."""
    found = []
    for entry in entries(cfg, kind):
        if entry.status == "retired" and not retired:
            continue
        if tags and not set(tags) & set(entry.tags):
            continue
        haystack = " ".join([entry.title, entry.body, *entry.tags, *entry.aliases]).casefold()
        if all(term.casefold() in haystack for term in terms):
            found.append(entry)
    return found


def tag_counts(cfg: Config) -> list[tuple[str, int, str]]:
    """Every tag of the vocabulary with its number of active gotchas, most first."""
    vocab = vocabulary(cfg)
    counts = dict.fromkeys(vocab, 0)
    for entry in entries(cfg, "gotcha"):
        if entry.status == "active":
            for tag in entry.tags:
                counts[tag] = counts.get(tag, 0) + 1
    return sorted(((t, n, vocab.get(t, "")) for t, n in counts.items()), key=lambda r: (-r[1], r[0]))


def supersede(cfg: Config, ref: str, reason: str, by: str | None) -> Path:
    entry = resolve(cfg, ref)
    if by:
        successor = resolve(cfg, by)
        by = successor.slug
    entry.status, entry.superseded_by = "retired", by or ""
    entry.body = entry.body.rstrip() + f"\n\n_Retired {date.today().isoformat()}: {reason}_"
    path = directory(cfg, entry.kind) / f"{entry.slug}.md"
    path.write_text(entry.text())
    return path


def import_json(cfg: Config, lines: list[str]) -> list[Path]:
    """Validate every entry first, then write them all; one bad line writes nothing."""
    new: list[Entry] = []
    problems: list[str] = []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            kind, title = d["kind"], d["title"]
            if kind not in KINDS:
                raise ValueError(f"kind must be one of {', '.join(KINDS)}")
            if not isinstance(title, str):
                raise ValueError(f"title must be a string, not {title!r}")
            slug = d.get("slug") or slugify(title)
            if not isinstance(slug, str) or not SLUG.match(slug):
                raise ValueError(f"slug {slug!r} must be lowercase words joined by '-', like a title's slug")
            sections = d.get("sections") or {}
            if not isinstance(sections, dict):
                raise ValueError("sections must map a heading to its text")
            body = d.get("body") or "\n\n".join(f"## {k}\n\n{str(v).strip()}" for k, v in sections.items() if v)
            entry = _entry(kind, slug, {key: d.get(key) for key in FIELDS}, str(body))
            _check_tags(cfg, kind, entry.tags)
            new.append(entry)
        except (KeyError, ValueError, TypeError, AwError) as e:
            problems.append(f"line {n}: {e}")
    existing = entries(cfg)
    held = {e.slug: e.kind for e in existing}
    counts: dict[str, int] = {}
    aliases: dict[str, list[str]] = {}
    for entry in new:
        counts[entry.slug] = counts.get(entry.slug, 0) + 1
    for entry in existing + new:
        for alias in entry.aliases:
            aliases.setdefault(alias.casefold(), []).append(entry.slug)
    problems += [f"{slug} exists as a {held[slug]}; import never overwrites" for slug in counts if slug in held]
    problems += [
        f'slug {slug!r} used {n} times in the import; give the entries a "slug" or distinct titles'
        for slug, n in counts.items()
        if n > 1
    ]
    problems += [f"alias {a!r} claimed by {', '.join(owners)}" for a, owners in aliases.items() if len(owners) > 1]
    known = {e.slug for e in existing + new}
    problems += [
        f"{e.slug}: superseded_by {e.superseded_by!r} does not exist"
        for e in new
        if e.superseded_by and e.superseded_by not in known
    ]
    if problems:
        shown = problems[:20] + ([f"… {len(problems) - 20} more"] if len(problems) > 20 else [])
        raise AwError("import refused, nothing written:\n  " + "\n  ".join(shown))
    written = []
    for entry in new:
        root = directory(cfg, entry.kind)
        path = root / f"{entry.slug}.md"
        if not path.resolve().is_relative_to(root.resolve()):  # SLUG already rules it out; the write must not trust it
            raise AwError(f"{entry.slug}: outside {root}")
        root.mkdir(parents=True, exist_ok=True)
        with path.open("x") as handle:
            handle.write(entry.text())
        written.append(path)
    return written


# --- what a session loads, and the experiment's log ---------------------------------------


def start_text(cfg: Config, has_plan: bool) -> str:
    """What a session start reads: gotchas per gotchas_load, the decision index when there is no plan."""
    parts = []
    if cfg.get("gotchas_load") == "tags":
        counts = [f"{t} {n}" for t, n, _ in tag_counts(cfg) if n]
        if counts:
            parts.append(
                "Known gotchas by tool. Before working with one of these, or when it errors: "
                "`aw memory find --tags <tag> --compact`, then `aw memory show <id>`.\n" + " · ".join(counts)
            )
    else:
        active = [e for e in entries(cfg, "gotcha") if e.status == "active"]
        if active:
            parts.append("# Gotchas\n\n" + "\n\n".join(f"## {e.title}\n\n{e.body}" for e in active))
    if not has_plan:
        decisions = [e.compact() for e in entries(cfg, "decision") if e.status == "active"]
        if decisions:
            parts.append(
                "Decisions in force (`aw memory show <id>` for one; do not reopen them):\n"
                + "\n".join(f"- {line}" for line in decisions)
            )
    return "\n\n".join(parts)


def tokens(text: str) -> int:
    """Rough token count: four characters per token."""
    return (len(text) + 3) // 4


def pulled(plan_file: Path | None) -> list[str]:
    """Gotcha ids the plan lists under Known gotchas."""
    if not plan_file or not plan_file.is_file():
        return []
    lines = plan_file.read_text().splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == KNOWN_GOTCHAS)
    except StopIteration:
        return []
    ids = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if m := re.match(r"^- ([a-z0-9-]+) · ", line):
            ids.append(m.group(1))
    return ids


def log(
    cfg: Config, meta: dict[str, Any], plan_file: Path | None, relevant: list[str], missed: list[str], note: str
) -> Path:
    """One line per session for the experiment, in the primary checkout so it outlives the worktree."""
    ids = pulled(plan_file)
    record = {
        "date": date.today().isoformat(),
        "issue": meta.get("issue") or "",
        "mode": cfg.get("gotchas_load"),
        "start_tokens": meta.get("memory_start_tokens"),
        "pulled": len(ids),
        "relevant": relevant,
        "relevant_pulled": [r for r in relevant if r in ids],
        "missed": missed,
        "note": note,
    }
    path = cfg.root / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
