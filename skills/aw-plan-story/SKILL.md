---
name: aw-plan-story
description: Plan one story - gather the issue, its parent, children and linked docs, draft an implementation plan in session-sized sections, grill it with the user, and save it for /aw-to-subtasks. Use when the user says "plan story", "plan issue #N", "plan PROJ-123", or wants to turn an issue into a session plan.
allowed-tools: Bash(~/.agents/bin/aw memory supersede:*) Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw template plan) Bash(~/.agents/bin/aw plan path:*) Bash(~/.agents/bin/aw plan state:*) Bash(~/.agents/bin/aw issue view:*) Bash(~/.agents/bin/aw issue children:*) Bash(~/.agents/bin/aw issue list:*) Bash(~/.agents/bin/aw issue search:*) Bash(~/.agents/bin/aw issue update:*) Bash(~/.agents/bin/aw issue comment:*) Bash(~/.agents/bin/aw memory add:*) Bash(~/.agents/bin/aw memory find:*) Bash(~/.agents/bin/aw memory show:*) Bash(~/.agents/bin/aw memory tags:*)
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
- Read `instructions_file` and follow its pointers to whatever the work touches: reference docs, runbooks.
- Project memory:
  - Decisions in force: `~/.agents/bin/aw memory find --kind decision --compact`. Do not reopen them; `aw memory show <id>` for the reasoning of one.
  - Gotchas: pick the tags this story touches from `~/.agents/bin/aw memory tags --verbose`, by the tools of the files and systems the plan will change and by what the story names. Then `~/.agents/bin/aw memory find --kind gotcha --tags <tag,tag> --compact`.
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
- A step whose result has to be live before the next one can be built or checked (a GitOps reconcile, a migration, a deploy) is followed by `Checkpoint: merge and verify <what, live>`. The session then merges more than once (`/aw-checkpoint`), and every checkpoint is a deploy: name what the live check looks at in **Checks**. Few checkpoints are better than many.
- **Session order**, **Open questions**, **Risks**, **Out of scope**.
- **Known gotchas**: the lines of the gotcha `find` above, as printed (`- <id> · <title>`). Do not copy entries in full; a session runs `aw memory show <id>` for one. Write the tags you chose on the line above the list.
- **Decisions in force**: the decision index from step 2, as printed.
- `definition_of_done` set → link it instead of copying it.

A story that fits one session has one section.

## 5. Grill the plan

Load and follow the `aw-grilling` skill on the draft. After each round, update the plan and record the settled points under **Decisions from grilling**: the question, the decision, and why it won. Unresolved external inputs stay under Open questions.

The plan is the only record while it is drafted and grilled. Write nothing to project memory in this step: no decision after an answer, no gotcha from a probe. Hypotheses, alternatives, open questions and what a probe showed (a library call that worked, a limit you hit) stay in the plan as evidence; a pitfall you predict is a risk in the plan, not a gotcha. Flag contradictions between the issue, decision records and the code. Do not finalize until the user confirms shared understanding.

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
- Decisions go into the project's memory once, here, and only after the user approved the settled plan as a whole: not after each answer, not for alternatives still open. Only decisions that outlive this story (they bind work beyond it) and that a later session would otherwise reopen, one entry each:

  ```bash
  ~/.agents/bin/aw memory find --kind decision --text <two or three words> --compact    # one already covers it?
  ~/.agents/bin/aw memory add decision --intent --title "<the decision as a claim>" [--tags <tag,tag>] --body-file - --ref <id>
  ```

  - `--intent`: the plan accepts it, nothing builds it yet. It shows as `(intent: accepted, not built yet)` until the session that builds it runs `aw memory implemented`. Without `--intent` only when the code already does what it says.
  - Body: the decision, why it won, the alternatives it beat, what would reopen it, and the plan path. Not the plan's contract: the plan stays the one source for steps and details.
  - An entry already covers it: the same → write nothing; changed by this plan → write the new one and `aw memory supersede <old> --by <new>`. A revised plan never adds a second entry for the same choice.
- No gotchas from planning. A gotcha needs an experience: a session that hit the symptom, verified the cause and tested the fix.
- Post a short comment on the issue linking the plan, by its path relative to the repo root: `~/.agents/bin/aw issue comment <id> --body-file -`. `plan_scope = local` → no path; say only that a plan exists and who holds it.
- Tell the user the next step is `/aw-to-subtasks <id>`.

## Rules

- One story per invocation.
- Never invoke `/aw-start-task` or `/aw-finalize` yourself.
- Out-of-scope items: propose them as issues; create them only when the user says so (`aw issue create --dry-run` first).
- Every create (splits, out-of-scope items) sets each `board_required` field from `aw config`, as `aw-to-story` does.
- No secret values in plans or issue comments.
