# Issue status and boards

How `aw` moves issues through their states, and what that looks like on each tracker. Configuration keys are in [`src/aw/schema.toml`](../src/aw/schema.toml).

## The model

### Five canonical statuses

Skills and commands speak one vocabulary, whatever the tracker calls things:

| Status | Means |
|---|---|
| `backlog` | captured, not scheduled |
| `ready` | scheduled, can be picked up |
| `in_progress` | a session is working on it |
| `in_review` | waiting for review |
| `done` | merged or otherwise finished |

`status_map` translates them into the tracker's names: a Jira workflow status, or a column on a GitHub board. Unmapped statuses use title case (`in_progress` → `In Progress`). Names match case-insensitively, so `In Progress` also finds a column called `In progress`.

```toml
status_map = { backlog = "To Do", in_review = "Code Review" }
```

### When the status changes

| Event | Target | Guarded |
|---|---|---|
| `aw issue set-status <id> <status>` | any | no: someone chose that state |
| `aw start-task … --issue <id>` | `in_progress` | yes |
| `aw finish` | `done` | no: merged work is done, from any state |
| `aw issue create` | `backlog` | GitHub with a board only; elsewhere the tracker's own default applies |

`/aw-backlog-item` runs `aw issue set-status <id> backlog` after each create. `sync_issue_status = false` turns off the moves at session start and finish; explicit `set-status` still works.

### The guard: automatic moves never go backwards

A session start moves the issue to `in_progress` only when its current state is `backlog`, `ready`, or nothing at all. Anything else stays where it is, and `aw start-task` says so (`PROJ-12 stays at Code Review: a session start moves only from backlog or ready`).

The current state is read from the tracker and mapped back through `status_map`. A name that maps to no canonical status counts as nothing, so an unmapped "To Do" does not block the move. This is why a card someone moved to review or done is never dragged back by a session that picks the issue up again.

### Trackers with and without states

- **With states** (Jira; GitHub with a board): `aw` moves the issue itself, at every event above.
- **Without states** (GitHub without a board, GitLab, no tracker): an issue is open or closed. Session start changes nothing on the tracker; the merge closes the issue through the closing keyword in the pull request (`pr_close_keyword`, e.g. `Fixes #12`). An explicit `set-status` opens or closes it.

### The hook

`on_issue_status` runs after every status change, on every tracker, also those without states:

```toml
on_issue_status = "scripts/notify.sh {issue} {status} {status_name}"
```

`{status}` is the canonical status, `{status_name}` its `status_map` name. It runs in the current checkout. A failing hook makes `aw issue set-status` exit non-zero; at session start and finish it is a warning, because the session itself succeeded. A guarded start that does not move the issue does not run the hook either.

Use it for what `aw` does not do itself: a notification, a board on another system.

### What `aw` never does

- Change board or workflow configuration, or create columns, statuses or labels.
- Touch a board it was not pointed at.
- Move an issue backwards on its own.

## Per tracker

### GitHub without a board

The default with `tracker = "github"`. Issues are open or closed; projects boards in the repository are ignored, and `aw doctor` does not mention them.

| Event | Effect |
|---|---|
| `set-status done` | closes the issue |
| `set-status` anything else | reopens a closed issue, otherwise nothing |
| session start | nothing on GitHub; the hook runs |
| `aw finish` | the pull request's closing keyword closed the issue at the merge; the hook runs |
| create | an open issue, on no board |

### GitHub with a Projects board

A GitHub issue has no workflow state, but a Projects board does: its single-select **Status** field. Pointing `aw` at the board makes that field the issue's state:

```toml
github_project = "jvosten/1"     # owner/number; user- or organization-owned
status_field = "Status"          # the default
```

`aw init` asks for `github_project` when `tracker = github`. The token needs the `project` scope: `gh auth refresh -s project`.

| Event | Effect |
|---|---|
| `set-status <status>` | opens or closes the issue as above, and sets the card's column; a card not yet on the board is added first |
| session start | card to `in_progress`, guarded |
| `aw finish` | issue closed if it is not, card to `done` |
| create | the new issue goes on the board as `backlog` |

Details:

- Field and column ids are read from the board at run time, so a renamed column fails loudly instead of writing to the wrong one. A missing column fails before anything changes and lists the columns that exist.
- Create checks the `backlog` column before it creates the issue. If the issue is created but the board step fails, the error names the new issue and the repair, `aw issue set-status <id> backlog`; creating it again would make a duplicate.
- A card already in the target column is left alone.

**Board workflows.** GitHub boards have built-in workflows (item added → a column, item closed → Done, auto-add). They can be switched on only in the GitHub UI; the API can read them but not enable them. `aw` does not need them, and works next to them:

| Board workflow | Off | On |
|---|---|---|
| Item added to project | `aw issue create` sets Backlog itself; cards added by hand get no status | both set a column on add; keep it the same as `status_map.backlog` |
| Item closed | issues closed outside `aw finish` stay out of Done | both move closed issues to Done |
| Auto-add (sub-)issues | issues created outside `aw` stay off the board | `aw` adds the card itself either way |

When a workflow and `status_map` name different columns for the same moment, whichever runs last wins. Keep them consistent.

`aw doctor` checks the scope, the board, the field, and the columns for `backlog`, `in_progress`, `done` and every `status_map` key. Workflows that are off appear as notes, not problems:

```
  ✓ Tools         6 checks ok · 2 notes
      · board workflow 'Item added to project' is off: cards added by hand get no status; aw issue create sets Backlog itself
      · board workflow 'Item closed' is off: issues closed outside aw finish stay out of Done
```

### Jira

Jira has states natively: a Jira board is a view of the workflow's statuses, so there is nothing to opt into. Moving the status moves the card.

| Event | Effect |
|---|---|
| `set-status <status>` | runs the transition whose target status (or transition name) matches the `status_map` name; already there → nothing |
| session start | `in_progress`, guarded |
| `aw finish` | `done` |
| create | the issue starts in the workflow's initial status; `aw` does not change it |

- A status the workflow cannot reach from the current one fails with the transitions that are available: `no transition to 'Backlog' (available: In Progress, Done); set status_map.backlog`.
- Map to your workflow's names. A new issue often starts in "To Do", and `/aw-backlog-item` then sets `backlog`; without `status_map = { backlog = "To Do" }` that looks for a status called "Backlog".
- `aw doctor` checks credentials, the login and `jira_project`, not yet the statuses (see the backlog).

### GitLab

Issues are open or closed, as on GitHub without a board: `set-status done` closes, anything else reopens; the merge request's closing keyword closes at the merge. GitLab boards are lists of scoped labels (`workflow::in progress`), which `aw` does not drive yet; the hook can. The GitLab adapter is not tested against a live instance.

### No tracker

With `tracker = none` there are no issue states. `aw issue set-status` is not available; session start and finish run only the hook, when one is set and the session was started with `--issue`.
