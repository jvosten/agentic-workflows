# agentic-workflows

Generic agent skills that give every project the same session workflow. Project differences live in a committed config file that the skills read, not in the skills.

Skills follow the [Agent Skills](https://agentskills.io/specification) format and install to `~/.agents/skills/`. Codex, Cursor, Gemini CLI, OpenCode and Copilot read that directory directly. Claude Code does not, so `aw install` links each skill into `~/.claude/skills/` as well.

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

A session is one worktree on one branch, from `aw start-task` to `aw finish`. Its number is counted per clone (`.git/aw-last-session`) and never committed. It names the worktree and nothing else, so in a shared repo nobody's numbers collide. Session metadata (branch, worktree, issue) lives in the worktree's private git dir and disappears with it.

The committed record of a session is its pull request and its changelog entry. Projects moving from their own numbering start once with `aw start-task ... --number N`; the counter continues from there.

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
| `aw doctor` | Check installation, skill frontmatter, project config, tools, tracker auth |

## Skills

| Skill | Invocation | Does |
|---|---|---|
| `aw-start-task` | user only | Creates the session worktree via `aw start-task`, loads the plan into a task list, hands over to implementation |
| `aw-finalize` | user only | Docs, `aw verify`, commit, PR, changelog entry, review + CI, then `aw finish` |

`aw finish` is deliberately not in `aw-finalize`'s `allowed-tools`: the merge asks for permission.

User-only skills set `disable-model-invocation: true` (Claude Code) and `policy.allow_implicit_invocation: false` in `agents/openai.yaml` (Codex).

Rule for new skills: deterministic steps (git, paths, numbering, tracker calls) go into `aw` subcommands. Skills keep only the steps that need judgement.

## Development

```bash
uv run pytest
```

Planned work: [BACKLOG.md](BACKLOG.md).
