"""aw: command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from aw import __version__, doctor, finish, init, install, plan, session, start_task, templates, trackers
from aw.config import AwError, load, toml_value
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
    for key, value in start_task.run(load(), args.type, args.slug, args.issue, args.number).items():
        print(f"{key}={value}")


def _rows(rows: list[trackers.Row], as_json: bool) -> None:
    if as_json:
        print(json.dumps([vars(r) for r in rows], indent=2))
        return
    print("\n".join(trackers.rows_line(r) for r in rows) or "no issues")


def _body(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text()


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
        if args.dry_run:
            print(f"DRY RUN ({tracker.name}): title={args.title!r} parent={args.parent} type={args.type}")
            print(f"body: {len(body.splitlines())} lines")
            return
        new = tracker.create(args.title, body, args.parent, args.type)
        print(tracker.ref(new))
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
        _rows(tracker.children(issue), args.json)
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
    elif op == "ref":
        print(tracker.ref(issue))
    elif op == "pr-text":
        print(tracker.pr_text(issue))


def _plan(args: argparse.Namespace) -> None:
    cfg = load()
    tracker = trackers.get(cfg)
    if args.op == "state":
        for key, value in plan.state(cfg, tracker, args.ref).items():
            print(f"{key}={value}")
        return
    _, found = plan.locate(cfg, tracker, args.ref, args.slug)
    print(found)


def _template(args: argparse.Namespace) -> None:
    print(templates.read(load(), args.name), end="")


def _session(args: argparse.Namespace) -> None:
    for key, value in session.read().items():
        print(f"{key}={value}")


def _verify(args: argparse.Namespace) -> int:
    return finish.verify(load())


def _finish(args: argparse.Namespace) -> None:
    for line in finish.run(load(), session.read(), args.pr):
        print(line)


def _init(args: argparse.Namespace) -> None:
    path = init.run(args.yes, args.set)
    print(f"wrote {path}; review and commit it")


def _install(args: argparse.Namespace) -> None:
    running = Path(sys.argv[0])
    exe = running.absolute() if running.name == "aw" and running.is_file() else None
    for line in install.run(args.agent, exe):
        print(line)


def _doctor(args: argparse.Namespace) -> int:
    results = doctor.run()
    for level, message in results:
        print(f"{level:<4}  {message}")
    return 1 if any(level == "fail" for level, _ in results) else 0


def _summary(description: str) -> str:
    """First clause of a skill description: up to ' - ' or the end of the first sentence."""
    return re.split(r"\s-\s|(?<=\.)\s", description, maxsplit=1)[0].rstrip(".")


def menu(parser: argparse.ArgumentParser) -> str:
    color = sys.stdout.isatty() and "NO_COLOR" not in os.environ

    def name(text: str) -> str:
        return f"\033[36m{text}\033[0m" if color else text

    def head(text: str) -> str:
        return f"\033[1m{text}\033[0m" if color else text

    workflow = ["aw-plan-story", "aw-start-task", "aw-finalize"]
    order = sorted(install.source_skills(), key=lambda p: (workflow.index(p.name) if p.name in workflow else 99, p.name))
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
            text = text if len(text) <= room else text[: room - 1] + "…"
            out.append(f"  {name(n.ljust(col))}{text}")
        return out

    lines = [f"aw {__version__}: standardized agentic workflows", "",
             head("Skills (run in your agent)"), *rows(skills), "",
             head("Commands"), *rows(commands), "",
             "Run `aw <command> -h` for options."]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aw", description="Standardized agentic workflows.")
    p.add_argument("--version", action="version", version=f"aw {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("install", help="link skills and the CLI into ~/.agents")
    s.add_argument("--agent", action="append", default=None,
                   help="also link skills for this agent (default: claude)")
    s.set_defaults(func=_install)

    s = sub.add_parser("init", help="create or update .agents/aw.toml in this repo")
    s.add_argument("-y", "--yes", action="store_true", help="accept detected defaults, no prompts")
    s.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    s.set_defaults(func=_init)

    s = sub.add_parser("config", help="print the resolved configuration")
    s.add_argument("--get", metavar="KEY", help="print one value")
    s.add_argument("--sources", action="store_true", help="show which layer set each value")
    s.set_defaults(func=_config)

    s = sub.add_parser("start-task", help="create branch and worktree for a session")
    s.add_argument("type")
    s.add_argument("slug")
    s.add_argument("--issue")
    s.add_argument("--number", type=int, help="session number (default: next in this clone)")
    s.set_defaults(func=_start_task)

    s = sub.add_parser("issue", help="issue tracker operations (tracker from config)")
    ops = s.add_subparsers(dest="op", required=True)
    o = ops.add_parser("view", help="issue with parent, children, comments, extra fields")
    o.add_argument("id")
    o.add_argument("--json", action="store_true")
    o.add_argument("--out", metavar="DIR", help="write <id>.md (or .json) into DIR instead of printing")
    o = ops.add_parser("children", help="child issues / subtasks")
    o.add_argument("id")
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
    o.add_argument("--type", help="issue type (Jira), default Task")
    o.add_argument("--dry-run", action="store_true")
    o = ops.add_parser("update", help="replace title and description of an existing issue")
    o.add_argument("id")
    o.add_argument("--title")
    o.add_argument("--body-file", help="Markdown file with the complete new description, or - for stdin")
    o.add_argument("--dry-run", action="store_true")
    o = ops.add_parser("comment", help="add a Markdown comment")
    o.add_argument("id")
    o.add_argument("--body-file", required=True, help="Markdown file, or - for stdin")
    o = ops.add_parser("set-status", help="move to a canonical status (mapped by status_map)")
    o.add_argument("id")
    o.add_argument("status", choices=STATUSES)
    o = ops.add_parser("ref", help="how to reference the issue in text (#12, PROJ-123)")
    o.add_argument("id")
    o = ops.add_parser("pr-text", help="line for the PR body that links or closes the issue")
    o.add_argument("id")
    s.set_defaults(func=_issue)

    s = sub.add_parser("plan", help="locate the plan document of a story or subtask")
    plan_ops = s.add_subparsers(dest="op", required=True)
    o = plan_ops.add_parser("path", help="print the plan file of this issue")
    o.add_argument("ref")
    o.add_argument("--slug", help="compose the path to write when no plan exists yet")
    o = plan_ops.add_parser("state", help="what exists for this issue: plan file, subtasks")
    o.add_argument("ref")
    s.set_defaults(func=_plan)

    s = sub.add_parser("template", help="print a document template (project override from templates)")
    s.add_argument("name", help="template name")
    s.set_defaults(func=_template)

    s = sub.add_parser("session", help="print the current worktree's session metadata")
    s.set_defaults(func=_session)

    s = sub.add_parser("verify", help="run verify_cmd in the current checkout")
    s.set_defaults(func=_verify)

    s = sub.add_parser("finish", help="merge the PR, remove the worktree, update main, delete the branch")
    s.add_argument("--pr", help="pull/merge request number (required unless forge = none)")
    s.set_defaults(func=_finish)

    s = sub.add_parser("doctor", help="check installation and project configuration")
    s.set_defaults(func=_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] == "help":
        print(menu(parser))
        return 0
    args = parser.parse_args(argv)
    if args.command == "install" and args.agent is None:
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
