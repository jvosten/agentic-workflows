# agentic-workflows

Generic agent skills that give every project the same session workflow. Project differences live in a committed config file that the skills read, not in the skills.

Skills follow the [Agent Skills](https://agentskills.io/specification) format and install to `~/.agents/skills/`. Pi, Codex, Cursor, Gemini CLI, OpenCode and Copilot read that directory directly. Claude Code does not, so `aw install` links each skill into `~/.claude/skills/` as well.

## Install

Requires `git` and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone <this repo> ~/projects/agentic-workflows
cd ~/projects/agentic-workflows
uv tool install --editable .     # puts `aw` in ~/.local/bin
~/.local/bin/aw install          # links skills and ~/.agents/bin/aw
~/.agents/bin/aw doctor
```

The editable install means edits to this repo take effect without reinstalling. Re-run `aw install` after adding or removing a skill.

## Use the skills

This is the point of the package: one session workflow that you drive from your coding agent, in any repo. Set the repo up once with `aw init` (see [Set up a project](#set-up-a-project)), then call the skills.

| Harness | Call a skill | Skills come from |
|---|---|---|
| Pi | `/skill:aw-plan #12` | `~/.agents/skills/` |
| Claude Code | `/aw-plan #12` | `~/.claude/skills/`, linked by `aw install --agent claude` |
| Codex, Cursor, Gemini CLI, OpenCode, Copilot | name the skill in your request | `~/.agents/skills/` |

One session, start to finish:

1. `/aw-plan #12` — routes: no story yet → writes one, story without plan → plans it, plan without subtasks → cuts them. One step per call.
2. `/aw-plan-story #12` — reads the issue, its parent, children and the project docs, drafts a plan in session-sized sections, grills it with you, saves it under `plan_dir`.
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

User-only skills never start by themselves; the model may pick up the others when the task calls for them.

The story, subtask and plan documents follow templates: `aw template <name>` prints the bundled one, and the `templates` key points at your own.

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
| `view` (parent, children, comments, extra fields) | ✓ | ✓ | ✓ (no children/comments) |
| `children` | sub-issues + task-list refs | JQL `parent = KEY` | – |
| `list`, `search` | ✓ | ✓ (`--raw` = JQL) | ✓ |
| `create` (with `--parent`, `--dry-run`) | ✓ (as sub-issue) | ✓ (Markdown → ADF) | – |
| `update` (title, description; `--dry-run`) | ✓ | ✓ | – |
| `comment` | ✓ | ✓ | ✓ |
| `set-status` | open/closed only | workflow transition via `status_map` | open/closed only |
| `ref` / `pr-text` | `#12` / `Fixes #12` | `PROJ-12` / `PROJ-12` | `#12` / `Fixes #12` |

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
| `aw issue view\|children\|list\|search\|create\|update\|comment\|set-status\|ref\|pr-text` | Tracker operations; see [Issue trackers](#issue-trackers) |
| `aw plan path <ref> [--slug S]` | Plan file of a story or subtask (subtask: through its parent); `--slug` composes the path to write |
| `aw plan state <ref>` | What exists for the issue: plan file, subtasks |
| `aw template <story\|subtask\|plan>` | Print a document template, project override from `templates` |
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

Planned work: [BACKLOG.md](BACKLOG.md).

## License

MIT, see [LICENSE](LICENSE). Skills copied from other projects keep their own `LICENSE` file.
