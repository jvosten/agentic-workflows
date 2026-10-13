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
                meta[key.strip()] = value.strip()
    return Entry(
        kind=kind,
        slug=path.stem,
        title=meta.get("title", path.stem),
        tags=list(meta.get("tags", [])),
        status=meta.get("status", "active"),
        superseded_by=meta.get("superseded_by", ""),
        aliases=[str(a) for a in meta.get("aliases", [])],
        date=str(meta.get("date", "")),
        issue=str(meta.get("issue", "")),
        body=body.strip(),
    )


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
    """An entry by slug or alias (a number like 95, an id like D15)."""
    wanted = ref.strip().removeprefix("#").casefold()
    every = entries(cfg)
    for entry in every:
        if entry.slug.casefold() == wanted:
            return entry
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


def add(cfg: Config, kind: str, title: str, text: str, tags: list[str], issue: str | None) -> Path:
    _check_tags(cfg, kind, tags)
    slug = slugify(title)
    path = directory(cfg, kind) / f"{slug}.md"
    if path.exists():
        raise AwError(f"{path.name} exists: same subject? `aw memory supersede {slug}`, or a more specific title")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(Entry(kind, slug, title, tags, date=date.today().isoformat(), issue=issue or "", body=text).text())
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
            sections = d.get("sections") or {}
            body = d.get("body") or "\n\n".join(f"## {k}\n\n{str(v).strip()}" for k, v in sections.items() if v)
            entry = Entry(
                kind,
                d.get("slug") or slugify(title),
                title,
                list(d.get("tags", [])),
                d.get("status", "active"),
                d.get("superseded_by", ""),
                [str(a) for a in d.get("aliases", [])],
                str(d.get("date", "")),
                str(d.get("issue", "")),
                body,
            )
            if entry.status not in STATUSES:
                raise ValueError(f"status must be one of {', '.join(STATUSES)}")
            _check_tags(cfg, kind, entry.tags)
            new.append(entry)
        except (KeyError, ValueError, TypeError, AwError) as e:
            problems.append(f"line {n}: {e}")
    existing = entries(cfg)
    slugs: dict[tuple[str, str], int] = {}
    aliases: dict[str, list[str]] = {}
    for entry in existing + new:
        slugs[(entry.kind, entry.slug)] = slugs.get((entry.kind, entry.slug), 0) + 1
        for alias in entry.aliases:
            aliases.setdefault(alias.casefold(), []).append(entry.slug)
    problems += [
        f'slug {slug!r} ({kind}) used {n} times; give the entries a "slug" or distinct titles'
        for (kind, slug), n in slugs.items()
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
        path = directory(cfg, entry.kind) / f"{entry.slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry.text())
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
