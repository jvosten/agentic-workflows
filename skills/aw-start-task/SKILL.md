---
name: aw-start-task
description: Start an implementation session - create the branch and worktree, load the scope into a task list, and hand over to implementation. Use only when the user invokes it.
disable-model-invocation: true
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw start-task:*)
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

- Issue reference (`#N`) in the request and `tracker` is set: read the issue.
  - `github`: `gh issue view N --json title,body,labels`
  - `gitlab`: `glab issue view N`
- `type`: one of `branch_types`. New feature → `feat`, bug → `fix`, upgrade or maintenance → `chore`, docs only → `docs`.
- `slug`: 2–5 words, kebab-case, naming the outcome (e.g. `retry-failed-uploads`).

## 3. Create the worktree

```bash
~/.agents/bin/aw start-task <type> <slug> [--issue N]
```

It syncs `main_branch`, picks the session number, creates branch and worktree, sets up direnv, and runs `on_issue_start`. It prints `session`, `branch`, `worktree`, `issue`.

- Do not create branches or worktrees any other way.
- On a non-zero exit, show stderr and stop.

## 4. Load scope

- Read `<worktree>/<instructions_file>`.
- Plan source, first match: a plan path in the request; a file under `plan_dir` that names the issue; the issue body.
- Create one task per plan step. No plan → plan the approach with the user before any code.
- State the scope: what this session delivers, what it defers.

## 5. Hand over

Print:

```
Session s<session> ready
  worktree: <worktree>
  branch:   <branch>
  issue:    #<issue> | none
  verify:   <verify_cmd> | none
  scope:    <one line>
Implementation starts now. All file operations use absolute paths under <worktree>.
```

Then continue with the first task. Implementation rules come from `instructions_file`, not from this skill.
