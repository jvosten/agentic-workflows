"""aw: command-line entry point."""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from aw import (
    __version__,
    backlog,
    doctor,
    finish,
    forge,
    init,
    install,
    memory,
    plan,
    restack,
    rollup,
    session,
    start_task,
    templates,
    trackers,
    ui,
    update,
)
from aw.config import PROJECT_FILE, AwError, Config, git, load, toml_value
from aw.trackers import STATUSES


def _config(args: argparse.Namespace) -> None:
    cfg = load()
    if args.get:
        if args.get not in cfg.values:
            raise AwError(f"unknown key: {args.get}")
        value = cfg.get(args.get)
        print(" ".join(value) if isinstance(value, list) else toml_value(value).strip('"'))
        return
    print(f"project = {toml_value(cfg.project)}")
    for key in cfg.values:
        line = f"{key} = {toml_value(cfg.get(key))}"
        print(f"{line:<60} # {cfg.sources[key]}" if args.sources else line)


def _start_task(args: argparse.Namespace) -> None:
    for key, value in start_task.run(load(), args.type, args.slug, args.issue, args.base).items():
        print(f"{key}={value}")


def _rows(rows: list[trackers.Row], as_json: bool) -> None:
    if as_json:
        print(json.dumps([vars(r) for r in rows], indent=2))
        return
    print("\n".join(trackers.rows_line(r) for r in rows) or "no issues")


def _body(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text()


DUPES_FETCH = 50  # hits fetched per term; only the printed list follows --limit, so a small cap misses nothing


def _dupes(rows: list[trackers.Row], limit: int, as_json: bool) -> None:
    """Hits in the tree always; elsewhere only the best-ranked up to limit rows in all, plus a count of the rest."""
    tree = [r for r in rows if r.scope != "elsewhere"]
    elsewhere = [r for r in rows if r.scope == "elsewhere"]
    keep = elsewhere[: max(limit - len(tree), 0)]
    _rows(tree + keep, as_json)
    if len(keep) < len(elsewhere) and not as_json:
        print(f"… {len(elsewhere) - len(keep)} more elsewhere, matching fewer terms (--limit raises the cap)")


def _issue(args: argparse.Namespace) -> None:
    cfg = load()
    tracker = trackers.get(cfg)
    op = args.op
    if op in ("list", "search"):
        rows = tracker.list_open(args.limit) if op == "list" else tracker.search(args.query, args.limit, args.raw)
        _rows(rows, args.json)
        return
    if op == "create":
        body = _body(args.body_file)
        if args.field and not tracker.has_fields():
            raise AwError(f"--field: tracker {tracker.name!r} has no board fields (GitHub with github_project has)")
        fields = trackers.board_fields(cfg, args.label, args.field, from_labels=tracker.has_fields())
        if tracker.has_fields() and (missing := trackers.missing_fields(cfg, fields)):
            wanted = "; ".join(f"{n} ({', '.join(o)})" for n, o in map(tracker.field_options, missing))
            raise AwError(f"board_required: no value for {wanted}; pass --field Name=Option for each, nothing created")
        if args.dry_run:
            print(
                f"DRY RUN ({tracker.name}): title={args.title!r} parent={args.parent} type={args.type} "
                f"labels={','.join(args.label) or None} status={args.status or 'default'} "
                f"fields={','.join(f'{n}={v}' for n, v in fields.items()) or None}"
            )
            print(f"body: {len(body.splitlines())} lines")
            return
        new = tracker.create(args.title, body, args.parent, args.type, args.label, args.status, fields)
        print(tracker.ref(new))
        return
    if op == "dupes" and args.id is None:
        if args.tree_only:
            raise AwError("issue dupes: --tree-only needs a parent")
        _dupes(tracker.dupes(None, args.terms, DUPES_FETCH), args.limit, args.json)
        return
    issue = tracker.normalize(args.id)
    if op == "view":
        data = tracker.view(issue)
        text = json.dumps(asdict(data), indent=2) if args.json else trackers.render(data)
        if args.out:
            out = Path(args.out) / f"{issue}.{'json' if args.json else 'md'}"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text)
            print(out)
        else:
            print(text, end="")
    elif op == "children":
        _rows(tracker.text_children(issue) if args.text_only else tracker.children(issue), args.json)
    elif op == "set-parent":
        if (args.parent is None) == (not args.none):
            raise AwError("issue set-parent: pass a parent id or --none")
        parent = None if args.none else tracker.normalize(args.parent)
        if parent == issue:
            raise AwError(f"{tracker.ref(issue)} cannot be its own parent")
        if args.dry_run:
            current = tracker.parent(issue)
            was = f"{tracker.ref(current.id)} ({current.link} link)" if current else "none"
            print(
                f"DRY RUN ({tracker.name}): {tracker.ref(issue)} parent {was} -> "
                f"{tracker.ref(parent) if parent else 'none'}"
            )
            return
        print(tracker.set_parent(issue, parent))
    elif op == "dupes":
        rows = tracker.dupes(issue, args.terms, DUPES_FETCH, args.tree_only)
        _dupes(rows, args.limit, args.json)
        if not tracker.scoped():
            print(f"note: {tracker.name} has no parent links; searched the whole project", file=sys.stderr)
    elif op == "comment":
        tracker.comment(issue, _body(args.body_file))
        print(f"commented on {tracker.ref(issue)}")
    elif op == "update":
        body = _body(args.body_file) if args.body_file else None
        if args.title is None and body is None:
            raise AwError("issue update: pass --title, --body-file, or both")
        if args.dry_run:
            print(f"DRY RUN ({tracker.name}): update {tracker.ref(issue)} title={args.title!r}")
            print(body if body is not None else "body: unchanged", end="" if body else "\n")
            return
        tracker.update(issue, args.title, body)
        print(f"updated {tracker.ref(issue)}")
    elif op == "set-status":
        print(tracker.set_status(issue, args.status))
        if message := trackers.status_hook(cfg, issue, args.status):
            print(message)
    elif op == "set-field":
        print(tracker.set_fields(issue, trackers.board_fields(cfg, [], args.pairs)))
    elif op == "rollup":
        if args.close:
            print("\n".join(rollup.close(cfg, tracker, issue)))
        elif args.json:
            print(
                json.dumps(rollup.data(tracker, issue, rollup.check(cfg, tracker, issue)), indent=2, ensure_ascii=False)
            )
        else:
            print(rollup.report(tracker, issue, rollup.check(cfg, tracker, issue)))
    elif op == "ref":
        print(tracker.ref(issue))
    elif op == "pr-text":
        print(tracker.pr_text(issue))


MR_PREFIX = {"github": "#", "gitlab": "!"}


CLOSING = r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s+"  # GitHub's and GitLab's closing keywords


def _closes_in(tracker: trackers.Tracker, issue: str, body: str) -> bool:
    """Whether the body already closes exactly this issue: a closing keyword right before its reference.

    Trackers whose reference itself links (pr_text == ref, Jira) need the exact reference. A bare mention
    (`see #12`) or a longer number (`#123`) does not count.
    """
    ref = re.escape(tracker.ref(issue)) + r"(?![\w-])"
    if tracker.pr_text(issue) == tracker.ref(issue):
        return re.search(r"(?<![\w-])" + ref, body) is not None
    return re.search(CLOSING + ref, body, re.IGNORECASE) is not None


def _session_issue(cfg: Config) -> str:
    try:
        issue = session.read().get("issue") or ""
    except session.NoSession:
        return ""
    return issue if cfg.get("tracker") != "none" else ""


def _issue_lines(cfg: Config, body: str, part: int | None, earlier: list[str]) -> list[str]:
    """Lines that tie the request to the session: the issue (closing it only on the last part), earlier parts."""
    lines = []
    if issue := _session_issue(cfg):
        tracker = trackers.get(cfg)
        if part:
            lines.append(f"Refs {tracker.ref(issue)} (part {part})")
        elif not _closes_in(tracker, issue, body):
            lines.append(tracker.pr_text(issue))
    if earlier and not part:
        lines.append(f"Earlier parts: {', '.join(earlier)}")
    return [line for line in lines if line not in body]


def _check_closes(cfg: Config, kind: str, shown: str, number: str, part: int | None) -> None:
    """Compare what the request will close with the session issue: missing is an error, any other a warning.

    Only where the forge closes the tracker's issues (both GitHub, or both GitLab). The request exists either way.
    """
    issue = _session_issue(cfg)
    if not issue or cfg.get("tracker") != kind:
        return
    tracker = trackers.get(cfg)
    closed = forge.closes(kind, number, cfg.checkout)
    for other in closed:
        if other != issue:
            print(
                f"warning: {shown} also closes #{other}; reword the phrase that names it "
                f'("Closed: #{other}" counts as a closing keyword)',
                file=sys.stderr,
            )
    if part and issue in closed:
        print(
            f"warning: {shown} is part {part} but closes {tracker.ref(issue)}; only the last part closes it",
            file=sys.stderr,
        )
    if not part and issue not in closed:
        raise AwError(
            f"{shown} does not close {tracker.ref(issue)}: its description needs '{tracker.pr_text(issue)}' "
            "(aw mr update adds it)"
        )


def _target(cfg: Config) -> str:
    """The session's base while it is stacked, else main_branch."""
    try:
        return session.read().get("base") or cfg.get("main_branch")
    except session.NoSession:
        return cfg.get("main_branch")


def _mr(args: argparse.Namespace) -> int:
    cfg = load()
    kind = cfg.get("forge")
    if kind not in MR_PREFIX:
        raise AwError(f"forge = {kind}: no merge requests (set forge in aw init)")
    cwd, mark = cfg.checkout, MR_PREFIX[kind]
    branch = git("branch", "--show-current", cwd=cwd)
    ref = getattr(args, "ref", None) or branch
    if args.op == "create":
        if branch == cfg.get("main_branch"):
            raise AwError(f"on {branch}: create the merge request from the session branch")
        body = _body(args.body_file)
        expect = args.expect.removeprefix(mark) if args.expect else None
        if expect is not None and not expect.isdigit():
            raise AwError(f"--expect takes a request number, got {args.expect!r}")
        target = _target(cfg)
        done = [f"{mark}{r.number}" for r in forge.merged(kind, branch, cwd)]
        part = len(done) + 1 if args.part else None
        if lines := _issue_lines(cfg, body, part, done):
            body = body.rstrip() + "\n\n" + "\n".join(lines) + "\n"
        if args.dry_run:
            print(
                f"DRY RUN ({kind}): {branch} → {target} title={args.title!r} draft={args.draft}"
                + (f" part={part}" if part else "")
            )
            print(body, end="" if body.endswith("\n") else "\n")
            if expect and (upcoming := forge.next_number(kind, cwd)) != expect:
                print(f"expect {mark}{expect}, but the next request is {mark}{upcoming}")
            return 0
        try:
            unpushed = git("rev-list", "--count", "@{upstream}..HEAD", cwd=cwd)
        except AwError:
            raise AwError(f"{branch} has no upstream; push it first: git push -u origin {branch}") from None
        if unpushed != "0":
            raise AwError(f"{branch} has {unpushed} unpushed commit(s); push first")
        if existing := forge.find_open(kind, branch, cwd):
            print(f"{mark}{existing.number} already open: {existing.url} (aw mr update changes it)")
            return 0
        if expect and (upcoming := forge.next_number(kind, cwd)) != expect:  # moved since: nothing is created
            raise AwError(
                f"the next request is {mark}{upcoming}, not {mark}{expect}: fix the entry that names {mark}{expect}, "
                f"push, then create with --expect {upcoming}"
            )
        made = forge.create(kind, branch, target, args.title, body, args.draft, cwd)
        print(f"{mark}{made.number} {made.url}")
        raced = expect is not None and made.number != expect
        if raced:  # another request or issue took the number between the check and the create
            print(
                f"error: {mark}{made.number} opened, not {mark}{expect} (--expect): change {mark}{expect} to "
                f"{mark}{made.number} where it names this request, and push",
                file=sys.stderr,
            )
        _check_closes(cfg, kind, f"{mark}{made.number}", made.number, part)
        return 1 if raced else 0
    if args.op == "next":
        print(f"{mark}{forge.next_number(kind, cwd)}")
    elif args.op == "update":
        body = _body(args.body_file) if args.body_file else None
        if args.title is None and body is None:
            raise AwError("mr update: pass --title, --body-file, or both")
        part = None
        if body is not None and (issue := _session_issue(cfg)):
            # keep what create appended: the part reference of a part request, else the closing line
            refs = re.search(
                rf"^Refs {re.escape(trackers.get(cfg).ref(issue))} \(part (\d+)\)", forge.body(kind, ref, cwd), re.M
            )
            part = int(refs.group(1)) if refs else None
            done = [] if part else [f"{mark}{r.number}" for r in forge.merged(kind, branch, cwd)]
            if lines := _issue_lines(cfg, body, part, done):
                body = body.rstrip() + "\n\n" + "\n".join(lines) + "\n"
        if args.dry_run:
            print(f"DRY RUN ({kind}): update {ref} title={args.title!r}")
            print(body if body is not None else "body: unchanged", end="" if body else "\n")
            return 0
        forge.update(kind, ref, args.title, body, cwd)
        print(f"updated {ref}")
        if body is not None:
            _check_closes(cfg, kind, f"{mark}{ref}" if ref.isdigit() else ref, ref, part)
    elif args.op == "checks":
        results = forge.checks(kind, ref, cwd, args.watch)
        expected = None if results else forge.ci_file(kind, cwd)
        print(_checks_line(results, expected))
        for c in results:
            if c.bucket in ("fail", "pending") or args.verbose:
                print(f"  {c.bucket:<8}{c.name}")
        buckets = {c.bucket for c in results}
        return 1 if "fail" in buckets else 2 if "pending" in buckets or expected else 0
    elif args.op == "comments":
        threads, general, resolved = forge.comments(kind, ref, cwd)
        print(
            f"{ui.plural(len(threads), 'unresolved thread')} · {resolved} resolved · "
            f"{ui.plural(len(general), 'comment')}"
        )
        for t in threads:
            print(f"\n{t.path}:{t.line}" if t.line else f"\n{t.path or '(general)'}")
            for author, text in t.comments:
                print(f"  {author}: {text.strip()}")
        if general:
            print("\nComments")
            for author, text in general:
                print(f"  {author}: {text.strip()}")
    elif args.op == "view":
        s = forge.summary(kind, ref, cwd)
        print(f"{mark}{s.request.number} {s.request.title}")
        print(s.request.url)
        mergeable = s.mergeable if s.request.state in ("open", "opened") and s.mergeable not in ("", "unknown") else ""
        state = [s.request.state, "draft" if s.draft else "", f"mergeable: {mergeable}" if mergeable else ""]
        print("state    " + " · ".join(filter(None, state)))
        print("closes   " + (", ".join(f"#{n}" for n in s.closes) or "nothing"))
        print("checks   " + _checks_line(s.checks, None if s.checks else forge.ci_file(kind, cwd)))
        print(f"review   {s.review} · {ui.plural(s.unresolved, 'unresolved thread')}")
        diff = f" · +{s.additions} −{s.deletions}" if s.additions is not None else ""
        print(f"diff     {ui.plural(s.files, 'file')}{diff}")
    return 0


def _checks_line(results: list, expected: str | None = None) -> str:
    """expected: the CI configuration that should have reported checks; none reported is then not final."""
    if not results:
        return f"no checks yet: {expected} is configured, none reported" if expected else "no checks"
    counts = {b: [c.name for c in results if c.bucket == b] for b in ("pass", "fail", "pending", "skip")}
    parts = [f"{len(counts['pass'])} passed"]
    if counts["fail"]:
        parts.append(f"{len(counts['fail'])} failed: {', '.join(counts['fail'])}")
    if counts["pending"]:
        parts.append(f"{len(counts['pending'])} pending")
    if counts["skip"]:
        parts.append(f"{len(counts['skip'])} skipped")
    return " · ".join(parts)


def _plan(args: argparse.Namespace) -> None:
    cfg = load()
    tracker = trackers.get(cfg)
    if args.op == "state":
        for key, value in plan.state(cfg, tracker, args.ref).items():
            print(f"{key}={value}")
        return
    _, found = plan.locate(cfg, tracker, args.ref, args.slug)
    print(found)


def _backlog(args: argparse.Namespace) -> None:
    cfg = load()
    if args.op == "list":
        print("\n".join(backlog.titles(cfg)) or "no items")
        return
    if args.op == "pop":
        path = backlog.pop(cfg, args.title)
        print(f"removed from {path}" + ("; no items left, file deleted" if not path.exists() else ""))
        return
    print(f"added to {backlog.add(cfg, args.title, _body(args.body_file))}")


def _ids(text: str) -> list[str]:
    return [] if text.strip().casefold() == "none" else [i for i in re.split(r"[,\s]+", text.strip()) if i]


def _memory(args: argparse.Namespace) -> None:
    cfg = load()
    op = args.op
    if op == "add":
        text = _body(args.body_file)
        path = memory.add(cfg, args.kind, args.title, text, _ids(args.tags or ""), args.ref, args.intent)
        print(f"wrote {path.relative_to(cfg.checkout)}")
    elif op == "find":
        found = memory.find(cfg, args.kind, _ids(args.tags or ""), args.text or [], args.retired)
        if args.compact:
            print("\n".join(f"- {e.compact()}" for e in found) or "no entries")
        else:
            print("\n".join(e.text() for e in found).rstrip() or "no entries")
    elif op == "show":
        entry = memory.resolve(cfg, args.id)
        print(f"{entry.kind}: {entry.slug}")
        print(entry.text(), end="")
    elif op == "tags":
        rows = memory.tag_counts(cfg)
        if not rows:
            print(f"no vocabulary: {cfg.get('memory_dir')}/tags.toml")
        elif args.verbose:
            width = max(len(t) for t, _, _ in rows) + 2
            print("\n".join(f"{t:<{width}}{n:>4}  {d}" for t, n, d in rows))
        else:
            print(" · ".join(f"{t} {n}" for t, n, _ in rows))
    elif op == "supersede":
        path = memory.supersede(cfg, args.id, args.reason, args.by)
        print(f"retired {path.relative_to(cfg.checkout)}")
    elif op == "implemented":
        path = memory.implemented(cfg, args.id, args.ref)
        print(f"implemented {path.relative_to(cfg.checkout)}")
    elif op == "import":
        lines = (sys.stdin.read() if args.json == "-" else Path(args.json).read_text()).splitlines()
        written = memory.import_json(cfg, lines)
        kinds = {k: sum(p.parent.name == d for p in written) for k, d in memory.KINDS.items()}
        print(f"imported {', '.join(ui.plural(n, k) for k, n in kinds.items() if n) or 'nothing'}")
    elif op == "load":
        text = memory.start_text(cfg, args.plan)
        with contextlib.suppress(AwError):  # outside a session: nothing to record
            session.update(memory_start_tokens=memory.tokens(text))
        print(text or "no project memory yet")
    elif op == "log":
        meta = session.read()
        found = None
        if meta.get("issue") and cfg.get("tracker") != "none":
            try:
                _, found = plan.owner(cfg, trackers.get(cfg), meta["issue"])
            except AwError:
                found = None
        path = memory.log(cfg, meta, found, _ids(args.relevant), _ids(args.missed), args.note or "")
        print(f"logged to {path}")


def _template(args: argparse.Namespace) -> None:
    cfg = load()
    path = templates.source(cfg, args.name)
    shown = (path.relative_to(cfg.checkout) if path.is_relative_to(cfg.checkout) else ui.home(path)) if path else None
    print(f"template: {shown or 'bundled ' + args.name}", file=sys.stderr)
    print(templates.read(cfg, args.name), end="")


def _session(args: argparse.Namespace) -> None:
    for key, value in session.read().items():
        print(f"{key}={value}")


def _verify(args: argparse.Namespace) -> int:
    return finish.verify(load())


def _finish(args: argparse.Namespace) -> None:
    for line in finish.run(load(), session.read(), args.pr, args.close_parent):
        print(line)


def _abandon(args: argparse.Namespace) -> None:
    for line in finish.abandon(load(), session.read(), args.discard, args.status):
        print(line)


def _merge(args: argparse.Namespace) -> None:
    for line in finish.merge(load(), session.read(), args.pr):
        print(line)


def _restack(args: argparse.Namespace) -> int:
    result = restack.run(load(), session.read(), args.dry_run)
    if args.json:
        data = {k: v for k, v in asdict(result).items() if k != "log"}
        print(json.dumps(data | {"summary": result.summary}, indent=2))
    else:
        for line in [*result.log, result.summary]:
            print(line)
    return 1 if result.state == "conflict" else 0


def _init(args: argparse.Namespace) -> int:
    report = init.run(args.yes, args.set, check=args.check)
    values, previous = report.values, report.previous
    name = PROJECT_FILE
    verbs = ("created", "updated", "added") if report.written else ("would create", "would update", "would add")
    created, updated, added = verbs
    print(ui.style("aw init", ui.BOLD))
    if previous is None:
        origin = [
            ui.plural(n, src) if src == "default" else f"{n} {src}"
            for src in ("detected", "answered", "--set", "default")
            if (n := sum(s == src for s in report.sources.values()))
        ]
        status = ui.style(created, ui.GREEN) + f" · {ui.plural(len(values), 'key')}: {', '.join(origin)}"
        changed: list[str] = []
        new: list[str] = []
    else:
        changed = [k for k in values if k in previous and previous[k] != values[k]]
        new = [k for k in values if k not in previous]
        n_changed = len(changed) + (report.version is not None)
        counts = [f"{n_changed} changed" if n_changed else "", f"{len(new)} new" if new else ""]
        status = (
            ui.style(updated, ui.GREEN) + " · " + ", ".join(filter(None, counts))
            if n_changed or new
            else ui.style("up to date", ui.DIM)
        )
    print(f"  {name:<20}{status}")

    def show(value: object) -> str:
        return init.shown(value) or "—"

    if args.verbose:
        width = max(len(k) for k in values) + 2
        for key, value in values.items():
            print(f"    {key:<{width}}{show(value):<28}{ui.style(report.sources.get(key, ''), ui.DIM)}")
    else:
        old = previous or {}
        if report.version and previous is not None:
            before, after = report.version
            print(f"    aw_version  {show(before)} → {ui.style(str(after), ui.GREEN)}")
        for key in changed:
            print(f"    {key}  {show(old[key])} → {ui.style(show(values[key]), ui.GREEN)}")
        for key in new:
            print(f"    {key}  {ui.style(show(values[key]), ui.GREEN)} {ui.style('(new)', ui.DIM)}")
    if report.ignored:
        print(f"  {'.agents/.gitignore':<20}{added} {', '.join(report.ignored)}")
    for warning in report.warnings:
        ui.warn(warning)
    if not report.changes:
        return 0
    if not report.written:
        print("next: aw init")
        return 1
    print(f"next: review and commit {name} and .agents/.gitignore, then `aw doctor`")
    return 0


def _install(args: argparse.Namespace) -> None:
    running = Path(sys.argv[0])
    exe = running.absolute() if running.name == "aw" and running.is_file() else None
    report = install.run(args.agent, exe)
    print(ui.style("aw install", "1"))
    if args.verbose:
        for change in report.changes:
            print(f"  {change.action:<10}{ui.home(change.path)}")
    else:
        targets: dict[Path, list[install.Change]] = {}
        for change in report.changes:
            key = change.path if change.path.name == "aw" and change.path.parent.name == "bin" else change.path.parent
            targets.setdefault(key, []).append(change)
        width = max(len(ui.home(t)) for t in targets) + 3
        for target, changes in targets.items():
            counts = {a: sum(c.action == a for c in changes) for a in ("new", "updated", "removed")}
            moved = " · ".join(f"{n} {a}" for a, n in counts.items() if n)
            kept = [c for c in changes if c.action != "removed"]
            what = f"{len(kept)} skills" if target.name != "aw" else "CLI"
            status = ui.style(moved, "32") if moved else ui.style("up to date", "2")
            print(f"  {ui.home(target):<{width}}{what:<11}{status}")
        for action in ("new", "updated", "removed"):
            names = sorted({c.path.name for c in report.changes if c.action == action and c.path.name != "aw"})
            if names and not (action == "new" and len(names) == len(install.source_skills())):
                print(f"  {action + ':':<9}{', '.join(names)}")
    for warning in report.warnings:
        print(ui.style(f"! {warning}", "33"))


def _update(args: argparse.Namespace) -> int:
    print(ui.style("aw update", ui.BOLD), flush=True)
    for line in update.update_code():
        print(f"  {line}", flush=True)
    exe = update.executable()
    if code := update.relink(exe, args.agent):
        return code
    if root := update.project_root():
        update.check_project(exe, root)  # exit 1: changes pending, which it reports itself
    return 0


DOCTOR_MARKS = {"ok": ("✓", "32"), "info": ("·", "2"), "warn": ("!", "33"), "fail": ("✗", "31")}


def _doctor(args: argparse.Namespace) -> int:
    groups = doctor.sections()
    width = max(len(name) for name, _ in groups) + 3
    home = str(Path.home())
    print(ui.style("aw doctor", "1"))
    for name, results in groups:
        levels = [level for level, _ in results]
        worst = "fail" if "fail" in levels else "warn" if "warn" in levels else "ok"
        mark, color = DOCTOR_MARKS[worst]
        problems = [
            ui.plural(levels.count(lvl), word)
            for lvl, word in (("fail", "failure"), ("warn", "warning"))
            if lvl in levels
        ]
        passed = ui.plural(levels.count("ok"), "check") + " ok" if "ok" in levels else ""
        if "info" in levels:
            passed = " · ".join(filter(None, [passed, ui.plural(levels.count("info"), "note")]))
        summary = " · ".join(filter(None, [*problems, passed]))
        if results == [("ok", results[0][1])]:  # one passing check says more than "1 check ok"
            summary = results[0][1].replace(home, "~")
        print(f"  {ui.style(mark, color)} {name:<{width}}{summary}")
        for level, message in results:
            if level != "ok" or args.verbose:
                mark, color = DOCTOR_MARKS[level]
                print(f"      {ui.style(mark, color)} {message.replace(home, '~')}")
    levels = [level for _, results in groups for level, _ in results]
    if "fail" in levels or "warn" in levels:
        counts = [
            ui.plural(levels.count(lvl), word)
            for lvl, word in (("fail", "failure"), ("warn", "warning"))
            if lvl in levels
        ]
        print(", ".join(counts))
    else:
        print(ui.style("all good", "32"))
    return 1 if "fail" in levels else 0


def _summary(description: str) -> str:
    """First clause of a skill description: up to ' - ' or the end of the first sentence."""
    return re.split(r"\s-\s|(?<=\.)\s", description, maxsplit=1)[0].rstrip(".")


def menu(parser: argparse.ArgumentParser) -> str:
    def name(text: str) -> str:
        return ui.style(text, "36")

    def head(text: str) -> str:
        return ui.style(text, "1")

    workflow = [
        "aw-plan",
        "aw-to-story",
        "aw-plan-story",
        "aw-to-subtasks",
        "aw-start-task",
        "aw-checkpoint",
        "aw-merge-request",
        "aw-finalize",
    ]
    order = sorted(
        install.source_skills(), key=lambda p: (workflow.index(p.name) if p.name in workflow else 99, p.name)
    )
    skills = []
    for skill in order:
        fm = doctor.frontmatter(skill / "SKILL.md")
        suffix = " (user only)" if fm.get("disable-model-invocation") == "true" else ""
        skills.append((f"/{fm.get('name', skill.name)}", _summary(fm.get("description", "")) + suffix))
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    commands = [(f"aw {a.dest}", a.help or "") for a in sub._choices_actions]

    col = max(len(n) for n, _ in skills + commands) + 2
    width = shutil.get_terminal_size((100, 20)).columns
    room = max(width - col - 2, 20)

    def rows(items: list[tuple[str, str]]) -> list[str]:
        out = []
        for n, text in items:
            shown = text if len(text) <= room else text[: room - 1] + "…"
            out.append(f"  {name(n.ljust(col))}{shown}")
        return out

    lines = [
        f"aw {__version__}: standardized agentic workflows",
        "",
        head("Skills (run in your agent)"),
        *rows(skills),
        "",
        head("Commands"),
        *rows(commands),
        "",
        "Run `aw <command> -h` for options.",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aw", description="Standardized agentic workflows.")
    p.add_argument("--version", action="version", version=f"aw {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("install", help="link skills and the CLI into ~/.agents")
    s.add_argument("--agent", action="append", default=None, help="also link skills for this agent (default: claude)")
    s.add_argument("-v", "--verbose", action="store_true", help="one line per link instead of a summary")
    s.set_defaults(func=_install)

    s = sub.add_parser("update", help="update aw (git pull or uv tool upgrade), relink skills, check this project")
    s.add_argument("--agent", action="append", default=None, help="also link skills for this agent (default: claude)")
    s.set_defaults(func=_update)

    s = sub.add_parser("init", help="create or update .agents/aw.toml in this repo")
    s.add_argument("-y", "--yes", action="store_true", help="accept detected defaults, no prompts")
    s.add_argument("-v", "--verbose", action="store_true", help="list every value written and where it came from")
    s.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    s.add_argument(
        "--check", action="store_true", help="report what aw init --yes would change; write nothing, exit 1 if it would"
    )
    s.set_defaults(func=_init)

    s = sub.add_parser("config", help="print the resolved configuration")
    s.add_argument("--get", metavar="KEY", help="print one value")
    s.add_argument("--sources", action="store_true", help="show which layer set each value")
    s.set_defaults(func=_config)

    s = sub.add_parser("start-task", help="create branch and worktree for a session")
    s.add_argument("type")
    s.add_argument("slug")
    s.add_argument("--issue")
    s.add_argument("--base", help="start on this pending branch instead of main_branch (a stacked session)")
    s.set_defaults(func=_start_task)

    s = sub.add_parser("issue", help="issue tracker operations (tracker from config)")
    ops = s.add_subparsers(dest="op", required=True)
    o = ops.add_parser("view", help="issue with parent, children, comments, extra fields")
    o.add_argument("id")
    o.add_argument("--json", action="store_true")
    o.add_argument("--out", metavar="DIR", help="write <id>.md (or .json) into DIR instead of printing")
    o = ops.add_parser("children", help="child issues / subtasks, each marked when linked only by text")
    o.add_argument("id")
    o.add_argument(
        "--text-only",
        action="store_true",
        help="only children without a native link: what is left to move to set-parent",
    )
    o.add_argument("--json", action="store_true")
    o = ops.add_parser("dupes", help="issues matching the terms, any state: under the parent first, then elsewhere")
    o.add_argument("id", nargs="?", help="parent issue the candidates hang under (none: the whole project)")
    o.add_argument("--terms", nargs="+", required=True)
    o.add_argument("--tree-only", action="store_true", help="only issues under the parent (two levels)")
    o.add_argument("--limit", type=int, default=20, help="rows in all; hits under the parent are never cut")
    o.add_argument("--json", action="store_true")
    o = ops.add_parser("list", help="open issues (Jira: in jira_project)")
    o.add_argument("--limit", type=int, default=20)
    o.add_argument("--json", action="store_true")
    o = ops.add_parser("search", help="text search; --raw passes a tracker query (JQL, gh search syntax)")
    o.add_argument("query")
    o.add_argument("--raw", action="store_true")
    o.add_argument("--limit", type=int, default=20)
    o.add_argument("--json", action="store_true")
    o = ops.add_parser("create", help="create an issue from a Markdown body")
    o.add_argument("--title", required=True)
    o.add_argument("--body-file", required=True, help="Markdown file, or - for stdin")
    o.add_argument("--parent")
    o.add_argument("--type", help="issue type (Jira default Task; GitHub only on organization-owned repos)")
    o.add_argument("--label", action="append", default=[], help="label to set; repeat for several")
    o.add_argument(
        "--status",
        choices=[*STATUSES, "none"],
        help="state of the new issue (default: backlog on a GitHub board, the workflow's first on Jira); "
        "none: on the board without a column, e.g. an epic",
    )
    o.add_argument(
        "--field",
        action="append",
        default=[],
        metavar="NAME=OPTION",
        help="single-select field of github_project to set; repeat for several (board_fields: also from labels)",
    )
    o.add_argument("--dry-run", action="store_true")
    o = ops.add_parser("set-parent", help="link, re-parent or unlink an existing issue with the native parent link")
    o.add_argument("id")
    o.add_argument("parent", nargs="?", help="new parent; replaces the current one")
    o.add_argument("--none", action="store_true", help="remove the parent link")
    o.add_argument("--dry-run", action="store_true", help="print the current and the new parent, change nothing")
    o = ops.add_parser("update", help="replace title and description of an existing issue")
    o.add_argument("id")
    o.add_argument("--title")
    o.add_argument("--body-file", help="Markdown file with the complete new description, or - for stdin")
    o.add_argument("--dry-run", action="store_true")
    o = ops.add_parser("comment", help="add a Markdown comment")
    o.add_argument("id")
    o.add_argument("--body-file", required=True, help="Markdown file, or - for stdin")
    o = ops.add_parser("set-status", help="move to a canonical status (mapped by status_map), then run on_issue_status")
    o.add_argument("id")
    o.add_argument("status", choices=STATUSES)
    o = ops.add_parser("set-field", help="set single-select fields of the issue's card on github_project")
    o.add_argument("id")
    o.add_argument("pairs", nargs="+", metavar="NAME=OPTION")
    o = ops.add_parser("rollup", help="whether this subtask's story can close once it is done; --close closes it")
    o.add_argument("id", help="the subtask; it counts as closed")
    acts = o.add_mutually_exclusive_group()
    acts.add_argument(
        "--close",
        action="store_true",
        help="close the story with a comment naming its children; refuses while anything keeps it open",
    )
    acts.add_argument(
        "--json", action="store_true", help="the decision as JSON: can_close, stays_open, unknown, no_story"
    )
    o = ops.add_parser("ref", help="how to reference the issue in text (#12, PROJ-123)")
    o.add_argument("id")
    o = ops.add_parser("pr-text", help="line for the PR body that links or closes the issue")
    o.add_argument("id")
    s.set_defaults(func=_issue)

    s = sub.add_parser("mr", aliases=["pr"], help="merge/pull request operations (forge from config)")
    mr_ops = s.add_subparsers(dest="op", required=True)
    o = mr_ops.add_parser(
        "create", help="open a merge request for the current branch against main_branch, or a stacked session's base"
    )
    o.add_argument("--title", required=True)
    o.add_argument("--body-file", required=True, help="Markdown file, or - for stdin")
    o.add_argument("--draft", action="store_true")
    o.add_argument(
        "--part", action="store_true", help="one part of a multi-merge session: references the issue without closing it"
    )
    o.add_argument(
        "--expect",
        metavar="N",
        help="the number already written down (aw mr next, e.g. in the changelog): refuse when the next request "
        "would get another; exit 1 when a race gave it another anyway",
    )
    o.add_argument("--dry-run", action="store_true")
    mr_ops.add_parser("next", help="the number the next merge request gets, for a changelog entry written first")
    o = mr_ops.add_parser("update", help="replace title and description")
    o.add_argument("ref", nargs="?", help="number or branch (default: the current branch)")
    o.add_argument("--title")
    o.add_argument("--body-file", help="Markdown file with the complete new description, or - for stdin")
    o.add_argument("--dry-run", action="store_true")
    o = mr_ops.add_parser("view", help="state, checks, review, unresolved threads and diff size in one view")
    o.add_argument("ref", nargs="?", help="number or branch (default: the current branch)")
    o = mr_ops.add_parser("checks", help="CI results; exit 0 passed, 1 failed, 2 pending")
    o.add_argument("ref", nargs="?", help="number or branch (default: the current branch)")
    o.add_argument("--watch", action="store_true", help="wait until no check is pending")
    o.add_argument("-v", "--verbose", action="store_true", help="list passing checks too")
    o = mr_ops.add_parser("comments", help="unresolved review threads and general comments")
    o.add_argument("ref", nargs="?", help="number or branch (default: the current branch)")
    s.set_defaults(func=_mr)

    s = sub.add_parser("plan", help="locate the plan document of a story or subtask")
    plan_ops = s.add_subparsers(dest="op", required=True)
    o = plan_ops.add_parser("path", help="print the plan file of this issue")
    o.add_argument("ref")
    o.add_argument("--slug", help="compose the path to write when no plan exists yet")
    o = plan_ops.add_parser("state", help="what exists for this issue: plan file, subtasks")
    o.add_argument("ref")
    s.set_defaults(func=_plan)

    s = sub.add_parser("backlog", help="add and remove items in the repo backlog file")
    backlog_ops = s.add_subparsers(dest="op", required=True)
    o = backlog_ops.add_parser("add", help="add one item")
    o.add_argument("--title", required=True)
    o.add_argument("--body-file", required=True, help="Markdown file, or - for stdin")
    o = backlog_ops.add_parser("pop", help="remove one item: sent to the tracker, or discarded")
    o.add_argument("--title", required=True)
    o = backlog_ops.add_parser("list", help="item titles in backlog_file, one per line")
    s.set_defaults(func=_backlog)

    s = sub.add_parser("memory", help="the project's decisions and gotchas, one file per entry")
    memory_ops = s.add_subparsers(dest="op", required=True)
    o = memory_ops.add_parser("add", help="write one entry")
    o.add_argument("kind", choices=sorted(memory.KINDS))
    o.add_argument("--title", required=True, help="the fact, stated as a claim; becomes the slug")
    o.add_argument("--body-file", required=True, help="Markdown file, or - for stdin")
    o.add_argument("--tags", help="comma-separated tags from tags.toml (a gotcha needs at least one)")
    o.add_argument("--ref", help="issue the entry came from")
    o.add_argument(
        "--intent", action="store_true", help="a decision accepted in a settled plan and not built yet (decisions only)"
    )
    o = memory_ops.add_parser("find", help="entries with any of the tags and all of the text terms")
    o.add_argument("--kind", choices=sorted(memory.KINDS))
    o.add_argument("--tags", help="comma-separated; any of them")
    o.add_argument("--text", nargs="+", help="terms that must all appear (case-insensitive)")
    o.add_argument("--compact", action="store_true", help="one line per entry: id · title")
    o.add_argument("--retired", action="store_true", help="include retired entries")
    o = memory_ops.add_parser("show", help="one entry by slug or alias (95, D15)")
    o.add_argument("id")
    o = memory_ops.add_parser("tags", help="the tag vocabulary with the number of active gotchas per tag")
    o.add_argument("-v", "--verbose", action="store_true", help="one tag per line, with its description")
    o = memory_ops.add_parser("supersede", help="retire an entry; it stays, marked retired")
    o.add_argument("id", help="slug or alias")
    o.add_argument("--reason", required=True, help="why it no longer holds")
    o.add_argument("--by", help="the entry that replaces it")
    o = memory_ops.add_parser("implemented", help="an intent decision is built: it becomes active")
    o.add_argument("id", help="slug or alias")
    o.add_argument("--ref", help="issue that built it")
    o = memory_ops.add_parser("import", help="write entries from JSON lines; all are checked before any is written")
    o.add_argument("--json", required=True, metavar="FILE", help="one JSON object per line, or - for stdin")
    o = memory_ops.add_parser("load", help="what a session start reads, per gotchas_load")
    o.add_argument("--plan", action="store_true", help="the session has a plan: leave out the decision index")
    o = memory_ops.add_parser("log", help="record this session for the gotchas experiment (gitignored)")
    o.add_argument("--relevant", required=True, help="gotcha ids that mattered this session, or none")
    o.add_argument("--missed", required=True, help="gotchas that bit although an entry existed, or none")
    o.add_argument("--note", help="one line, e.g. a tag that was missing")
    s.set_defaults(func=_memory)

    s = sub.add_parser("template", help="print a document template (project override from templates)")
    s.add_argument("name", help="template name")
    s.set_defaults(func=_template)

    s = sub.add_parser("session", help="print the current worktree's session metadata")
    s.set_defaults(func=_session)

    s = sub.add_parser("verify", help="run verify_cmd in the current checkout")
    s.set_defaults(func=_verify)

    s = sub.add_parser("merge", help="merge one part of the session; the branch catches up with main and goes on")
    s.add_argument(
        "--pr", help="merge request number (default: the branch's open one; forge = none: after a manual merge)"
    )
    s.set_defaults(func=_merge)

    s = sub.add_parser("restack", help="stacked session: rebase onto the base's tip, or onto main once it merged")
    s.add_argument("--dry-run", action="store_true", help="show the rebase without running it")
    s.add_argument("--json", action="store_true", help="the result as JSON")
    s.set_defaults(func=_restack)

    s = sub.add_parser(
        "finish", help="last merge (skipped when nothing is left), remove the worktree, delete the branch"
    )
    s.add_argument(
        "--pr", help="merge request number (default: the branch's open one; forge = none: after a manual merge)"
    )
    s.add_argument(
        "--close-parent",
        action="store_true",
        help="also close the issue's parent story, unless another child or a plan section keeps it open",
    )
    s.set_defaults(func=_finish)

    s = sub.add_parser("abandon", help="end the session without a merge: issue back, worktree and branch removed")
    s.add_argument(
        "--discard",
        action="store_true",
        help="also drop uncommitted changes and commits main lacks (refused without it)",
    )
    s.add_argument(
        "--status",
        choices=["backlog", "ready"],
        default="backlog",
        help="where an issue in progress goes back to (default: backlog)",
    )
    s.set_defaults(func=_abandon)

    s = sub.add_parser("doctor", help="check installation and project configuration")
    s.add_argument("-v", "--verbose", action="store_true", help="list passing checks too, not only problems")
    s.set_defaults(func=_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] == "help":
        print(menu(parser))
        return 0
    args = parser.parse_args(argv)
    if args.command in ("install", "update") and args.agent is None:
        args.agent = ["claude"]
    try:
        return args.func(args) or 0
    except AwError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
