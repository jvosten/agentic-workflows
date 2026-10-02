---
name: aw-plan
description: Entry point for planning - decide what the work needs next (a story, a plan, or subtasks) and hand over to the skill that does it. Use only when the user invokes it.
disable-model-invocation: true
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw plan state:*) Bash(~/.agents/bin/aw issue view:*) Bash(~/.agents/bin/aw issue list:*)
metadata:
  package: agentic-workflows
---

# Plan

Request: $ARGUMENTS

Route one piece of work to the next planning step. Run one step per invocation; each needs a fresh head.

## 1. Load settings

```bash
~/.agents/bin/aw config
```

On error, show it and stop. `.agents/aw.toml` missing → tell the user to run `aw init` and stop.

## 2. Read the state

- No issue id in the request → the work has no story yet. Skip to step 3.
- Issue id (`#12`, `PROJ-123`) given:

```bash
~/.agents/bin/aw plan state <id>
```

It prints `issue` (the story the plan belongs to; the parent when the id is a subtask), `plan` (path or `none`) and `subtasks` (ids, empty when none).

## 3. Choose the next step

| State | Next | Skill |
|---|---|---|
| No issue | write the story | `aw-to-story` |
| `plan=none` | plan the story | `aw-plan-story` |
| plan exists, `subtasks=` empty | cut the plan into subtasks | `aw-to-subtasks` |
| plan and subtasks exist | nothing pending | report; offer re-planning or re-syncing the subtasks |

Implementation is not a planning step: a session starts with `/aw-start-task <subtask id>`.

## 4. Confirm, then hand over

Print one line and wait for the user:

```
<issue> <state in six words or fewer> → <skill>?
```

On confirmation, load and follow that skill with the same request. On refusal, ask which step the user wants.

## Rules

- One step per invocation. Never chain two planning skills in one turn.
- Never invoke `/aw-start-task` or `/aw-finalize`.
- Report what `aw plan state` said; do not guess at state you did not read.
