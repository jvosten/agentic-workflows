# Changelog

## 0.1.13 — 2026-10-17 (#14)

### Fixed

- A branch no longer decides what runs or merges on the host. In a session worktree, `merge_gate`, `merge_method`,
  `on_start`, `on_merge` and `on_issue_status` come from the primary checkout's `.agents/aw.toml`, not from the
  branch's (schema: `trusted = true`); user, local and env layers apply as before. A branch that changes one of them
  takes effect once it has merged; until then `aw finish`, `aw merge` and `aw doctor` print `ignored from the branch:
  <keys>`, and `aw config --sources` shows the value as `primary`.

### Added

- `AW_SANDBOXED=1`, set by a sandbox runner, makes `aw finish`, `aw merge` and `aw issue rollup --close` refuse with
  `sandboxed: <command> runs on the host`. It is env only: a config file that sets `sandboxed` is ignored with an `aw
  doctor` warning, and `aw init --set` refuses it.

## 0.1.12 — 2026-10-16 (#13)

### Added

- Decisions take a status `intent`: accepted in a settled plan, not built yet. `aw memory add decision --intent`
  writes one, every listing marks it `(intent: accepted, not built yet)`, and `aw memory implemented <id>` makes it
  active with a dated note. A gotcha cannot be intent; `add` and `import` refuse it.

### Changed

- Memory gets only what held up. `aw-plan-story` writes nothing while a plan is drafted or grilled: probes,
  hypotheses and predicted pitfalls stay in the plan, and decisions go in once, after the plan is approved, as
  intent, linking the plan and superseding instead of duplicating. `aw-remember` takes gotchas only from a symptom
  someone hit; `aw-finalize` marks the intents a session built.

## 0.1.11 — 2026-10-16 (#12)

### Added

- `aw mr next` prints the number the next merge request gets, and `aw mr create --expect N` refuses before the
  create when it moved, or exits 1 naming the line to fix when a race gave the request another. `aw-finalize` writes
  the changelog entry before it commits and opens the request, so the entry is in the request's first pushed state
  and a review bot that runs once on open finds it; no `docs: changelog for #N` commit follows.

## 0.1.10 — 2026-10-16

### Fixed

- `aw mr view` accepts external issue references returned by GitLab, such as Jira keys, instead of crashing when
  they have no `iid`; native GitLab issues still use their `iid`.

## 0.1.9 — 2026-10-15 (#11)

### Added

- `board_required` lists single-select fields of a `github_project` board that every new issue sets. `aw issue
  create`, dry run included, creates nothing while one of them has neither a `--field` nor a `board_fields` label,
  and names each missing field with its options. `aw-backlog-item`, `aw-to-story`, `aw-to-subtasks` and the splits
  in `aw-plan-story` propose a value for each and show it before the create. `aw doctor` checks each field exists.

## 0.1.8 — 2026-10-14 (#10)

### Changed

- Worktrees are named `{issue}-{slug}`, or `{slug}` without an issue; the session number is gone. `aw start-task`
  no longer counts sessions (`.git/aw-last-session` is no longer read or written; delete it), drops `--number`, the
  `{n}` placeholder and the `session=` line of its output, and refuses while `branch_name`, `worktree_name` or
  `on_start` still uses `{n}`. A name that exists already is refused, as before. Session files that still hold a
  number are read as before.

## 0.1.7 — 2026-10-14 (#9)

### Added

- `aw issue create --field Name=Option` sets single-select fields of a `github_project` board (an `Area` lane, a
  `Priority`) on the new card, and `aw issue set-field <id> Name=Option…` on an existing one. `board_fields` maps a
  label prefix to a field (`"area/" = "Area"`), so a label picked on create sets the field too; `aw-backlog-item` and
  `aw-to-story` pick one label per mapped prefix. Fields and options are checked before the create, and a failure
  after it names `set-status` and `set-field` as the repair. `aw doctor` checks each mapped field and that every label
  with its prefix has an option. Jira refuses `--field` for now.

### Fixed

- `aw restack` reports the actual commit count after conflict recovery in its human summary and JSON result,
  counting only commits above the saved rebase target, not newly inherited base commits.

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
