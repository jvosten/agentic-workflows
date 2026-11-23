---
title: "Changelog entries name no request number and carry no version"
tags: []
status: "active"
date: "2026-11-23"
---

**Decision:** a session's changelog entry names no merge request number and no version. `aw mr next` and
`aw mr create --expect` are removed. Versioning is independent of the changelog and of `aw`: a release is its own
step (by hand, a make target or CI) that passes its heading line to `aw changelog collect` and bumps the version as
the project likes.

**Why:** parallel sessions that each pick the next number and version conflict on every merge. The request number
forced a lookup before opening, two race paths and a commit after opening. Fragment tools (towncrier, scriv,
changie) also take the version from the caller.

**Beat:** keeping the number via `aw mr next`; a version per request (conflicts on the version line); compiling and
bumping in `aw finish` after each merge (pushes to the main branch, and `aw` would know the version file).

**Reopen when:** a project needs the request number in its changelog; then derive it at collect time from git
(merge commit subject), never at write time.

**Source:** BACKLOG item "REFACTOR: functions without a prescribed implementation".

_Implemented 2026-11-23_
