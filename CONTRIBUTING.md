# Contributing

`AGENTS.md` holds the project's rules; they apply to people and to agents. This file is the short form for a pull request.

## Before you start

- A bug: open an issue with the bug form. A feature: open an issue first; `BACKLOG.md` lists what is already planned.
- A vulnerability: see `SECURITY.md`. Never a public issue.

## Changes

- `make check` passes: tests, `ruff` and `ty`. CI runs the same.
- Tests never reach the network or depend on credentials; see `AGENTS.md`, Tests.
- A bug fix starts with a test that fails without it.
- `README.md`, `docs/boards.md` and the skills change with the command they describe.
- Nothing names a private project, host or person; examples use neutral names.

## Commits

- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `style:`, `refactor:`. The subject says what changed.
- No `Co-Authored-By` or "Generated with" lines.

## Pull requests

- Title: a conventional-commit summary of the outcome.
- One changelog fragment per pull request in `changelog.d/` (`aw changelog target` names it), in the commits the
  request opens with. It names no pull request number and no version.
- A pull request that only bumps a dependency (Dependabot) needs no fragment.
- A release is a pull request of its own: `aw changelog collect --heading "## <version> — <date>"` folds the
  fragments into `CHANGELOG.md`, and the version is set in `pyproject.toml`, `src/aw/__init__.py` and `uv.lock`.
- The description has three sections: Summary, Evidence (the test that failed before and passes now), Merge danger.
- Pull requests merge with a merge commit, after the four CI checks pass.

## Reviewing a pull request from outside

`make install` links the skills and the `aw` CLI to your clone, so a checkout runs that code in every project. Review a branch you do not trust in a separate worktree or clone, never by checking it out in the installed clone.
