---
name: aw-backlog-item
description: Turn the current discussion into one backlog item - write it to the repo backlog, then optionally push it to the tracker after a duplicate check. Use when the user says "backlog item", "capture this as tech debt", "wrap this up for later", or wants deferred work recorded.
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw backlog add:*) Bash(~/.agents/bin/aw backlog pop:*) Bash(~/.agents/bin/aw issue dupes:*) Bash(~/.agents/bin/aw issue children:*) Bash(~/.agents/bin/aw issue view:*) Bash(~/.agents/bin/aw issue create:*) Bash(~/.agents/bin/aw issue set-parent:*) Bash(~/.agents/bin/aw issue set-status:*) Bash(~/.agents/bin/aw session)
metadata:
  package: agentic-workflows
---

# Backlog item

Request: $ARGUMENTS

Capture deferred work as one self-contained item. The repo backlog is the default home; the tracker is an option, not the goal.

## 1. Load settings

```bash
~/.agents/bin/aw config
```

`backlog_file` empty → ask where the item should go, or offer to push it straight to the tracker. On error, show it and stop.

## 2. Draft one item

Read `backlog_file` first and copy the shape its items already use. Where it has none:

```markdown
## <Title: the outcome, as an active phrase>

**Context:** what triggered this — the observation, review comment, decision record or constraint that surfaced it.

**Problem:** what is wrong and why it matters.

**Scope:** the concrete work, as a short list.

**Acceptance criteria:** testable, binary outcomes.

**Effort:** small | medium | large, with a one-line reason.
```

- One item per invocation. Two subjects → two items, written one at a time.
- Self-contained: a session six weeks from now must not need this conversation.
- Plain Markdown, so it survives a copy into the tracker. No tables unless they carry data.
- Keep implementation detail concrete, but do not over-prescribe where the design is open.

## 3. Write it locally

```bash
~/.agents/bin/aw backlog add --title "<title>" --body-file -
```

It places the item with the file's other items and matches their heading level. Show the user what was written.

## 4. Offer the tracker

Ask whether this should also live on the tracker. No → you are done; say where the item landed.

Yes, and `tracker` is not `none`:

```bash
~/.agents/bin/aw issue dupes <backlog_parent> --terms "<term>" "<term>" "<term>"
```

- Terms: the subject and the outcome, two to four of them. Matching is fuzzy; expect loose hits.
- Treat a candidate as a duplicate **only** when it targets the same subject **and** the same outcome. Adjacent, enabling or related work is not a duplicate.
- Closed candidates count: "we already did this, see the closed one" is an answer.
- Show every candidate with its state and let the user decide. Never skip the create on a weak match, never merge silently.
- `backlog_parent` unset → ask which issue the item should hang under, or none.

## 5. Pick the parent

`backlog_parent` is the default, not the only choice. Show the tree under it, two levels:

```bash
~/.agents/bin/aw issue children <backlog_parent>
~/.agents/bin/aw issue children <child>          # for each child that can hold items
```

Offer a numbered list — `backlog_parent` first, marked as the default, then its children and grandchildren with their type and title, then *none*. Recommend the narrowest one whose scope covers the item. The user picks.

Rows marked `[text link]` are linked to the tree only by a line in a body. They can still be a parent; say that they are not natively in the tree.

## 6. Create after confirmation

Show the payload — parent, issue type, title, full body — and wait for an explicit go.

```bash
~/.agents/bin/aw issue create --title "<title>" --body-file - [--parent <parent>] [--type <backlog_type>] --dry-run
~/.agents/bin/aw issue create --title "<title>" --body-file - [--parent <parent>] [--type <backlog_type>]
~/.agents/bin/aw issue set-status <new id> backlog      # trackers with workflow states
```

- Title becomes the summary unchanged. The full item body becomes the description; do not shorten it.
- The parent is set by `--parent` only, as the tracker's native link. Never write it into the body (`Part of #N`, `Epic: KEY`, a parent line under Links).
- A warning that `--type` was ignored (GitHub repos owned by a user) → report it; the issue was still created.
- An issue exists but is not under the chosen parent → fix the link with `aw issue set-parent <new id> <parent> --dry-run`, then without `--dry-run`. Never create it again.
- `set-status` fails because the tracker has no such state → report the actual state, do not retry.

## 7. Pop the local copy

Only after the create is confirmed and you have the new id:

```bash
~/.agents/bin/aw backlog pop --title "<title>"
```

The tracker is now the single source of truth for that item. Print the new issue ref and the file it left.

A create that failed → leave the local item alone and say so.

## Rules

- Never create on the tracker without an explicit go.
- Never pop an item that was not confirmed created.
- No secret values in items, bodies or comments.
