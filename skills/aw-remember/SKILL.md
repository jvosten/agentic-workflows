---
name: aw-remember
description: Record a decision or a gotcha in the project's memory - one file per entry under .agents/memory, tagged, so later sessions find it. Use when the user says "remember this", "note that down", or wants a decision or pitfall kept for later sessions.
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw session) Bash(~/.agents/bin/aw memory add:*) Bash(~/.agents/bin/aw memory find:*) Bash(~/.agents/bin/aw memory show:*) Bash(~/.agents/bin/aw memory tags:*) Bash(~/.agents/bin/aw memory supersede:*)
metadata:
  package: agentic-workflows
---

# Remember

Request: $ARGUMENTS

Put one fact into the project's committed memory, now, while it is fresh.

## 1. Decide what it is

| Kind | What it is | Where it goes |
|---|---|---|
| **gotcha** | External tool behavior that bites: a symptom, its cause, the fix. A version pin, an API quirk, an ordering rule, a tool that lies. | `aw memory add gotcha` |
| **decision** | What the project settled, and why it won over the alternatives. | `aw memory add decision` |
| **rule** | A workflow pitfall that bites whatever the tool: "never commit generated files", "run X before Y". | Not memory: propose the rule text for `instructions_file`; the user decides. |

Drop: anything derivable from the code, personal preferences, secrets of any kind. Not sure it will matter next month → say so and stop.

## 2. Check for an entry that already covers it

```bash
~/.agents/bin/aw memory find --text <two or three words> --compact
~/.agents/bin/aw memory show <id>
```

An existing entry says something weaker, narrower, or now wrong → write the new one, then retire the old one pointing at it:

```bash
~/.agents/bin/aw memory supersede <old id> --reason "<what changed>" --by <new id>
```

## 3. Write it

```bash
~/.agents/bin/aw memory tags --verbose      # the vocabulary: pick from it
~/.agents/bin/aw memory add <gotcha|decision> --title "<the claim>" --tags <tag,tag> --body-file - [--ref <issue>]
```

- **Title is the fact as a claim**: `boto3 is pinned below 1.36`, not `About boto3`. It becomes the file name and the id, and plans list entries by it alone.
- **Tags**: the tools it is about, from the vocabulary. A gotcha needs at least one. No tag fits → add one to `<memory_dir>/tags.toml` with a one-line description, in the same change; do not stretch a tag that does not fit.
- **Gotcha body**: three short sections:

  ```markdown
  ## Symptom
  What you see when it bites: the error, the behavior.

  ## Cause
  Why it happens.

  ## Fix
  What to do instead, concretely.
  ```

- **Decision body**: what was decided, the reason it won, the alternatives it beat, and what would reopen it.
- `--ref`: the issue of the current session (`aw session` prints it) when there is one.

## 4. Confirm

Print the file path and the title. The file is committed with the session's work, so the entry lands in review with the change that taught it.

## Rules

- One fact per entry. Two facts → two entries.
- Never record a secret value, not even an example.
- Never edit an entry's meaning in place, and never delete one; write the new one and retire the old.
