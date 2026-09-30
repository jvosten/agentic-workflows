---
name: aw-plan-story
description: Plan one session from an issue - gather the issue, its parent, children and linked docs, and project context, draft an implementation plan, grill it with the user, and save it for /aw-start-task. Use when the user says "plan story", "plan issue #N", "plan PROJ-123", or wants to turn an issue into a session plan.
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw issue view:*) Bash(~/.agents/bin/aw issue children:*) Bash(~/.agents/bin/aw issue list:*) Bash(~/.agents/bin/aw issue search:*)
metadata:
  package: agentic-workflows
---

# Plan story

Request: $ARGUMENTS

Turn one issue (a "story": one or more sessions of work) into a plan the user has vetted, ready for `/aw-start-task <id>`.

## 1. Load settings and pick the issue

```bash
~/.agents/bin/aw config
```

- An issue id (`#12`, `PROJ-123`) is required unless `tracker = none`. None given → ask, or offer candidates from `~/.agents/bin/aw issue list`.
- `tracker = none` → plan from the user's description instead of an issue.
- Optional inputs the user may name: design docs or decision records, test files, doc files. Read each one.

## 2. Gather context

- `~/.agents/bin/aw issue view <id>`: description, extra fields (e.g. acceptance criteria), children, comments, parent.
- Parent → `aw issue view <parent>` too, and read the design docs it links.
- Read `instructions_file` and follow its pointers to whatever the work touches: decision records (do not reopen decided choices), known pitfalls, reference docs.
- Where the work touches running systems, check their current state read-only instead of trusting docs.
- Facts you can look up are your job; ask the user only for decisions.
- The user asks for research on an approach → compare the options in a table and recommend one.

## 3. Draft the plan

1. **Summary**: one paragraph, what the story achieves and why.
2. **Context and constraints**: relevant decisions (cite them), pitfalls, dependencies.
3. **Sections**: one per session-sized unit of work. For each:
   - **Goal**
   - **Children covered**: which child issues it implements, if the issue has any. Respect the existing breakdown; propose regrouping when it is technically better.
   - **Steps**: ordered and executable, with exact file paths.
   - **Checks**: `verify_cmd` plus what is specific to the section.
   - **Acceptance criteria**: from the issue, made concrete and testable.
4. **Session order**: sequence of sections; mark which can run in parallel.
5. **Open questions**
6. **Risks**: what could go wrong, blast radius, rollback.
7. **Out of scope**: deferred work; say which items deserve their own issue.

A story that fits one session has one section.

## 4. Grill the plan

Load and follow the `aw-grilling` skill on the draft. Update the plan after each round of answers. Unresolved external inputs stay under Open questions. Flag contradictions between the issue, decision records, and the code. Do not finalize until the user confirms shared understanding.

## 5. Deliver

- `plan_dir` set → write `<plan_dir>/<plan_file>`, filling its placeholders: `{issue}` id, `{slug}` first 3–5 title words in kebab-case, `{parent}` and `{parent_slug}` from the parent (lowercase the ids), `{date}` today as YYYY-MM-DD. Create directories as needed. Not set → show the final plan and ask where to keep it.
- Post a short comment on the issue that links the plan: `~/.agents/bin/aw issue comment <id> --body-file -`.
- Tell the user each section starts with `/aw-start-task <id>`.

## Rules

- One issue per invocation.
- Never invoke `/aw-start-task` or `/aw-finalize` yourself.
- Out-of-scope items: propose them as issues; create them only when the user says so (`aw issue create --dry-run` first).
- No secret values in plans or issue comments.
