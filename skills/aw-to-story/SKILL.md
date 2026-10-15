---
name: aw-to-story
description: Turn the current conversation into a user story on the tracker, or rewrite an existing one - synthesize what was discussed, fill the story template, and create or update the issue after review. Use only when the user invokes it.
disable-model-invocation: true
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw template story) Bash(~/.agents/bin/aw issue view:*) Bash(~/.agents/bin/aw issue list:*) Bash(~/.agents/bin/aw issue create:*) Bash(~/.agents/bin/aw issue update:*)
metadata:
  package: agentic-workflows
---

# To story

Request: $ARGUMENTS

Synthesize the conversation into one story. Do not interview the user beyond the gaps named in step 3.

An issue id in the request means rewrite that story; no id means create one.

## 1. Load settings and the template

```bash
~/.agents/bin/aw config
~/.agents/bin/aw template story
```

On error, show it and stop.

## 2. Gather what is already known

- The conversation is the source. Use it before anything else.
- Rewriting → `~/.agents/bin/aw issue view <id>` first: the current body is a source too, and what it carries beyond the template stays.
- Read `instructions_file` and the project's domain terms; write the story in the project's vocabulary.
- A parent is named (epic, story id) → `~/.agents/bin/aw issue view <id>` for its scope and constraints.
- Check the code only to confirm facts the story asserts. Facts are your job; decisions are the user's.
- A cheap subagent can do this gathering (`subagent_model`, when set). Keep the writing yourself.

## 3. Fill the template, then close the gaps

Fill every slot of the story template. Where the conversation never named one, ask — in **one** round, numbered, with your recommended answer:

- the persona, when "as a …" would be a guess;
- the benefit, when "so that …" would be a guess;
- acceptance criteria that decide done, when none were discussed.

Do not grill. `/aw-plan-story` does that later, on the plan.

## 4. Size check

More than about five session-sized slices, more than one deployable outcome, or acceptance criteria spanning two personas → say so and propose splitting into several stories. Create what the user approves, one issue per story.

## 5. Create or update after review

New story:

```bash
~/.agents/bin/aw issue create --title "<title>" --body-file - --dry-run   # show it first
~/.agents/bin/aw issue create --title "<title>" --body-file - [--parent <id>]
```

The parent (epic, parent story) goes in `--parent` only, as the tracker's native link, never into the body.
Labels the project requires on new issues (`instructions_file`) → `--label` on the create. With `board_fields` in `aw config`, include one label per mapped prefix (e.g. `area/...`, `priority/...`); `aw issue create` sets the board field from it. With `board_required`, every field it lists gets a value: from a mapped label, otherwise `--field Name=Option`. Propose each value from the story (its urgency, its size) and show it in the payload, so the user confirms it with the rest; the dry run names the options of a field still missing.

Existing story — follow the story-write protocol:

1. Re-read the issue (`aw issue view <id>`) immediately before writing; it changed since step 2 → stop and show what moved.
2. Show the old/new diff of the body and wait for approval.
3. `~/.agents/bin/aw issue update <id> --title "<title>" --body-file - --dry-run`, then the same without `--dry-run`.
4. Keep every section you did not author. Never touch status, labels or the parent link.

Print the issue ref and say the next step is `/aw-plan-story <id>`.

## Rules

- No file paths, code snippets or step-by-step implementation in a story.
- Acceptance criteria are testable conditions, not tasks.
- Create nothing without an explicit go from the user.
- Acceptance criteria that are already ticked are appended to, never rewritten.
- No secret values in the issue body.
