# agentic-workflows

Generic agent skills that give every project the same session workflow. Project differences live in a committed config file that the skills read, not in the skills.

Skills follow the [Agent Skills](https://agentskills.io/specification) format and install to `~/.agents/skills/`. Pi, Codex, Cursor, Gemini CLI, OpenCode and Copilot read that directory directly. Claude Code does not, so `aw install` links each skill into `~/.claude/skills/` as well.

## Install

Requires `git`, `make` and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone <this repo> ~/projects/agentic-workflows
cd ~/projects/agentic-workflows
make install       # installs the `aw` CLI, links skills and ~/.agents/bin/aw
make doctor
```

`make install` runs two steps: `uv tool install --editable .` puts `aw` into uv's tool directory (usually `~/.local/bin`), and `aw install` links each skill into `~/.agents/skills/` (plus `~/.claude/skills/`) and the CLI to `~/.agents/bin/aw`, the path every skill calls. Without the second step no agent sees the skills.

The editable install means edits to this repo take effect without reinstalling. Re-run `make install` after adding or removing a skill: it also prunes links to skills that are gone. It prints one summary line per target; `make install V=1` lists every link. It warns when `aw` is not on your PATH: skills still work, since they call `~/.agents/bin/aw`, and `uv tool update-shell` makes `aw` available in your shell.

The installed `aw` and every agent's skills run whatever this clone has checked out, in every project. Review someone else's branch in a worktree or another clone, never by checking it out here; `aw doctor` warns when the clone is off its default branch or has uncommitted changes in `src/` or `skills/`.

`make install` installs the tool; `aw init` (below) configures one project.

Without a clone, install the package (not editable; the skills come from the package). While the repository is private, this needs read access and git credentials for it:

```bash
uv tool install git+https://github.com/jvosten/agentic-workflows
aw install
```

The package is the bundle: CLI and skills ship together, at one version. Not through `npx skills add`: it copies the skills without the `aw` CLI they call.

### Update

```bash
aw update          # from anywhere; inside a project it also checks that project
```

- Editable install: fast-forwards the clone's default branch from `origin`, whatever branch the clone has checked out, and lists the commits it gained. It refuses when the branch diverged from `origin` or when the update would overwrite uncommitted changes. With another branch checked out it warns: the installed `aw` runs that branch's code, not the updated one.
- Packaged install: `uv tool upgrade agentic-workflows`.
- Then, with the new code: `aw install` relinks the skills, adding new ones and pruning removed ones. Inside a project, `aw init --check` reports what `aw init` would change (pending migrations, a new `aw_version`, new keys it asks for) and writes nothing.

Agent sessions see the update without a restart: the CLI runs the new code on its next call, and Claude Code watches its skill directories (added, edited and removed skills). A skill already loaded into a conversation keeps the text it was loaded with; start the skill again, or a new session, to use the new version.

## Use the skills

This is the point of the package: one session workflow that you drive from your coding agent, in any repo. Set the repo up once with `aw init` (see [Set up a project](#set-up-a-project)), then call the skills.

| Harness | Call a skill | Skills come from |
|---|---|---|
| Pi | `/skill:aw-plan #12` | `~/.agents/skills/` |
| Claude Code | `/aw-plan #12` | `~/.claude/skills/`, linked by `aw install --agent claude` |
| Codex, Cursor, Gemini CLI, OpenCode, Copilot | name the skill in your request | `~/.agents/skills/` |

One session, start to finish:

1. `/aw-plan #12` — routes: no story yet → writes one, story without plan → plans it, plan without subtasks → cuts them. One step per call.
2. `/aw-plan-story #12` — reads the issue, its parent, children and the project docs, drafts a plan in session-sized sections, grills it with you, saves it under `.agents/plans/` (see [Plans](#plans)).
3. `/aw-to-subtasks #12` — one subtask per plan section, reconciled with the subtasks that exist, published after your approval, linked back into the plan.
4. `/aw-start-task PROJ-13` — creates the branch and worktree, loads that subtask's plan section as a task list, then implements it with you.
5. `/aw-finalize` — docs, `aw verify`, changelog entry, commit, pull request, review and CI. Then it stops at the green PR and merges only on your go (`merge_gate = approve`, the default; `auto` merges once CI and review are green).

For design work before planning, `/aw-grill-with-docs` interviews you and keeps `GLOSSARY.md` and `docs/adr/` current.

| Skill | Invocation | Does |
|---|---|---|
| `aw-plan` | user only | Reads `aw plan state` and hands over to the planning skill the work needs next |
| `aw-to-story` | user only | Conversation → user story on the tracker, from the `story` template; rewrites an existing story too |
| `aw-plan-story` | user or model | Story + parent + project context → plan in `S1`, `S2`, … sections, grilled with you |
| `aw-to-subtasks` | user only | Plan sections → subtasks, each a vertical slice with its blocking edges |
| `aw-start-task` | user only | Creates the session worktree via `aw start-task`, loads the plan section, hands over to implementation |
| `aw-checkpoint` | user or model | Merge one part mid-session: verify, part merge request, CI, gate, `aw merge`, live check, then the session goes on |
| `aw-merge-request` | user or model | Title and description from `CONTRIBUTING.md`, the merge request template and a show-the-change style; opens or updates it through `aw mr` |
| `aw-finalize` | user only | Docs, `aw verify`, changelog entry, commit, merge request (`aw-merge-request`), review + CI, your go at the green PR (`merge_gate`), then `aw finish` |
| `aw-grilling` | user or model | Interview in rounds over a design tree until nothing is assumed |
| `aw-grill-with-docs` | user only | `aw-grilling` plus `aw-domain-modeling` |
| `aw-domain-modeling` | user or model | Challenge terms, keep `GLOSSARY.md` and `docs/adr/` current |
| `aw-remember` | user or model | Append one decision or gotcha to the project's memory |
| `aw-backlog-item` | user or model | Discussion → one backlog item, repo-local, optionally pushed to the tracker |

User-only skills never start by themselves; the model may pick up the others when the task calls for them.

The story, subtask and plan documents follow templates: `aw template <name>` prints the bundled one, and the `templates` key points at your own.

## Plans

A plan lives at `plan_dir/plan_file`, by default `.agents/plans/<area>/<issue>-<slug>-<date>.md`. The area is the parent issue (`PROJ-1-upload-retries`), so the plans of one epic share a folder; an issue without a parent puts its plan directly under `.agents/plans/`. `aw plan path <id> --slug <slug>` composes the path; `aw plan path <id>` finds an existing plan by the issue id in its file name, and a subtask finds its story's plan through the parent link. Several plans for one issue are refused and listed: keep one.

`plan_scope` decides who sees plans:

| `plan_scope` | Where | For |
|---|---|---|
| `repo` (default) | committed, in the current checkout or worktree | teams; subtasks link to plan sections that anyone can open, and the plan stays as history |
| `local` | gitignored, always in the primary checkout, so every session worktree of this clone sees it | personal plans; the tracker subtasks and the project memory carry what others need |

`aw init --set plan_scope=local` adds `plans/` to `.agents/.gitignore`; `aw doctor` warns when a local plan directory is not ignored.

## Project memory

What the project learned is committed under `memory_dir` (default `.agents/memory`), one file per entry:

| Path | Holds |
|---|---|
| `gotchas/<slug>.md` | External tool behavior that cost someone time: symptom, cause, fix |
| `decisions/<slug>.md` | What the project settled, and why it won; `intent` while it is accepted but not built |
| `tags.toml` | The tag vocabulary: `flux = "Flux CD: kustomizations, HelmReleases"` |

Each file has a small frontmatter (title, tags, status, aliases, date, issue), one JSON value per field; a value of the wrong type, such as a YAML list `tags: [git, gh]`, is an error that names the file and the field. The slug comes from the title and is the entry's permanent id, unique across decisions and gotchas; numbers from an older numbering live on as aliases (`aw memory show 95`). Titles are claims (`boto3 is pinned below 1.36`): plans list entries by title alone. Entries are retired, never deleted. Parallel sessions write different files, so they never conflict. A workflow pitfall that bites whatever the tool is not a gotcha but a rule for `instructions_file`.

| Command | Does |
|---|---|
| `aw memory add <gotcha\|decision> --title T --tags a,b --body-file F [--ref ID] [--intent]` | Writes one entry; unknown tags are refused, a gotcha needs one, and a slug taken by either kind is refused. `--intent` (decisions only): accepted, not built yet |
| `aw memory find [--kind K] [--tags a,b] [--text terms…] [--compact]` | Entries with any of the tags and all of the terms; `--compact` prints `id · title` |
| `aw memory show <id\|alias>` | One entry |
| `aw memory tags [-v]` | The vocabulary with the number of active gotchas per tag |
| `aw memory supersede <id> --reason R [--by ID]` | Retires an entry |
| `aw memory implemented <id> [--ref ID]` | An intent decision is built: it becomes active, with a dated note |
| `aw memory import --json F` | Writes entries from JSON lines (`kind`, `title`, `slug`, `tags`, `aliases`, `date`, `issue`, `body` or `sections`); every line is checked before any file is written: a `slug` must look like one made from a title, and an existing entry is never overwritten |
| `aw memory load [--plan]` | What a session start reads |
| `aw memory log --relevant IDS --missed IDS` | One line for the gotchas experiment (gitignored) |

Converting an existing pitfalls table or decision log is a matter of producing those JSON lines, with a `jq` line, a short script or a model; `aw` checks and writes.

**Loading.** `gotchas_load = full` (default) loads every active gotcha at session start. `gotchas_load = tags` loads only the tags that have gotchas, with counts (about 150 tokens); `/aw-plan-story` pulls the gotchas matching the story's tags into the plan as `id · title` lines, and the session looks up the rest when a tool errors. The decision index goes into the plan; a session without a plan loads it at start. `tags` is an experiment: `/aw-finalize` records per session which gotchas mattered and which bit although they existed (`aw memory log`), and the defaults follow the result.

**Plan or memory.** A plan holds what is still provisional: hypotheses, alternatives, open questions, probe results, predicted pitfalls. Memory holds what held up. A gotcha is empirical: a symptom someone hit in implementation, debugging or operation, with a verified cause and a tested fix; a probe while planning is plan evidence, not a gotcha. A decision enters memory once, after the user approved the settled plan, never after a single grilling answer, and links the plan instead of copying it. Until something builds it, it is `intent` and every listing marks it `(intent: accepted, not built yet)`, so no session reads planned behavior as existing; the session that builds it runs `aw memory implemented`. A revised plan supersedes an entry, never adds a second one.

Writers: `aw-plan-story` once the plan is approved, for decisions that outlive the story, `aw-finalize` for gotchas the session paid for and intents it built, `/aw-remember` any time in between. Entries are written in the session worktree, so they are reviewed and merged with the work that taught them. `aw doctor` checks unknown tags, retired entries pointing nowhere and aliases claimed twice, and says how many tokens a session start loads.

## Backlog

Deferred work is captured with `/aw-backlog-item`, which `aw-finalize` also calls for anything a session chose not to do. `backlog_home` decides where it lives (`aw init` asks when a tracker is set):

| `backlog_home` | `backlog_file` (default `BACKLOG.md`) is | At the end of a session |
|---|---|---|
| `tracker` (default with a tracker) | a session inbox: items noted mid-session, without a tracker round trip | `aw-finalize` asks per item: send it to the tracker, or discard it. The emptied file is deleted, and `aw finish` refuses while it holds items. Outside a session, items go straight to the tracker. |
| `file` (always without a tracker) | the backlog itself, committed | items stay; any of them can be pushed to the tracker on request |

`aw backlog add` places an item among the file's existing items and copies their heading level and separators, so a flat `## Item` list and a sectioned `### [PRIO] Item` list both stay intact. `aw backlog list` prints the titles, `aw backlog pop` removes one.

Pushing an item to the tracker: `aw issue dupes <backlog_parent> --terms ...` shows candidates in any state, those under `backlog_parent` (two levels deep) first, then matches elsewhere in the project, you confirm, pick the parent (`backlog_parent` or one of its children and grandchildren, or none), `aw issue create --parent <parent> [--type <backlog_type>] [--label ...]` creates it with the tracker's native parent link, `aw issue set-status <id> backlog` files it (and runs `on_issue_status`), and `aw backlog pop` removes the local copy so one item does not live in two places.

## Merge requests

`/aw-merge-request` writes the merge request (a pull request on GitHub) for the current branch; `/aw-finalize` loads it. Three sources decide the content, strongest first:

1. **Rules** in `contributing_file` (default `CONTRIBUTING.md`): title format, required sections, labels, reviewers, draft policy, commit style.
2. **Template**: `aw template mr` resolves it — `templates.mr` when set; else the forge's own file (`mr_template` names one in `.gitlab/merge_request_templates/` or `.github/PULL_REQUEST_TEMPLATE/`; unset, GitLab's `Default.md` or GitHub's `pull_request_template.md`); else a bundled Summary / Evidence / Merge danger template. A named template that does not exist is an error; `aw doctor` checks it.
3. **Style** for the content inside the sections: the smallest diagram, tree or diff sketch that shows the change, before/after evidence, and whether the merge is a one-way door and how far it reaches. Adapted from [mattpocock/skills `pr`](https://github.com/mattpocock/skills/tree/main/skills/engineering/pr).

`aw mr` talks to the forge, so skills do not call `gh` or `glab` themselves. Its output is a compact summary, not the forge CLI's:

| Command | Does |
|---|---|
| `aw mr next` | The number the next request gets (`#12`): one above the newest issue, pull request or discussion on GitHub, merge request on GitLab. `/aw-finalize` writes it into the changelog entry before the request opens, so the entry is in the request's first pushed state |
| `aw mr create --title T --body-file F [--draft] [--expect N] [--dry-run]` | Opens the request from the current branch against `main_branch` (a stacked session: its base); refuses unpushed work; an open request for the branch is reported, never duplicated; appends the issue's closing line (`Fixes #12`) unless the body already closes exactly that issue (a closing keyword before `#12`; `see #12` or `#123` does not count); then checks what the request will close: the session issue missing is an error, any other issue a warning. `--expect N`: refuses before the create when the next number is not N, and exits 1 when a race gave the request another |
| `aw mr update [ref] --title T --body-file F` | Replaces title and description; keeps the closing line or the part reference `create` appended, and checks what the request closes, as `create` does |
| `aw mr view [ref]` | State, the issues it closes, CI, review, unresolved threads, files and lines changed: what the merge gate shows |
| `aw mr checks [ref] [--watch]` | One line of counts plus the failing and pending checks; `--watch` waits without streaming progress. Exit 0 passed, 1 failed, 2 pending. With CI in the checkout (`.github/workflows/*.yml`, `.gitlab-ci.yml`), no checks reported is `no checks yet` and exit 2, never a pass: `--watch` waits up to two minutes for the first one |
| `aw mr comments [ref]` | Unresolved review threads with file and line, then general comments; an author without write access is marked `[outside]` (`aw issue view` marks comments and the issue's author the same way), and the skills never act on such text. Write access is the repository permission (admin, maintain, write; GitLab: Developer or above), looked up once per author; whatever `aw` cannot tell, a deleted account or an app, is outside unless `trusted_bots` names it. Every body line is quoted (`> `), so no body can pass for an author line of its own |

`ref` is a number or branch, the current branch by default; `aw pr` is the same command. GitHub runs this repository's own pull requests: create, checks, comments, view, and `aw finish` merging, removing the worktree and deleting both branches. GitLab is taken from the `glab` documentation and not tested against a live instance yet.

## Sessions with several merges

Some changes have to be live before the next step can be built or checked: a GitOps reconcile, a migration, a deploy. Such a session merges more than once, on the same branch and worktree:

1. `/aw-plan-story` marks it: `Checkpoint: merge and verify <what>` after the step, with the live check under **Checks**.
2. `/aw-checkpoint` at that step: `aw verify`, docs this part makes wrong, commit, a part merge request (`aw mr create --part`, which references the issue as `Refs #12 (part N)` and does not close it), CI, the merge gate (every merge deploys), `aw merge`, the live check. A failed live check stops and asks: fix forward or revert.
3. The session goes on. `/aw-finalize` at the end fills only what is missing (memory, leftovers, inbox, one changelog entry for all parts); its merge request closes the issue and lists the earlier parts. Nothing left to merge (no commit `main` lacks, even when `main` moved on since) → `aw finish` skips the merge and closes the issue itself.

`aw merge [--pr N]` merges the branch's open request (`forge = none`: after a manual merge), refuses a request that is not at the branch's head (another branch's request, or commits pushed after it merged) before merging or cleaning up anything, updates `main`, and moves the branch to `main`'s tip: a fast-forward after a merge commit; after a squash or rebase merge a `reset --keep`, and the merged remote branch is deleted so the next `git push -u` needs no force. It comments on the issue (`Part 2 merged: #315`) and runs `on_merge` (e.g. `flux reconcile source git flux-system`), as `aw finish` does after the last merge. Worktree, branch and issue stay. Which parts merged and where a checkpoint stopped come from the forge and git, so an interrupted checkpoint resumes where it was.

A stacked checkpoint can verify, commit, push and open or update a draft part request while the base request is open. It targets and links the recorded base, runs CI and review, then waits before the merge gate. Resume reuses the same request; after the base merges, run `aw restack`, verify again and recheck CI on the new HEAD before seeking fresh approval when `merge_gate = approve`.

Promotion across environments and changes split across repos are not covered yet.

## Stacked sessions

Reviews take time. A session that builds on another session's unmerged branch starts on it instead of waiting:

```bash
aw start-task feat <slug> --base <branch>    # worktree from origin/<branch>
aw restack [--dry-run] [--json]              # follow the base, or move onto main once it merged
```

The session records the base and its *fork point*: the base commit it was cut from or last restacked onto. When rebasing, it runs `git rebase --onto <upstream> <fork point>`, so only the session's own commits are replayed, whatever happened to the base. Its merge request targets the base until the base merges; `aw merge` and `aw finish` refuse before that. `aw merge` and `aw finish` in the base session warn about every session stacked on it. Before they delete the remote branch, they retarget every open request into it to `main_branch`: a push that deletes the branch would close those requests instead, and a closed request cannot be retargeted. When the requests cannot be listed or moved, the remote branch stays, with a `kept origin/<branch>` warning.

| Event | `merge` | `squash` | `rebase` |
|---|---|---|---|
| Base gets new commits | restack onto `origin/<base>` | same | same |
| Base merged into `main` | restack onto `origin/main` (the base's commits are in `main` under the same ids, so nothing is replayed twice) | restack onto `origin/main`; without the fork point the base's commits would be replayed onto their own squash | same as squash |
| Merge request target | `aw finish` and `aw merge` in the base session retarget it before they delete the base branch; `aw restack` retargets when nothing else did | same | same |

Before it changes anything, `aw restack` refuses when the branch has no open request and one closed without merging at the branch's remote head: after a force-push, that request cannot reopen. Reopen it, or push the branch yourself to give it up. After the base merged, `aw restack` force-pushes (`--force-with-lease`), retargets and then clears the base; the session is an ordinary one from then on. The base's local worktree, local branch and remote branch may already be deleted: the forge confirms the merge, and restack uses `origin/main` and the recorded fork point, not the base's checkout.

Before rebasing, restack records its target as `restack_onto`. A conflict leaves the rebase in progress: resolve, `git rebase --continue`, `aw restack` again. While a rebase is active, restack refuses to start another one. Once the recorded target is an ancestor of `HEAD` and no rebase is active, it can recover even if the old fork point is no longer in the branch's history. If upstream still matches the target, it finishes the push and retarget without rebasing again. If upstream changed, including a base that merged while the rebase was paused, it uses the recovered target as the fork point and rebases only the session's own commits onto the current upstream. A failed push or retarget keeps the recovery metadata; rerun `aw restack` after addressing the failure. A changed remote branch still blocks the lease-protected push.

With no pending work and an unchanged base, a repeat run reports `up_to_date` without changing the branch; after the base is cleared it reports `not_stacked`. An unrelated manual rebase without a recorded target is not inferred: an invalid fork point still refuses. `--dry-run` may fetch, but never rebases, pushes, retargets or changes session metadata, including during recovery.

Output is one line per action and a summary line; `--json` gives the same as a structured result.

Not covered: `forge = none`, stacks deeper than two, and part merges (`aw merge`) in the base session beyond the warning.

## Set up a project

```bash
cd <repo>
aw init            # prompts, with defaults detected from the repo
aw init --yes      # accept detected defaults
aw init --set verify_cmd="make check"
aw doctor
```

`aw init` writes `.agents/aw.toml` (commit it) and `.agents/.gitignore`. Re-running it keeps existing answers as defaults and asks only what `schema.toml` added since. `aw init --check` shows what a run with `--yes` would change, writes nothing, and exits 1 when anything would change.

## Configuration

| Layer | Path | Scope |
|---|---|---|
| defaults | `src/aw/schema.toml` | built in |
| user | `~/.agents/aw/config.toml` | all projects on this machine |
| project | `<checkout>/.agents/aw.toml` | committed; read from the current checkout or worktree |
| local | `<primary>/.agents/aw.local.toml` | gitignored; this machine only |
| env | `AW_<KEY>` | one run |

Later layers win. `aw config --sources` shows which layer set each value. All keys, types and help texts are in [`src/aw/schema.toml`](src/aw/schema.toml).

**Trusted keys.** `merge_gate`, `merge_method`, `on_start`, `on_merge` and `on_issue_status` decide what runs or merges on the host, and `jira_base_url` where the Jira credentials go. In a session worktree their project value comes from the primary checkout's `.agents/aw.toml`, not from the branch's: a branch, perhaps written by an agent, never picks its own merge gate, hooks or credential host. The user, local and env layers apply as usual; `aw config --sources` shows such a value as `primary`. A branch that changes one of them takes effect once it has merged; until then `aw finish`, `aw merge` and `aw doctor` print `ignored from the branch: <keys>`.

**Paths.** Keys that name a file or directory (`instructions_file`, `changelog_file`, `contributing_file`, `backlog_file`, `memory_dir`, `definition_of_done`, `templates`, `plan_dir`, `plan_file`) are relative to the repo root. In the committed `.agents/aw.toml` they stay inside the repo: `~`, an absolute path or a `..` past the root is refused, and `aw` follows no link out of the repo where it reads or writes. A template shared by several projects goes into the user or local layer. `aw doctor` fails a path that links out of the repo.

**Private terms.** `private_terms` lists words that must never leave this machine: a private project, host or person. `aw issue create`, `update` and `comment`, `aw mr create` and `update`, `aw backlog add` and `aw memory add` refuse a text that names one (case-insensitive), and `aw doctor` lists tracked files that do. Set it in `~/.agents/aw/config.toml` or `.agents/aw.local.toml`: the committed file refuses it, since committing the list would publish it.

**Sandboxed sessions.** A sandbox runner sets `AW_SANDBOXED=1` (env only; a config file cannot set it). `aw finish`, `aw merge` and `aw issue rollup --close` then refuse with `sandboxed: <command> runs on the host`: the session pushes its branch, and the host merges, with its own configuration. This is a contract for runners, not a security boundary.

When a key changes shape, `schema.toml` lists a migration (rename, and a rewrite of the value where its meaning changed). A config file in the old shape keeps working: loading applies the migration in memory, `aw doctor` reports it as pending, and `aw init` writes it into `.agents/aw.toml`. Example: `on_issue_start = "make setup"` becomes `on_start = "[ -n {issue} ] && make setup"`, which still runs only when the session has an issue. Since `aw` quotes hook placeholder values itself, a second migration removes quotes written around a placeholder (`sync.sh "{status_name}"` becomes `sync.sh {status_name}`); a placeholder inside a longer quoted text (`"merged {pr}"`) cannot be rewritten safely, and `aw doctor` warns about it until it is moved out of the quotes.

## Sessions

A session is one worktree on one branch, from `aw start-task` to `aw finish`, and implements one subtask: one vertical slice that is verifiable on its own. Its worktree is named after the issue and the slug (`worktree_name`, default `{issue}-{slug}`, just `{slug}` without an issue); a path that exists already is refused, so two sessions never share one. Session metadata (branch, worktree, issue) lives in the worktree's private git dir and disappears with it.

A session that should not land (parked, or superseded) ends with `aw abandon`, never with `aw finish`: on a branch without changes, `aw finish` takes the nothing-left path and closes the issue.

The committed record of a session is its pull request and its changelog entry.

## Issue trackers

Skills never call a tracker directly; they call `aw issue <op>`, and `tracker` in the config picks the adapter.

| Op | github (`gh`) | jira (REST v3) | gitlab (`glab`, untested) |
|---|---|---|---|
| `view` (parent, children, comments, extra fields) | ✓ (parent: sub-issue link, `Part of #N` as fallback) | ✓ | ✓ (no parent/children/comments) |
| `children` (`--text-only`) | sub-issues + task-list refs, the latter marked `[text link]` | JQL `parent = KEY` | – |
| `set-parent <id> <parent>\|--none` (`--dry-run`) | sub-issue link, replaces an existing parent | `fields.parent` | – |
| `dupes` (parent, terms, any state; `--tree-only`) | hits in the native sub-issue tree first, then the rest of the repo marked `[elsewhere: …]`, ranked by terms matched | one JQL over `jira_project`, tree first | unscoped search, says so |
| `list`, `search` | ✓ | ✓ (`--raw` = JQL) | ✓ |
| `create` (with `--parent`, `--type`, `--label`, `--status`, `--field`, `--dry-run`) | one GraphQL call, so never left unlinked; `--type` on org-owned repos only; `--field` with `github_project` | ✓ (Markdown → ADF; no `--field` yet) | – |
| `update` (title, description; `--dry-run`) | ✓ | ✓ | – |
| `comment` | ✓ | ✓ | ✓ |
| `set-status` | open/closed, plus the board column with `github_project` | workflow transition via `status_map` | open/closed only |
| `set-field <id> Name=Option…` | single-select fields of the card on `github_project` | – | – |
| `rollup <subtask>` (`--close` \| `--json`) | whether the parent story can close once the subtask is done; `--close` closes it; `--json` gives the decision (`can_close`, `stays_open`, `unknown`, `no_story`) with `story`, `children`, `open`, `unsplit`, `reason` and the printed `line`, where `children`, `open` and `unsplit` are `null` when they were not read completely; an `unknown` line names what could not be read (`parent story`, `children` or `plan`) | ✓ | – |
| `ref` / `pr-text` | `#12` / `Fixes #12` | `PROJ-12` / `PROJ-12` | `#12` / `Fixes #12` |

**Parent links** are always the tracker's own: GitHub sub-issues, Jira `parent`. Skills never write `Part of #N` or `Epic: KEY` into a body. On GitHub, `view` still reads a `Part of #N` line and `children` a task-list ref, marked `[text link]`, so older projects keep working while they move: `aw issue children <root> --text-only` lists what is linked only by text (task-list refs in the root, `Part of #<root>` lines in other issues), `aw issue set-parent <id> <root>` links each one natively, and an empty `--text-only` confirms none remain. Jira rejects parents that break its hierarchy (a sub-task under an epic, mixed team- and company-managed projects); `set-parent` passes the error through with both issue types.

Statuses are canonical (`backlog`, `ready`, `in_progress`, `in_review`, `done`); `status_map` maps them to the tracker's names, defaulting to title case (`In Progress`). With `sync_issue_status` (default on), `aw start-task --issue` moves the issue to `in_progress` and `aw finish` to `done`, on trackers with workflow states. These automatic moves never go backwards: a session start moves only from backlog or ready (or no status), so an issue in review stays there. An explicit `aw issue set-status` is never guarded. Without workflow states, GitHub and GitLab close through the PR keyword.

**Parent rollup:** a story follows its subtasks. A session start on a subtask also moves its parent story to `in_progress`, under the same guard. After the last merge, `aw finish` says whether the story can close: no other child open, and no section of the story's plan without a subtask. It never closes the story itself, because a story can hold work that was never cut into a subtask; `/aw-finalize` asks at the merge gate and passes `aw finish --close-parent` on a yes; `aw issue rollup <subtask> --close` does the same later. Either closes the story with a comment naming its children and refuses while anything keeps it open, or while the children cannot be read completely or the story has several plans: every page of sub-issues (GitHub) or children (Jira) is read, and a failed request means "children unknown", never "no children". A listing that misses the subtask itself is incomplete too, and a parent or sub-issue in another repository is never taken for this repository's issue of the same number. Epics never roll up: a type in `epic_types` (default `Epic`), on Jira any type above story level, on a GitHub board a card without a column. Only native parent links count.

How states, boards and the hook fit together on each tracker: [docs/boards.md](docs/boards.md).

**GitHub Projects board:** a GitHub issue is only open or closed; the board's single-select Status field is its workflow state. `github_project = "owner/number"` (user or organization board; `aw init` asks when `tracker = github`) makes it the backend of `set-status`:

- `set-status` opens or closes the issue and sets the column named by `status_map`, matched case-insensitively, so the default title case finds `In progress`. Field and column ids are resolved at run time; a missing column fails before anything changes.
- `aw issue create` puts the new issue on the board as `backlog`, also on boards without auto-add. If that step fails, it names the new issue and the repair (`aw issue set-status <id> backlog`).
- Other single-select fields (an `Area` for swimlanes, a `Priority`): `aw issue create --field Area=net` sets them on the new card, `aw issue set-field <id> Area=net` on an existing one. `board_fields` maps a label prefix to a field, `board_fields = { "area/" = "Area" }`, so the label `area/net` sets `Area` to `net` on create; `--field` wins over a label. `board_required = ["Area", "Priority"]` makes fields mandatory: a create that sets one of them by neither `--field` nor label creates nothing and lists the missing fields with their options. Fields and options match case-insensitively and are resolved before the create, so an unknown one creates nothing. The status field is set with `--status` only.
- Session start and `aw finish` move the card, under the guard above.
- `aw doctor` checks the token's `project` scope (`gh auth refresh -s project`), the board, the field and the columns, each `board_fields` field and that every label with its prefix has an option, each `board_required` field, and notes board workflows that are off. It never changes board settings; board workflows can only be switched on in the GitHub UI.
- `status_field` names the field when it is not `Status`. Nothing touches a board without `github_project`.

**Hook:** `on_issue_status` runs after every status change (`aw issue set-status`, session start, `aw finish`) with `{issue}`, `{status}` (canonical) and `{status_name}` (from `status_map`), for anything beyond the board: a notification, a board on another system. A failing hook makes `set-status` exit non-zero; at session start and finish it is a warning. In every hook (`on_start`, `on_merge`, `on_issue_status`) `aw` shell-quotes each placeholder value, so `In Progress` arrives as one argument and an empty `{issue}` as an empty one: write placeholders without quotes.

**Jira setup:** `aw init` asks for `jira_base_url` (an `https://` URL; every request carries the credentials) and `jira_project` when `tracker = jira`. Credentials come from the environment only: `JIRA_USER_EMAIL`, `JIRA_API_TOKEN`, and optionally `JIRA_CLOUD_ID` for scoped tokens (routes through `api.atlassian.com`). Instance-specific fields go into `jira_fields`, e.g. `aw init --set jira_fields=acceptance_criteria=customfield_10000`. `aw doctor` checks that the variables are set, never their values, and runs a one-issue search.

## Commands

| Command | Does |
|---|---|
| `aw install [--agent claude] [-v]` | Link skills into `~/.agents/skills` and agent dirs, CLI into `~/.agents/bin/aw` |
| `aw init [-y] [--set K=V] [-v] [--check]` | Create or update `.agents/aw.toml`; reports what changed, `-v` every value and where it came from; `--check` reports what would change and writes nothing (exit 1 when anything would) |
| `aw update [--agent claude]` | Update `aw` (editable: fast-forward the clone; packaged: `uv tool upgrade`), relink the skills, and inside a project run `aw init --check` |
| `aw config [--get KEY] [--sources]` | Print resolved configuration |
| `aw start-task <type> <slug> [--issue N] [--base B]` | Fast-forward the local main (the primary checkout may be on any branch), create branch + worktree from main (`--base`: from `origin/B`, a [stacked session](#stacked-sessions)), direnv (a tracked `.envrc` is kept and left for you to read and `direnv allow`; a missing or failing `direnv` is a warning), `on_start` |
| `aw restack [--dry-run] [--json]` | Stacked session: rebase onto the base's tip, or onto main once the base merged; push, retarget |
| `aw session` | Print the current worktree's session metadata |
| `aw verify` | Run `verify_cmd` in the current checkout (through direnv if enabled) |
| `aw merge [--pr N]` | Merge one part; the branch catches up with main, worktree and issue stay, `on_merge` runs |
| `aw finish [--pr N] [--close-parent]` | Last merge with `merge_method` (skipped when nothing is left); refuses a request that is not at the branch's head, so commits after it are never deleted, and merges exactly that commit (a push in between makes the forge refuse); a request from a fork is never the branch's; remove worktree, update main, delete local + remote branch; `--close-parent` also closes the parent story (see [Parent rollup](#issue-trackers)) |
| `aw abandon [--discard] [--status backlog\|ready]` | End the session without a merge: an issue still in progress goes back (default backlog), worktree and branch (also on origin) are removed; refuses while the branch holds work main lacks or has an open merge request, unless `--discard` drops that work |
| `aw issue view\|children\|list\|search\|create\|update\|set-parent\|comment\|set-status\|set-field\|rollup\|ref\|pr-text` | Tracker operations; see [Issue trackers](#issue-trackers) |
| `aw plan path <ref> [--slug S]` | Plan file of a story or subtask (subtask: through its parent); `--slug` composes the path to write |
| `aw plan state <ref>` | What exists for the issue: plan file, subtasks |
| `aw template <story\|subtask\|plan>` | Print a document template, project override from `templates` |
| `aw memory add\|find\|show\|tags\|supersede\|implemented\|import\|load\|log` | Project memory; see [Project memory](#project-memory) |
| `aw backlog add --title T --body-file F` | Add an item to `backlog_file`, matching the file's item shape |
| `aw backlog list` / `aw backlog pop --title T` | Item titles; remove one (sent or discarded). An emptied inbox is deleted |
| `aw doctor [-v]` | Check installation, skill frontmatter, project config, tools, tracker auth; one line per area plus every problem, `-v` (`make doctor V=1`) lists passing checks too |

## Skill internals

The grilling and domain-modeling skills are copied from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT); each keeps its `LICENSE` and a `metadata.source` link to the exact upstream commit.

`aw finish` is deliberately not in `aw-finalize`'s `allowed-tools`: the merge asks for permission.

User-only skills set `disable-model-invocation: true` (Claude Code) and `policy.allow_implicit_invocation: false` in `agents/openai.yaml` (Codex).

Rule for new skills: deterministic steps (git, paths, numbering, tracker calls) go into `aw` subcommands. Skills keep only the steps that need judgement.

Mechanical steps inside a skill (gathering context, rendering one document from a template) say to delegate to a cheap subagent when the harness has one; `subagent_model` names it. Judgement stays with the main model: grilling, the epic-size call, and reconciling tickets.

Two skills write a story: `aw-to-story` when the conversation redefined it, `aw-plan-story` when grilling moved it. Both carry the same four-step story-write protocol (re-read, diff, `--dry-run`, keep what you did not author). Change one, change the other.

## Development

```bash
make check     # tests, ruff and ty: what CI runs
make format    # let ruff fix and format what it can
```

`make test`, `make lint` and `make types` run the parts. `aw init` detects `make check` as this repo's `verify_cmd`. How to work on `aw` (checks, rules, conventions): [AGENTS.md](AGENTS.md).

Planned work: [BACKLOG.md](BACKLOG.md).

## License

MIT, see [LICENSE](LICENSE). Skills copied from other projects keep their own `LICENSE` file.
