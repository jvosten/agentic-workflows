---
name: aw-backlog-item
description: Capture deferred work as one backlog item - note it in the backlog file during a session, or put it on the tracker after a duplicate check; also empties the session inbox for aw-finalize. Use when the user says "backlog item", "note this for later", "capture this as tech debt", "wrap this up for later", or wants deferred work recorded.
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw session) Bash(~/.agents/bin/aw backlog add:*) Bash(~/.agents/bin/aw backlog list) Bash(~/.agents/bin/aw backlog pop:*) Bash(~/.agents/bin/aw issue dupes:*) Bash(~/.agents/bin/aw issue children:*) Bash(~/.agents/bin/aw issue view:*) Bash(~/.agents/bin/aw issue create:*) Bash(~/.agents/bin/aw issue set-parent:*) Bash(~/.agents/bin/aw issue set-status:*)
metadata:
  package: agentic-workflows
---

# Backlog item

Request: $ARGUMENTS

Capture deferred work as one self-contained item, in the place the project keeps its backlog.

## 1. Load settings and pick the mode

```bash
~/.agents/bin/aw config
~/.agents/bin/aw session      # fails outside a session worktree; that is an answer, not an error
```

`backlog_home` decides; with `tracker = none` it is always `file`.

| `backlog_home` | Session | What to do |
|---|---|---|
| `tracker` | yes | **Note**: steps 2–3, then stop. `/aw-finalize` sends the item to the tracker or discards it. |
| `tracker` | no | **Push**: step 2, then 4–6. No file. |
| `file` | either | **Keep**: steps 2–3, then offer the tracker (4–7). |

- The user wants it on the tracker right away → steps 4–7 in any mode.
- The request says to empty the inbox (from `/aw-finalize`) → [Emptying the inbox](#emptying-the-inbox).
- `backlog_file` empty → ask where the item should go, or push it to the tracker. On error, show it and stop.

## 2. Draft one item

Read `backlog_file` first, if it exists, and copy the shape its items already use. Where it has none:

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

## 3. Write it to the file

```bash
~/.agents/bin/aw backlog add --title "<title>" --body-file -
```

It places the item with the file's other items and matches their heading level. Show the user what was written.

- **Note** mode: say it is in the session inbox and that `/aw-finalize` will ask whether it goes to the tracker or is discarded. Stop here. Do not commit the file for this; finalize handles it.
- **Keep** mode: ask whether the item should also live on the tracker. No → done; say where it landed.

## 4. Check for duplicates

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

Labels: read `instructions_file` for the labels the project requires on new issues of this kind, and pass each with `--label`.

Show the payload — parent, issue type, labels, title, full body — and wait for an explicit go.

```bash
~/.agents/bin/aw issue create --title "<title>" --body-file - [--parent <parent>] [--type <backlog_type>] [--label <label> ...] --dry-run
~/.agents/bin/aw issue create --title "<title>" --body-file - [--parent <parent>] [--type <backlog_type>] [--label <label> ...]
~/.agents/bin/aw issue set-status <new id> backlog
```

- Title becomes the summary unchanged. The full item body becomes the description; do not shorten it.
- The parent is set by `--parent` only, as the tracker's native link. Never write it into the body (`Part of #N`, `Epic: KEY`, a parent line under Links).
- An unknown label fails before anything is created. Report it; do not create labels yourself.
- A warning that `--type` was ignored (GitHub repos owned by a user) → report it; the issue was still created.
- `set-status` also runs `on_issue_status`, which is where a project puts its board move. The project's rules require a step `aw` does not do (a board without that hook) → do it as the rules say, and suggest setting `on_issue_status` so the next item needs no manual step.
- An issue exists but is not under the chosen parent → fix the link with `aw issue set-parent <new id> <parent> --dry-run`, then without `--dry-run`. Never create it again.
- `set-status` fails because the tracker has no such state → report the actual state, do not retry.

## 7. Pop the local copy

Only for an item that came from the file, and only after the create is confirmed and you have the new id:

```bash
~/.agents/bin/aw backlog pop --title "<title>"
```

The tracker is now the single source of truth for that item. Print the new issue ref and the file it left. In the session inbox, popping the last item deletes the file.

A create that failed → leave the local item alone and say so.

## Emptying the inbox

`/aw-finalize` loads this skill to empty the session inbox (`backlog_home = tracker`):

```bash
~/.agents/bin/aw backlog list
```

Go through the items one at a time. Show each one in full and ask: **send** to the tracker, or **discard**?

- Send → steps 4–7 for that item. The item text may be rough; tighten it to step 2's standard before showing the payload.
- Discard → `~/.agents/bin/aw backlog pop --title "<title>"`.
- Keeping an item in the file is not an option: the inbox does not survive the session, and `aw finish` refuses while it holds items.

Report what was sent (with issue refs) and what was discarded.

## Rules

- Never create on the tracker without an explicit go.
- Never pop an item that was not confirmed created, except on an explicit discard.
- No secret values in items, bodies or comments.
