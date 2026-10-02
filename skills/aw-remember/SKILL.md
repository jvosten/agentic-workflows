---
name: aw-remember
description: Record a decision or a gotcha in the project's memory - append one entry to .agents/memory so the next session starts knowing it. Use when the user says "remember this", "note that down", or wants a decision or pitfall kept for later sessions.
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw memory add:*) Bash(~/.agents/bin/aw memory supersede:*) Bash(~/.agents/bin/aw session)
metadata:
  package: agentic-workflows
---

# Remember

Request: $ARGUMENTS

Put one fact into the project's committed memory, now, while it is fresh.

## 1. Decide whether it qualifies

| Keep | Drop |
|---|---|
| A decision the team settled, and why it won | Anything derivable from the code |
| A constraint that cost someone time (version pin, API quirk, ordering rule) | Personal preferences |
| A reference the code cannot show (why a workaround exists) | Secrets, tokens, credentials, internal URLs with keys |

Not sure it will matter next month → say so and stop. Entry 181 that nobody reads costs more than the fact is worth.

## 2. Check for an entry that already covers it

Read `<memory_dir>/decisions.md` and `<memory_dir>/gotchas.md`. An existing entry says something weaker, narrower, or now wrong → supersede it instead of adding a second version:

```bash
~/.agents/bin/aw memory supersede <decision|gotcha> --title "<existing title>" --reason "<what changed>"
```

## 3. Write it

```bash
~/.agents/bin/aw memory add <decision|gotcha> --title "<the claim>" --body-file - [--ref <issue>]
```

- **Title is the fact as a claim**: `boto3 is pinned below 1.36`, not `About boto3`. The title alone has to carry the point: a session reads these files whole.
- **Body**: two or three sentences. What holds, why, and what breaks when it is ignored.
- `--ref`: the issue of the current session (`aw session` prints it) when there is one.

## 4. Confirm

Print the file and the entry title. The file is committed with the session's work, so the entry lands in review with the change that taught it.

## Rules

- One fact per entry. Two facts → two entries.
- Never record a secret value, not even an example.
- Never rewrite an entry in place; supersede it.
