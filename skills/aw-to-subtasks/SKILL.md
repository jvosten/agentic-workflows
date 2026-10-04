---
name: aw-to-subtasks
description: Cut a plan into subtasks on the tracker - one session-sized slice per subtask, reconciled with the subtasks that already exist, and linked back into the plan. Use only when the user invokes it.
disable-model-invocation: true
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw template subtask) Bash(~/.agents/bin/aw plan path:*) Bash(~/.agents/bin/aw plan state:*) Bash(~/.agents/bin/aw issue view:*) Bash(~/.agents/bin/aw issue children:*) Bash(~/.agents/bin/aw issue create:*) Bash(~/.agents/bin/aw issue update:*) Bash(~/.agents/bin/aw issue set-parent:*) Bash(~/.agents/bin/aw issue comment:*)
metadata:
  package: agentic-workflows
---

# To subtasks

Request: $ARGUMENTS

Publish one subtask per plan section, and keep plan and tracker in step. Every write is shown before it happens.

## 1. Load settings, plan and state

```bash
~/.agents/bin/aw config
~/.agents/bin/aw plan state <id>
~/.agents/bin/aw plan path <id>
```

- No plan → tell the user to run `/aw-plan-story <id>` first, and stop.
- Read the plan. The implementation sections (`S1`, `S2`, …) are the slices; their `**Subtask:**` lines say what was published before.
- `tracker = none` → no tickets exist. Keep the section list in the plan as the record and stop after step 3.

## 2. Map sections to existing subtasks

1. A section naming a subtask id owns that subtask.
2. For the rest, read `aw issue children <id>` and propose a mapping table: section ↔ existing subtask, or *new*, or *no section left* (obsolete).
3. A mapped subtask that is not natively under the story — marked `[text link]`, or a section's subtask that `children` does not list — gets a *relink* in the table.
4. Show the table and wait for approval. Never guess silently.

## 3. Draft each subtask body

From the template:

```bash
~/.agents/bin/aw template subtask
```

- **Title**: the outcome of the slice, active phrase.
- **What to build**: the end-to-end behaviour, from the user's view. No file paths, no code, no step lists — they live in the plan and go stale in tickets.
- **Acceptance criteria**: testable conditions from the section.
- **Blocked by**: the slices that gate this one, by subtask id once created, otherwise by section id. None → "None (can start immediately)".
- **Plan**: plan path (relative to the repo root) and section id, e.g. `.agents/plans/PROJ-1-uploads/PROJ-12-retries-2026-10-04.md#s2`. `plan_scope = local` → the section id only: the plan is not in the repo, and a path would point nowhere for anyone else.

Rendering one body per section is mechanical: delegate it to a cheap subagent per section when the harness has one (`subagent_model`). Keep the mapping and the writes yourself.

## 4. Show the set, then publish

Present the numbered set: title, blocked by, what it delivers. Ask whether the granularity and the blocking edges are right, and iterate until the user approves.

Then publish in dependency order, blockers first:

```bash
~/.agents/bin/aw issue create --title "<title>" --body-file - --parent <story> [--type <subtask_type>] --dry-run
~/.agents/bin/aw issue create --title "<title>" --body-file - --parent <story> [--type <subtask_type>]
~/.agents/bin/aw issue update <existing> --title "<title>" --body-file - --dry-run
~/.agents/bin/aw issue update <existing> --title "<title>" --body-file -
```

- `--type` comes from `subtask_type`; leave it out when the key is empty.
- `update` replaces the whole description. Show the new body before sending it, and keep anything the ticket carries that the plan does not cover.
- Relinks: `~/.agents/bin/aw issue set-parent <existing> <story> --dry-run`, then without `--dry-run`. A `Part of` line left in its body can go in the same `update`.
- The parent is set by `--parent` or `set-parent` only. Never write it into a body.
- Obsolete subtasks: list them and say why they fell out. Close one only when the user says so (`aw issue set-status <id> done`), with a comment naming the replacement.

## 5. Link back

- Write each created id into its section's `**Subtask:**` line in the plan.
- Post one comment on the story linking the plan and listing the subtasks in order.
- Print the set and tell the user each session starts with `/aw-start-task <subtask id>`.

## Rules

- One story per invocation.
- No write without approval; `--dry-run` first for every create and update.
- Never close or rewrite the parent story.
- Never invoke `/aw-start-task` or `/aw-finalize` yourself.
- No secret values in ticket bodies or comments.
