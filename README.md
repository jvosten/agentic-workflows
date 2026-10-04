# agentic-workflows

Generic agent skills that give every project the same session workflow. Project differences live in a committed config file that the skills read, not in the skills.

Skills follow the [Agent Skills](https://agentskills.io/specification) format and install to `~/.agents/skills/`. Pi, Codex, Cursor, Gemini CLI, OpenCode and Copilot read that directory directly. Claude Code does not, so `aw install` links each skill into `~/.claude/skills/` as well.

## Install

Requires `git`, `make` and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone <this repo> ~/projects/agentic-workflows
cd ~/projects/agentic-workflows
make install       # installs the `aw` CLI, links skills and ~/.agents/bin/aw
make doctor
```

`make install` runs two steps: `uv tool install --editable .` puts `aw` on your PATH, and `aw install` links each skill into `~/.agents/skills/` (plus `~/.claude/skills/`) and the CLI to `~/.agents/bin/aw`, the path every skill calls. Without the second step no agent sees the skills.

The editable install means edits to this repo take effect without reinstalling. Re-run `make install` after adding or removing a skill: it also prunes links to skills that are gone.

`make install` installs the tool; `aw init` (below) configures one project.

## Use the skills

This is the point of the package: one session workflow that you drive from your coding agent, in any repo. Set the repo up once with `aw init` (see [Set up a project](#set-up-a-project)), then call the skills.

| Harness | Call a skill | Skills come from |
|---|---|---|
| Pi | `/skill:aw-plan #12` | `~/.agents/skills/` |
| Claude Code | `/aw-plan #12` | `~/.claude/skills/`, linked by `aw install --agent claude` |
| Codex, Cursor, Gemini CLI, OpenCode, Copilot | name the skill in your request | `~/.agents/skills/` |

One session, start to finish:

1. `/aw-plan #12` — routes: no story yet → writes one, story without plan → plans it, plan without subtasks → cuts them. One step per call.
2. `/aw-plan-story #12` — reads the issue, its parent, children and the project docs, drafts a plan in session-sized sections, grills it with you, saves it under `.agents/plans/` (see [Plans](#plans)).
3. `/aw-to-subtasks #12` — one subtask per plan section, reconciled with the subtasks that exist, published after your approval, linked back into the plan.
4. `/aw-start-task PROJ-13` — creates the branch and worktree, loads that subtask's plan section as a task list, then implements it with you.
5. `/aw-finalize` — docs, `aw verify`, commit, pull request, changelog entry, review and CI. It asks before the merge.

For design work before planning, `/aw-grill-with-docs` interviews you and keeps `GLOSSARY.md` and `docs/adr/` current.

| Skill | Invocation | Does |
|---|---|---|
| `aw-plan` | user only | Reads `aw plan state` and hands over to the planning skill the work needs next |
| `aw-to-story` | user only | Conversation → user story on the tracker, from the `story` template; rewrites an existing story too |
| `aw-plan-story` | user or model | Story + parent + project context → plan in `S1`, `S2`, … sections, grilled with you |
| `aw-to-subtasks` | user only | Plan sections → subtasks, each a vertical slice with its blocking edges |
| `aw-start-task` | user only | Creates the session worktree via `aw start-task`, loads the plan section, hands over to implementation |
| `aw-finalize` | user only | Docs, `aw verify`, commit, PR, changelog entry, review + CI, then `aw finish` |
| `aw-grilling` | user or model | Interview in rounds over a design tree until nothing is assumed |
| `aw-grill-with-docs` | user only | `aw-grilling` plus `aw-domain-modeling` |
| `aw-domain-modeling` | user or model | Challenge terms, keep `GLOSSARY.md` and `docs/adr/` current |
| `aw-remember` | user or model | Append one decision or gotcha to the project's memory |
| `aw-backlog-item` | user or model | Discussion → one backlog item, repo-local, optionally pushed to the tracker |

User-only skills never start by themselves; the model may pick up the others when the task calls for them.

The story, subtask and plan documents follow templates: `aw template <name>` prints the bundled one, and the `templates` key points at your own.

## Plans

A plan lives at `plan_dir/plan_file`, by default `.agents/plans/<area>/<issue>-<slug>-<date>.md`. The area is the parent issue (`PROJ-1-upload-retries`), so the plans of one epic share a folder; an issue without a parent puts its plan directly under `.agents/plans/`. `aw plan path <id> --slug <slug>` composes the path; `aw plan path <id>` finds an existing plan by the issue id in its file name, and a subtask finds its story's plan through the parent link.

`plan_scope` decides who sees plans:

| `plan_scope` | Where | For |
|---|---|---|
| `repo` (default) | committed, in the current checkout or worktree | teams; subtasks link to plan sections that anyone can open, and the plan stays as history |
| `local` | gitignored, always in the primary checkout, so every session worktree of this clone sees it | personal plans; the tracker subtasks and the project memory carry what others need |

`aw init --set plan_scope=local` adds `plans/` to `.agents/.gitignore`; `aw doctor` warns when a local plan directory is not ignored.

## Project memory

Two committed files under `memory_dir` (default `.agents/memory`) carry what the project learned:

| File | Holds |
|---|---|
| `decisions.md` | What the team settled, and why it won |
| `gotchas.md` | Non-obvious constraints that cost someone time |

One entry per heading, newest last, each stamped with its date and issue. `aw memory add <decision\|gotcha> --title "<claim>" --body-file -` appends; `aw memory supersede <kind> --title "<claim>" --reason "<what changed>"` retires an entry under a `## Superseded` heading instead of deleting it.

Writers: `aw-plan-story` after accepted grilling decisions that outlive the story, `aw-finalize` for gotchas the session paid for, `/aw-remember` any time in between. Entries are written in the session worktree, so they are reviewed and merged with the work that taught them. `aw-start-task` reads both files at the start of the next session, and `aw doctor` warns when a file passes 200 lines — the point to retire what no longer holds.

Titles are claims (`boto3 is pinned below 1.36`), because a session loads these files whole and the title carries the point.

## Backlog

Deferred work goes to `backlog_file` (default `BACKLOG.md`) through `/aw-backlog-item`, which `aw-finalize` calls for anything a session chose not to do. `aw backlog add` places the item among the file's existing items and copies their heading level and separators, so a flat `## Item` list and a sectioned `### [PRIO] Item` list both stay intact.

An item can then be pushed to the tracker: `aw issue dupes <backlog_parent> --terms ...` shows candidates under `backlog_parent` two levels deep in any state, you confirm, pick the parent (`backlog_parent` or one of its children and grandchildren, or none), `aw issue create --parent <parent> [--type <backlog_type>]` creates it with the tracker's native parent link, and `aw backlog pop` removes the local copy so one item does not live in two places. Staying repo-local is a normal outcome, not a failure.

## Set up a project

```bash
cd <repo>
aw init            # prompts, with defaults detected from the repo
aw init --yes      # accept detected defaults
aw init --set verify_cmd="make check"
aw doctor
```

`aw init` writes `.agents/aw.toml` (commit it) and `.agents/.gitignore`. Re-running it keeps existing answers as defaults and asks only what `schema.toml` added since.

## Configuration

| Layer | Path | Scope |
|---|---|---|
| defaults | `src/aw/schema.toml` | built in |
| user | `~/.agents/aw/config.toml` | all projects on this machine |
| project | `<checkout>/.agents/aw.toml` | committed; read from the current checkout or worktree |
| local | `<primary>/.agents/aw.local.toml` | gitignored; this machine only |
| env | `AW_<KEY>` | one run |

Later layers win. `aw config --sources` shows which layer set each value. All keys, types and help texts are in [`src/aw/schema.toml`](src/aw/schema.toml).

## Sessions

A session is one worktree on one branch, from `aw start-task` to `aw finish`, and implements one subtask: one vertical slice that is verifiable on its own. Its number is counted per clone (`.git/aw-last-session`) and never committed. It names the worktree and nothing else, so in a shared repo nobody's numbers collide. Session metadata (branch, worktree, issue) lives in the worktree's private git dir and disappears with it.

The committed record of a session is its pull request and its changelog entry. Projects moving from their own numbering start once with `aw start-task ... --number N`; the counter continues from there.

## Issue trackers

Skills never call a tracker directly; they call `aw issue <op>`, and `tracker` in the config picks the adapter.

| Op | github (`gh`) | jira (REST v3) | gitlab (`glab`, untested) |
|---|---|---|---|
| `view` (parent, children, comments, extra fields) | ✓ (parent: sub-issue link, `Part of #N` as fallback) | ✓ | ✓ (no parent/children/comments) |
| `children` (`--text-only`) | sub-issues + task-list refs, the latter marked `[text link]` | JQL `parent = KEY` | – |
| `set-parent <id> <parent>\|--none` (`--dry-run`) | sub-issue link, replaces an existing parent | `fields.parent` | – |
| `dupes` (parent, terms, any state) | native sub-issue tree ∩ search | one scoped JQL | unscoped search, says so |
| `list`, `search` | ✓ | ✓ (`--raw` = JQL) | ✓ |
| `create` (with `--parent`, `--type`, `--dry-run`) | one GraphQL call, so never left unlinked; `--type` on org-owned repos only | ✓ (Markdown → ADF) | – |
| `update` (title, description; `--dry-run`) | ✓ | ✓ | – |
| `comment` | ✓ | ✓ | ✓ |
| `set-status` | open/closed only | workflow transition via `status_map` | open/closed only |
| `ref` / `pr-text` | `#12` / `Fixes #12` | `PROJ-12` / `PROJ-12` | `#12` / `Fixes #12` |

**Parent links** are always the tracker's own: GitHub sub-issues, Jira `parent`. Skills never write `Part of #N` or `Epic: KEY` into a body. On GitHub, `view` still reads a `Part of #N` line and `children` a task-list ref, marked `[text link]`, so older projects keep working while they move: `aw issue children <root> --text-only` lists what is linked only by text (task-list refs in the root, `Part of #<root>` lines in other issues), `aw issue set-parent <id> <root>` links each one natively, and an empty `--text-only` confirms none remain. Jira rejects parents that break its hierarchy (a sub-task under an epic, mixed team- and company-managed projects); `set-parent` passes the error through with both issue types.

Statuses are canonical (`backlog`, `ready`, `in_progress`, `in_review`, `done`); `status_map` maps them to the tracker's names, defaulting to title case (`In Progress`). With `sync_issue_status` (default on), `aw start-task --issue` moves the issue to `in_progress` and `aw finish` to `done`, on trackers with workflow states. GitHub and GitLab close through the PR keyword instead.

**Jira setup:** `aw init` asks for `jira_base_url` and `jira_project` when `tracker = jira`. Credentials come from the environment only: `JIRA_USER_EMAIL`, `JIRA_API_TOKEN`, and optionally `JIRA_CLOUD_ID` for scoped tokens (routes through `api.atlassian.com`). Instance-specific fields go into `jira_fields`, e.g. `aw init --set jira_fields=acceptance_criteria=customfield_10000`. `aw doctor` checks that the variables are set, never their values, and calls `/myself`.

## Commands

| Command | Does |
|---|---|
| `aw install [--agent claude]` | Link skills into `~/.agents/skills` and agent dirs, CLI into `~/.agents/bin/aw` |
| `aw init [-y] [--set K=V]` | Create or update `.agents/aw.toml` |
| `aw config [--get KEY] [--sources]` | Print resolved configuration |
| `aw start-task <type> <slug> [--issue N] [--number N]` | Sync main, pick session number, create branch + worktree, direnv, issue hook |
| `aw session` | Print the current worktree's session metadata |
| `aw verify` | Run `verify_cmd` in the current checkout (through direnv if enabled) |
| `aw finish [--pr N]` | Merge with `merge_method`, remove worktree, update main, delete local + remote branch |
| `aw issue view\|children\|list\|search\|create\|update\|set-parent\|comment\|set-status\|ref\|pr-text` | Tracker operations; see [Issue trackers](#issue-trackers) |
| `aw plan path <ref> [--slug S]` | Plan file of a story or subtask (subtask: through its parent); `--slug` composes the path to write |
| `aw plan state <ref>` | What exists for the issue: plan file, subtasks |
| `aw template <story\|subtask\|plan>` | Print a document template, project override from `templates` |
| `aw memory add <decision\|gotcha> --title T --body-file F [--ref ID]` | Append one entry to the project's memory |
| `aw memory supersede <decision\|gotcha> --title T --reason R` | Retire an entry, keeping it under `## Superseded` |
| `aw backlog add --title T --body-file F` | Add an item to `backlog_file`, matching the file's item shape |
| `aw backlog pop --title T` | Remove an item, once the tracker owns it |
| `aw doctor` | Check installation, skill frontmatter, project config, tools, tracker auth |

## Skill internals

The grilling and domain-modeling skills are copied from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT); each keeps its `LICENSE` and a `metadata.source` link to the exact upstream commit.

`aw finish` is deliberately not in `aw-finalize`'s `allowed-tools`: the merge asks for permission.

User-only skills set `disable-model-invocation: true` (Claude Code) and `policy.allow_implicit_invocation: false` in `agents/openai.yaml` (Codex).

Rule for new skills: deterministic steps (git, paths, numbering, tracker calls) go into `aw` subcommands. Skills keep only the steps that need judgement.

Mechanical steps inside a skill (gathering context, rendering one document from a template) say to delegate to a cheap subagent when the harness has one; `subagent_model` names it. Judgement stays with the main model: grilling, the epic-size call, and reconciling tickets.

Two skills write a story: `aw-to-story` when the conversation redefined it, `aw-plan-story` when grilling moved it. Both carry the same four-step story-write protocol (re-read, diff, `--dry-run`, keep what you did not author). Change one, change the other.

## Development

```bash
uv run pytest
```

or `make check`, which `aw init` detects as this repo's `verify_cmd`.

Planned work: [BACKLOG.md](BACKLOG.md).

## License

MIT, see [LICENSE](LICENSE). Skills copied from other projects keep their own `LICENSE` file.
