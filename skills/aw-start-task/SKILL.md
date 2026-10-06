---
name: aw-start-task
description: Start an implementation session - create the branch and worktree, load the scope into a task list, and hand over to implementation. Use only when the user invokes it.
disable-model-invocation: true
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw start-task:*) Bash(~/.agents/bin/aw issue view:*) Bash(~/.agents/bin/aw plan path:*) Bash(~/.agents/bin/aw memory load:*) Bash(~/.agents/bin/aw memory find:*) Bash(~/.agents/bin/aw memory show:*) Bash(~/.agents/bin/aw memory tags:*)
metadata:
  package: agentic-workflows
---

# Start task

Request: $ARGUMENTS

## 1. Load project settings

```bash
~/.agents/bin/aw config
```

On error, show it and stop. If `.agents/aw.toml` is missing, tell the user to run `aw init` and stop.

## 2. Choose type and slug

- Issue reference in the request (`#12`, `PROJ-123`) and `tracker` is not `none`: read it with `~/.agents/bin/aw issue view <id>`.
- `type`: one of `branch_types`. New feature → `feat`, bug → `fix`, upgrade or maintenance → `chore`, docs only → `docs`.
- `slug`: 2–5 words, kebab-case, naming the outcome (e.g. `retry-failed-uploads`).

## 3. Create the worktree

```bash
~/.agents/bin/aw start-task <type> <slug> [--issue <id>]
```

It syncs `main_branch`, picks the session number, creates branch and worktree, sets up direnv, moves the issue to in progress (trackers with workflow states, `sync_issue_status`), and runs `on_issue_start`. It prints `session`, `branch`, `worktree`, `issue`.

- Do not create branches or worktrees any other way.
- On a non-zero exit, show stderr and stop.

## 4. Load scope

- Read `<worktree>/<instructions_file>`.
- Plan source, first match: a plan path in the request; `~/.agents/bin/aw plan path <issue>` (for a subtask it resolves the parent story's plan); the issue from `aw issue view`.
- Project memory, from the worktree: `~/.agents/bin/aw memory load` (add `--plan` when there is a plan). Depending on `gotchas_load` it prints every gotcha, or only the tags that have gotchas; without a plan it adds the decisions in force. With a plan, its **Known gotchas** and **Decisions in force** sections are the memory for this session.
- With `gotchas_load = tags`: before working with a tool that has gotchas, and whenever a tool errors, look first: `aw memory find --tags <tag> --compact` (or `--text <error words>`), then `aw memory show <id>` for the one that fits.
- The issue is a subtask → work only the plan section whose `**Subtask:**` line names it. No match → ask which section applies.
- Create one task per plan step. No plan → plan the approach with the user before any code.
- A `Checkpoint:` step becomes its own task: run `/aw-checkpoint` there, then continue with the next task.
- State the scope: what this session delivers, what it defers.

## 5. Hand over

Print:

```
Session s<session> ready
  worktree: <worktree>
  branch:   <branch>
  issue:    <issue ref> | none
  verify:   <verify_cmd> | none
  scope:    <one line>
Implementation starts now. All file operations use absolute paths under <worktree>.
```

Then continue with the first task. Implementation rules come from `instructions_file`, not from this skill.
