# Changelog

## 0.1.2 — 2026-10-13 (#2)

### Added

- CI on GitHub Actions: tests on Python 3.11 and 3.13, ruff and ty, on every pull request and push to `main`.
- `make check` runs tests, lint and types; `make test`, `make lint`, `make types` and `make format` for the parts.

### Changed

- `ruff` and `ty` pinned in the dev group. A strict ruff rule set, each exception explained in `pyproject.toml` or on
  its `noqa` line; `src` and `tests` formatted with `ruff format` and clean under both checkers.
- `aw doctor` reports a board or Jira check against the wrong tracker as a failure instead of crashing.
- `AGENTS.md` adds the checks, the rules for working on `aw` and the repository conventions to the test rules.

## 0.1.1 — 2026-10-13 (#1)

### Added

- Stacked sessions: `aw start-task --base <branch>` starts a session on another session's unmerged branch, and
  `aw restack` follows the base or moves onto `main` once it merged, for `merge`, `squash` and `rebase` merges.
  `aw mr create` targets the base; `aw merge` / `aw finish` refuse while it is unmerged and warn in the base session.
  Skills and README describe the flow (README "Stacked sessions").

### Changed

- Tests never reach the network: sockets refuse, `gh` and `glab` fail, forge and tracker credentials are cleared.
- This repository uses `forge = "github"`; `AGENTS.md` holds its test rules.

## 0.1.0

- First version: `aw` CLI with layered project config, sessions in worktrees, the planning and session skills,
  tracker adapters for GitHub, GitLab and Jira, merge requests through `aw mr`, multi-merge sessions, project
  memory and the backlog.
