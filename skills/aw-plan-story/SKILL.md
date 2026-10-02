---
name: aw-plan-story
description: Plan one story - gather the issue, its parent, children and linked docs, draft an implementation plan in session-sized sections, grill it with the user, and save it for /aw-to-subtasks. Use when the user says "plan story", "plan issue #N", "plan PROJ-123", or wants to turn an issue into a session plan.
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw template plan) Bash(~/.agents/bin/aw plan path:*) Bash(~/.agents/bin/aw plan state:*) Bash(~/.agents/bin/aw issue view:*) Bash(~/.agents/bin/aw issue children:*) Bash(~/.agents/bin/aw issue list:*) Bash(~/.agents/bin/aw issue search:*) Bash(~/.agents/bin/aw issue update:*) Bash(~/.agents/bin/aw issue comment:*)
metadata:
  package: agentic-workflows
---

# Plan story

Request: $ARGUMENTS

Turn one story into a plan the user has vetted, cut into session-sized sections, ready for `/aw-to-subtasks`.

## 1. Load settings and pick the issue

```bash
~/.agents/bin/aw config
```

- An issue id (`#12`, `PROJ-123`) is required unless `tracker = none`. None given → ask, or offer candidates from `~/.agents/bin/aw issue list`.
- `tracker = none` → plan from the user's description instead of an issue.
- Optional inputs the user may name: design docs or decision records, test files, doc files. Read each one.

## 2. Gather context

- `~/.agents/bin/aw issue view <id>`: description, acceptance criteria, children, comments, parent.
- Parent → `aw issue view <parent>` too, and read the design docs it links.
- Read `instructions_file` and follow its pointers to whatever the work touches: decision records (do not reopen decided choices), known pitfalls, reference docs.
- Where the work touches running systems, check their current state read-only instead of trusting docs.
- Facts you can look up are your job; ask the user only for decisions.
- Delegate this gathering to a cheap subagent when the harness has one (`subagent_model`, when set): it reads and summarizes, you keep the judgement.
- The user asks for research on an approach → compare the options in a table and recommend one.

## 3. Size check before drafting

The story is epic-sized when any of these holds:

- more than about five session-sized slices;
- more than one deployable outcome;
- acceptance criteria spanning two personas.

Then stop drafting, say which rule it broke, and propose a split into sibling stories under the same parent. Create them only on the user's go (`aw issue create --parent <parent> --dry-run` first), then plan one of them. These thresholds are a starting point; tune them as the project uses them.

## 4. Draft the plan

Start from the template:

```bash
~/.agents/bin/aw template plan
```

Fill it:

- **Summary**, **Context and constraints**: what the story achieves, the decisions that bind it, pitfalls, dependencies.
- **Implementation sections**: one per session-sized slice. Ids are `S1`, `S2`, … and never change; later work appends a new id. Each slice cuts a complete path through the layers it touches and is verifiable on its own. A wide mechanical refactor is the exception: sequence it expand → migrate in batches → contract.
- Per section: **Subtask** (`none yet` until `/aw-to-subtasks` runs), **Steps**, **Files**, **Checks** (`verify_cmd` plus what is specific), **Acceptance criteria**.
- **Session order**, **Open questions**, **Risks**, **Out of scope**.
- `definition_of_done` set → link it instead of copying it.

A story that fits one session has one section.

## 5. Grill the plan

Load and follow the `aw-grilling` skill on the draft. After each round, update the plan and record the settled points under **Decisions from grilling**: the question, the decision, and why it won. Unresolved external inputs stay under Open questions. Flag contradictions between the issue, decision records and the code. Do not finalize until the user confirms shared understanding.

## 6. Write the story back when grilling moved it

Grilling changes scope, acceptance criteria, sometimes the statement itself. Carry that into the story, following the story-write protocol:

1. Re-read the issue (`aw issue view <id>`) immediately before writing; it changed since step 2 → stop and show what moved.
2. Show the old/new diff of the body and wait for approval.
3. `~/.agents/bin/aw issue update <id> --body-file - --dry-run`, then the same without `--dry-run`.
4. Keep every section you did not author. Never touch status, labels or the parent link. Acceptance criteria that are already ticked are appended to, never rewritten.

The story grew past the size rule in step 3 → go back to that rule instead of writing a bigger story.

## 7. Deliver

```bash
~/.agents/bin/aw plan path <id> --slug <slug>     # <slug>: 3-5 title words, kebab-case
```

- Write the plan to that path, creating directories as needed. An existing plan for the story is updated in place, never duplicated.
- Post a short comment on the issue linking the plan: `~/.agents/bin/aw issue comment <id> --body-file -`.
- Tell the user the next step is `/aw-to-subtasks <id>`.

## Rules

- One story per invocation.
- Never invoke `/aw-start-task` or `/aw-finalize` yourself.
- Out-of-scope items: propose them as issues; create them only when the user says so (`aw issue create --dry-run` first).
- No secret values in plans or issue comments.
