"""aw: command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aw import __version__, doctor, finish, init, install, session, start_task
from aw.config import AwError, load, toml_value


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
    args = build_parser().parse_args(argv)
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
