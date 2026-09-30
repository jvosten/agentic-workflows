---
name: aw-plan-story
description: Plan one session from an issue - gather the issue, its parent and linked docs, and project context, draft an implementation plan, grill it with the user, and save it for /aw-start-task. Use when the user says "plan story", "plan issue #N", "plan #N", or wants to turn an issue into a session plan.
allowed-tools: Bash(~/.agents/bin/aw config)
metadata:
  package: agentic-workflows
---

# Plan story

Request: $ARGUMENTS

Turn one issue (a "story": one session of work) into a plan the user has vetted, ready for `/aw-start-task #<N>`.

## 1. Load settings and pick the issue

```bash
~/.agents/bin/aw config
```

- An issue number is required when `tracker` is set. None given → ask, or offer open candidates (`gh issue list --state open` / `glab issue list`).
- `tracker = none` → plan from the user's description instead of an issue.
- Too large for one session → say so and propose a split before planning.

## 2. Gather context

- Read the issue with its comments:
  - `github`: `gh issue view <N> --json title,body,labels,comments`
  - `gitlab`: `glab issue view <N> --comments`
- Parent references (`Part of #M`, epics, task lists) → fetch the parent too, and read the design docs it links.
- Read `instructions_file` and follow its pointers to whatever the work touches: decision records (do not reopen decided choices), known pitfalls, reference docs.
- Where the work touches running systems, check their current state read-only instead of trusting docs.
- Facts you can look up are your job; ask the user only for decisions.

## 3. Draft the plan

1. **Summary**: one paragraph, what the story achieves and why.
2. **Context and constraints**: relevant decisions (cite them), pitfalls, dependencies.
3. **Steps**: ordered and executable: files to create or change (exact paths), and the check for each step (`verify_cmd` plus anything specific).
4. **Acceptance criteria**: from the issue, made concrete and testable.
5. **Open questions**
6. **Risks**: what could go wrong, blast radius, rollback.
7. **Out of scope**: deferred work; say which items deserve their own issue.

## 4. Grill the plan

Load and follow the `aw-grilling` skill on the draft. Update the plan after each round of answers. Unresolved external inputs stay under Open questions. Do not finalize until the user confirms shared understanding.

## 5. Deliver

- `plan_dir` set → write `<plan_dir>/<N>-<slug>.md` (slug: first 3–4 title words, kebab-case); create the directory if missing. Not set → show the final plan and ask where to keep it.
- Post a short comment on the issue that links the plan (`gh issue comment` / `glab issue note`).
- Tell the user the session starts with `/aw-start-task #<N>`.

## Rules

- One issue per invocation.
- Never invoke `/aw-start-task` or `/aw-finalize` yourself.
- Out-of-scope items: propose them as issues; file them only when the user says so.
- No secret values in plans or issue comments.
