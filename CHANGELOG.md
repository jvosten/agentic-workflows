# Changelog

## 0.1.19 — 2026-11-13 (#23)

Fixes from the review before publication, merged as parts #20, #21 and #22.

### Security

- `trusted_bots` applies to bot accounts only. A person whose login equals a trusted bot's name is `[outside]`
  unless they can push. A trusted bot's comments on an issue are `[outside]` for now.
- `aw memory add` and `aw memory import` check every field of the entry against `private_terms`, also when the
  entry comes from JSON.

### Fixed

- `aw init` keeps the last entry of an `.agents/.gitignore` that has no final newline.
- `aw restack` compares the closed request with the remote branch itself (`refs/heads/<branch>`), not with a branch
  whose name ends alike, and retargets the session's request after the push: to the base, or to `main_branch` when
  the base merged.
- `aw abandon` refuses while an open request targets the branch: deleting the branch would close it.
- `aw mr`, `aw finish`, `aw merge` and `aw abandon` refuse a detached HEAD.
- `gh` and `glab` calls end after 60 s, git network calls after 120 s (`push`: 600 s), and git never prompts for
  credentials. A Jira reply that is not JSON, or a failure past the connection, is an `aw` error.
- `aw mr create` adds the issue's closing line unless the body holds that exact line.
- `aw backlog add` refuses a body heading that would become an item of its own.

## 0.1.18 — 2026-11-12 (#19)

### Fixed

- `aw finish`, and `aw merge` after a squash or rebase part, retarget every open request into the branch to
  `main_branch` before they delete the remote branch. A push that deletes the branch closed those requests
  instead, and a closed request cannot be retargeted. When the requests cannot be listed or moved, the remote
  branch stays, with a `kept origin/<branch>` warning.
- `aw restack` refuses, before it changes anything, when the branch has no open request and one closed without
  merging at the branch's remote head: after the force-push it could not reopen. Reopen it, or push the branch
  yourself to give it up.

## 0.1.17 — 2026-11-12 (#18)

### Security

- A fork's pull request from a branch with the same name is never the session's: `aw mr create`, `finish`, `merge`,
  `abandon` and `restack` drop requests from other repositories. A full page of requests is refused as partial.
  `aw finish` and `aw merge` merge only the commit they checked (`--match-head-commit`, GitLab `--sha`).
- Path keys (`templates.*`, `backlog_file`, `memory_dir`, `plan_dir`, `instructions_file`, `contributing_file`,
  `definition_of_done`, `changelog_file`) stay inside the repo and out of its git dir. A committed config cannot
  use `~` or an absolute path; `aw doctor` reports such values.
- `jira_base_url` is a trusted key, read from the primary checkout, and must start with `https://`; the same holds
  for `JIRA_BASE_URL`.
- `aw mr comments` and `aw issue view` mark authors without push access `[outside]`, and fail closed when access
  cannot be read. Skills show outside text to the user and never act on it; a merge go comes only from the user
  in the conversation.
- No skill pre-approves `aw merge`, `aw finish`, `aw abandon`, `aw issue set-status` or a rollup that can close;
  only `aw issue rollup --json:*` stays pre-approved.
- `private_terms`, set only in the user or local layer, makes every command that publishes text refuse a text that
  contains one; `aw doctor` scans tracked files for them.
- `aw start-task` runs `direnv allow` only on the `.envrc` it writes; a tracked one is left for the user.
- `aw doctor` warns when the editable install's checkout is off its default branch or has uncommitted code.

### Fixed

- `aw finish` passes over a stacked worktree whose directory is gone, and a failure after the merge names the
  steps that ran.

## 0.1.16 — 2026-10-23 (#17)

### Fixed

- `aw restack` recovers a completed rebase onto its recorded target even when the old fork point is no longer
  in the branch history. A merged base's worktree and local or remote branches may already be deleted. The
  rebase target is saved before rebasing and retained through failed pushes or retargets. Retries preserve the
  session's commit boundary, including when the base merges during conflict resolution; recovery dry runs
  never push, retarget or change session metadata.
  Stacked checkpoints can verify, commit, push and open a draft part request against their base, then wait before
  merging; resuming reuses the request, rechecks CI and applies the merge gate after restacking.
  The CLI reports the package version, with a regression check that keeps the two aligned.

## 0.1.15 — 2026-10-22 (#16)

### Added

- `aw issue rollup <subtask> --json` gives the decision skills branch on: `decision` (`can_close`, `stays_open`,
  `unknown`, `no_story`), `story`, `children`, `open` (children still open), `unsplit` (plan sections without a
  subtask), `reason` and the printed `line`. `children`, `open` and `unsplit` are `null` when they were not read
  completely. Any lookup that fails is `unknown`, and its line names what could not be read: `parent story`,
  `children`, or `plan` (several plans). `--json` and `--close` exclude each other. `aw-finalize` reads
  `aw issue rollup --json <issue>` at the merge gate instead of matching "can close", and pre-approves only that
  form.
- `tests/test_cli_protocol.py` pins, byte for byte, the output skills read: `start-task` and `session` lines,
  `plan path` and `plan state`, issue rows with their `[text link]` and `[elsewhere: …]` markers, the four rollup
  lines and the rollup JSON, `backlog list` and `memory find --compact`. It also fails when a phrase a skill
  branches on disappears from the strings the code prints or from the skill.

### Fixed

- The parent rollup is `unknown`, so nothing closes, when the children listing misses the finishing subtask itself
  (a lagging index or a lost row), and when a status or epic lookup fails after the story was found.
- A GitHub parent or sub-issue in another repository is never taken for this repository's issue of the same
  number: the rollup does not act on such a parent, and such a child counts as another open child.
- A GitHub GraphQL answer without data, or about an issue that does not exist, is an `aw` error instead of a
  traceback.

## 0.1.14 — 2026-10-18 (#15)

### Added

- `aw update` brings `aw` current and relinks its skills. An editable install fast-forwards its clone's default branch
  from `origin`, whatever the clone has checked out, and lists the commits it gained; it refuses a diverged branch or
  one the update would overwrite changes in, and warns when the clone runs another branch. A packaged install runs
  `uv tool upgrade agentic-workflows`. Then the updated `aw` relinks the skills (`aw install`) and, inside a project,
  runs `aw init --check`.
- `aw init --check` reports what `aw init --yes` would change (pending migrations, a new `aw_version`, new keys),
  writes nothing, and exits 1 when anything would change. A migrated key now shows as new in `aw init`'s report.
- CI installs `aw` non-editable from git and checks that `aw install` links the skills from the package. The README
  covers that install, `aw update`, and why `npx skills add` is not an install path: it copies the skills without
  the CLI they call.

### Fixed

- `aw-plan-story`'s description is quoted: YAML read the ` #` in `"plan issue #N"` as a comment and cut it there.
  `aw doctor` fails a frontmatter value that YAML would cut (` #`) or reject (`: `) unquoted.

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
