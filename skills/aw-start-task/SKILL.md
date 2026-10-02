---
name: aw-start-task
description: Start an implementation session - create the branch and worktree, load the scope into a task list, and hand over to implementation. Use only when the user invokes it.
disable-model-invocation: true
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw start-task:*) Bash(~/.agents/bin/aw issue view:*) Bash(~/.agents/bin/aw plan path:*)
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

- Read `<worktree>/<instructions_file>`, and `<worktree>/<memory_dir>/decisions.md` and `gotchas.md` when they exist: they hold what earlier sessions settled and got bitten by.
- Plan source, first match: a plan path in the request; `~/.agents/bin/aw plan path <issue>` (for a subtask it resolves the parent story's plan); the issue from `aw issue view`.
- The issue is a subtask → work only the plan section whose `**Subtask:**` line names it. No match → ask which section applies.
- Create one task per plan step. No plan → plan the approach with the user before any code.
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
