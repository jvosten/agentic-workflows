---
title: "aw is a vessel for functions it does not prescribe"
tags: []
status: "intent"
date: "2026-11-23"
---

**Decision:** where `aw` supports a function whose implementation differs between projects (changelog first;
backlog and verification next), it does not prescribe one. Each such function gets:

- one choice key in the config, mapped to a closed enum and matched once in code;
- one protocol with a few operations; `aw` owns only what must not vary (where an entry goes, whether it exists,
  the fold), never a format, category set or versioning scheme;
- a lightweight built-in strategy as the default `aw` offers (for the changelog: one fragment file per session);
- later, presets for common external tools (a preset is only a list of commands, no format logic), detected by
  `aw init` or declared by the user, and a `cmd` strategy as the escape hatch for anything else.

Contract tests run against every strategy and a fake, so the protocol cannot drift towards the built-in format.

**Why:** projects run changelogs, backlogs and checks in many ways; one prescribed way makes `aw` unusable for the
rest, and loose keys plus skill prose give no extension point.

**Beat:** one key per variant (`changelog_file`, `changelog_dir`, ... as independent switches); a full built-in
tool with categories and versions; no built-in at all (every project writes its own fold).

**Reopen when:** a function needs an operation that cannot be stated without a format, or presets start to carry
format logic.

**Source:** BACKLOG item "REFACTOR: functions without a prescribed implementation".
