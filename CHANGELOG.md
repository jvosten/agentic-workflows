# Changelog

## 0.1.6 — 2026-10-13 (#6)

### Fixed

- `aw mr checks` no longer reads "no checks" as green when the checkout has CI (`.github/workflows/*.yml`,
  `.gitlab-ci.yml`): right after a request opens it prints `no checks yet: … is configured, none reported` and exits
  2, and `--watch` waits up to two minutes for the first check.
- Backlog items are the headings under `## Items`, so sub-headings inside an item no longer split it.
- A list at column 0 keeps its nested levels in Jira descriptions (ADF).
- `aw start-task` keeps a tracked `.envrc`; a missing or failing `direnv` is a warning and the start goes on.
- `aw plan state` on a tracker without parent links (GitLab) reports no subtasks instead of failing.
- `aw doctor` shows a merge request template outside the checkout instead of crashing.
- Several plans for one issue are refused and listed; the parent rollup counts them as unknown and closes nothing.
- A malformed memory entry or import line (a YAML list such as `tags: [git, gh]`, a wrong status) is an error naming
  the file or line and the field; files on disk and imports share one check.
- A malformed session file names the file and the field, and is never mistaken for "outside a session": a stacked
  session's merge request no longer falls back to `main` on it.
- Hooks and `direnv` print to file descriptor 2 instead of through `sys.stderr`, so they run when the host replaced
  `sys.stderr` (pytest's `capsys`, an embedding program) instead of failing with `fileno`.

### Changed

- README notes that the GitHub path runs this repository's own pull requests; the backlog keeps only what is still
  unconfirmed live.

## 0.1.5 — 2026-10-13 (#5)

### Fixed

- `aw memory import` refuses an unsafe or existing slug and malformed fields before writing anything; it never
  overwrites an entry. Slugs are unique across decisions and gotchas: `aw memory add` refuses a clash, a lookup
  refuses an ambiguous slug, and `aw doctor` lists existing clashes.
- The closing line (`Fixes #12`) is added unless a closing phrase for exactly this issue is in the body: a mention of
  `#123` or a bare `#12` no longer suppresses it. `aw mr update` keeps it, and after create and update `aw` checks what
  the request will close: the session issue missing is an error, another closed issue a warning.
- Hook placeholders are shell-quoted, so `In Progress` reaches a script as one argument and shell characters in values
  are inert.
- A missing `gh` or `glab` is an `aw` error, not a traceback.

### Changed

- Config migrations replace the rename table. `on_issue_start` becomes `on_start = "[ -n {issue} ] && <old>"`, keeping
  its behaviour; quotes written around hook placeholders are removed (`"{status_name}"` becomes `{status_name}`), and
  `aw doctor` warns about a placeholder inside a longer quoted text. `aw init` applies pending migrations.
- `aw mr view` prints a `closes` line with the issues the request will close.

## 0.1.4 — 2026-10-13 (#4)

### Fixed

- The parent rollup never closes a story on an incomplete list of its children. A failed sub-issue request on GitHub
  is no longer read as "no children", and Jira children beyond the first 100 are read: `aw finish` warns
  `#N: children unknown (…)`, and `--close-parent` and `aw issue rollup --close` refuse. HTTP 404 on GitHub's
  sub-issues endpoint still counts as none.
- `aw mr comments` reads every page of review threads, so an unresolved thread beyond the first 100 still stops the
  merge gate. GitLab jobs and discussions are paginated too.

### Changed

- `aw issue rollup` can print a fourth line, `#N: children unknown (<reason>)`, next to `can close` and `stays open`.

## 0.1.3 — 2026-10-13 (#3)

### Fixed

- `aw finish --pr N` with a request merged before later commits no longer removes the worktree and deletes the
  branch: it refuses and names the commits that would be lost. A request given with `--pr` that is not at the
  branch's head (another branch's) is never merged; `aw merge` checks the same before merging, not after.
- `aw finish` after `main` moved on since the last part no longer fails with "no open merge request": nothing is
  left once `main` holds every commit of the branch.

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
