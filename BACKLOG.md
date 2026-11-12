# Backlog

Deferred features and open checks. Each entry has enough context to be picked up in a later session.

**Conventions:** every item is a `###` entry with a priority tag — no tables of items, so entries have room for context. Resolved items are **deleted**, not struck through; the record lives in git history. Tables inside an entry are fine where they carry data.

---

## Items

### [HIGH] Verify v1 in live agent sessions

**Context:** v1 is tested with pytest and the CLI. Confirmed from inside Claude Code: `disable-model-invocation: true` hides `aw-start-task` and `aw-finalize` from the model while `/aw-start-task` works; the model goes on into implementation after the handover; the GitHub forge path ran end to end on this repository's pull requests #2–#5 (`aw mr create`, `checks --watch`, `comments`, `view`, a go in chat, `aw finish` merging and cleaning up). Unconfirmed:

- Claude Code accepts `~` in `allowed-tools: Bash(~/.agents/bin/aw start-task:*)`. If not, every `aw` call prompts for permission; fallback is a permission rule in `~/.claude/settings.json`.
- The permission prompt on `aw finish` without an allowlist (not observed: the sessions so far ran with automatic approval).
- A stacked session on GitHub through `aw restack` after its base merged, and `gh pr edit --base`.
- `forge = gitlab` / `tracker = gitlab`: `glab` JSON fields and flags are taken from docs, not tested.
- `tracker = jira` against a real instance: `aw doctor`, `aw issue view|children|list|comment|set-status`, status sync on start and finish, and ADF rendering of real descriptions (tested only with recorded responses).
- Native parent links, mutations tested only with recorded responses: GitHub `aw issue create --parent --type` (one `createIssue` call with `parentIssueId`, `issueTypeId`) on an org-owned repo, `aw issue set-parent` link, re-parent and `--none` (`addSubIssue` with `replaceParent`, `removeSubIssue`); Jira `aw issue set-parent` including `--none` (`fields.parent = null`) and a refused hierarchy. Then move one text-linked GitHub project (the first adopter's) until `aw issue children <root> --text-only` is empty.
- GitHub Projects board (`github_project`), tested with recorded responses and read-only against an adopting project's board: a session there moves its card Backlog → In progress → Done through `aw` alone (create, `start-task`, `finish`), then that project's own board-sync script and its hook entry are deleted. Also an organization-owned board.
- Multi-merge session in an adopting project: `/aw-checkpoint` twice (part merge requests with `Refs`, `aw merge` catching the branch up, `on_merge` running the Flux reconcile, issue comments), then `/aw-finalize` with and without a remaining diff. Also a squash-merge repo (the reset path and the deleted remote branch).
- Codex finds `~/.agents/skills/aw-start-task` and honours `agents/openai.yaml` (`allow_implicit_invocation: false`).

**Done when:** one real session per agent has run through both skills, and the findings are in the README.

### [LOW] Project memory follow-ups

**Context:** project memory as one file per entry under `memory_dir`, `aw memory add|find|show|supersede`, the `aw-remember` skill and the `aw-plan-story` / `aw-finalize` / `aw-start-task` hooks are in. What was scoped and not built:

- `aw init` adds a pointer to `memory_dir` in `instructions_file`, so a model that never loads a skill still finds it.
- Option: `autoMemoryEnabled: false` in Claude Code project settings, so Claude keeps one project memory, not two.
- Personal memory stays in each agent's native store; only project memory is committed. Confirm this split survives contact with a real multi-session week.

### [MEDIUM] Experiment: gotchas retrieved by tag, not preloaded

**Context:** `aw-start-task` used to read every gotcha at session start. The first large adopting project had 203 gotchas, ~23,500 tokens, loaded every session whatever the task; context loaded at session start is also the first to be compacted away. Pure on-demand lookup fails the other way: the agent must suspect there is something to find. The middle path, settled in design sessions on 2026-10-04 and 2026-10-06, is built (see README, Project memory): one file per entry under `.agents/memory/{gotchas,decisions}/`, a tag vocabulary in `tags.toml`, `aw memory add|find|show|tags|supersede|import|load|log`, `gotchas_load = full | tags`, plan-time pulls into the plan's **Known gotchas** and **Decisions in force**, and a gitignored per-session log written by `aw-finalize`.

**Next:** the first adopting project takes it up: import its gotchas table (201 entries after merging two duplicates) and decision log (109 decisions; the phase docs own the D-numbers), set `gotchas_load = "tags"`, point its rules at `aw memory`, freeze the two old docs. Then run ten sessions and read `.agents/gotchas-experiment.log`. Hooks that inject entries before an edit (Claude Code only) are the fallback if plan-time pulls miss too often.

**After the first results:** `tag_map` (path glob → tag) if model-chosen tags miss too often; `gotchas_load = none`; `aw doctor` suggesting `tags` past a size threshold; whether `full` stays the default; in that project, rewriting the 33 files that link the old docs and deleting them.

**Done when:** the ten sessions are recorded in the README, and the defaults are set from the result.

### [MEDIUM] Spec element above the story

**Context:** Requirements that arrive from outside often exceed one story (Jira epic). `aw-plan-story` currently stops and proposes a sibling split instead.

**Scope:** `aw-to-spec` skill (synthesis of a conversation, no interview, after `mattpocock/skills` `to-spec`), a `spec` template, a committed spec document under `spec_dir` that optionally publishes as an epic, and `aw-to-story` deriving stories from it. Decide the home first: repo document with a tracker pointer, as the planning decision records.

### [LOW] Native blocking links between issues

**Context:** `aw-to-subtasks` writes blocking edges as a `## Blocked by` section in the body, because Jira link types are per-instance (`Blocks`, `is blocked by`, renamed schemes). The story template does the same with `- Blocked by: <id>` under `## Links`. GitHub now has native issue dependencies: GraphQL `addBlockedBy` / `removeBlockedBy`, and `blockedBy` / `blocking` on issues (also `gh issue view --json blockedBy,blocking`). Seen in a real run: an epic with seven ordered stories (workflow-orchestrator, AIDA-1925) carried its order only as body text; the user had to add every Jira link by hand.

**Scope:** `aw issue link <id> blocks <other>`: GitHub through `addBlockedBy`, Jira with link-type discovery, text fallback elsewhere. Works for stories and subtasks alike; `aw-to-story` and `aw-to-subtasks` call it for each `Blocked by` entry. `aw issue view` shows blocked-by and blocking; `aw doctor` reports the available Jira link types.

### [MEDIUM] Fetch linked design docs (Confluence)

**Context:** Jira stories often link a Confluence page with the design decision. `aw-plan-story` reads linked docs, but has no way to fetch a Confluence page.

**Scope:** `aw doc fetch <url|page-id> [--out DIR]` → Markdown (Confluence REST v2 `body-format=atlas_doc_format` through the existing ADF converter), same credentials as Jira.

### [LOW] GitLab tracker parity

**Context:** The GitLab adapter lacks `children` and `create` and is untested.

**Scope:** implement both with `glab`; test against a GitLab instance.

### [MEDIUM] Configurable decision records for aw-domain-modeling

**Context:** The copied `aw-domain-modeling` skill writes ADRs to `docs/adr/NNNN-slug.md` and terms to `GLOSSARY.md`. Projects that already keep a decision log elsewhere would get a second, competing record.

**Scope:** keys `decision_dir` (or `decision_log` for a single-file log) and `glossary_file`; the skill reads them from `aw config` before writing. Keep the upstream text otherwise, so updates from mattpocock/skills stay easy to merge.

### [MEDIUM] aw-setup skill

**Context:** From zaks-io `ziw-setup`. Detection in `aw init` is static (files, remote URL, Make targets). An agent can inspect CI config, `package.json` scripts, or docs and propose better values.

**Scope:** skill that inspects the repo, shows proposed values, and writes them through `aw init --yes --set ...`. The CLI stays the only writer.

### [MEDIUM] Instruction file shim

**Context:** From ruler and rulesync. Claude Code prefers `CLAUDE.md`; other agents read `AGENTS.md`. Projects keep a manual `CLAUDE.md` containing `@AGENTS.md`.

**Scope:** `aw init` offers to create `CLAUDE.md` with `@AGENTS.md` when `instructions_file = "AGENTS.md"` and no `CLAUDE.md` exists.

**Alternative to weigh:** [encephalon](https://github.com/isaachinman/encephalon) adds a marked, reversible block to both `AGENTS.md` and `CLAUDE.md` (`init` writes it, `init --remove` takes it out and leaves the rest of the file alone). That also covers projects that already have a `CLAUDE.md` of their own, which the `@AGENTS.md` shim skips.

### [MEDIUM] Finalize refactor

**Context:** `aw-finalize` carries steps it cannot run without a permission prompt, and the end of a session regularly produces leftovers that belong in a backlog, not in a comment nobody reads.

**Scope:**

- Cleanup inside `allowed-tools`: decide which of `aw finish`'s steps may run unprompted (worktree removal, branch deletion) and which keep asking (the merge itself).

### [LOW] Per-skill model override for Claude Code

**Context:** Frontmatter `model:` is Claude-only and static. With symlinked skills all agents share one `SKILL.md`, so it cannot be set per machine. With the deterministic steps in `aw`, the saving is small.

**Scope, if wanted:** a `--copy` install mode for Claude that renders `model:` from the user or local layer.

### [LOW] More install targets

**Context:** From vercel `npx skills` (`--agent` targets). Only `claude` needs links today; agents that read `~/.agents/skills` natively need none.

**Scope:** add agents to `AGENT_DIRS` as they need their own skill directory.

### [MEDIUM] Changelog fragments for shared repos

**Context:** Session ids are no longer committed, but every PR still edits the same `CHANGELOG.md`, so parallel PRs conflict. towncrier and changesets solve this with one file per change (`changelog.d/<branch>.md`), compiled at release.

**Scope:** `changelog_mode = file | fragments` plus `changelog_dir`; `aw-finalize` writes a fragment in fragments mode; `aw changelog build` compiles and removes fragments.

### [LOW] Session title hook

**Context:** From agent-issue-tracker. Set the agent session title to `<slug> (#issue)` so parallel sessions are distinguishable. Claude Code hook; other agents vary.

### [MEDIUM] Where plans live, and when they stop being current

**Context:** `plan_scope` offers two homes, and each has a cost that surfaced in practice:
- `repo` (committed): finished plans stay in `.agents/plans/`; a later session cannot tell a live plan from a finished one and may read old steps as current requirements. [encephalon](https://github.com/isaachinman/encephalon) keeps old plans but marks them as history, "not current requirements".
- `local` (gitignored, primary checkout): the plan exists on one machine in one clone. Another machine never sees it, a re-clone (e.g. a history rewrite and republish) loses it unless copied by hand, and a sandboxed session with a fresh clone has no plan at all.
- `repo`, but planned outside a session: live test in an adopting project, 2026-10-07. `aw-plan-story` for its tracker-migration story ran in the primary checkout on `main_branch` and wrote the plan there, untracked; `/aw-to-subtasks` wrote the subtask ids into that file too. `aw start-task` creates the worktree from `main_branch`, so the plan is not in it and `aw plan path` in the worktree finds nothing; the first session moved the file in by hand. A copy left behind broke `aw finish` when updating `main_branch` ("untracked working tree files would be overwritten by merge"; since 2026-10-07 that update is a warning, not a failure). `aw memory add decision` in `aw-plan-story` has the same problem.

This repo's own hardening plan hit the second set right after it was written (2026-10-10).

**Options to weigh:**
- `repo` plus a lifecycle: `aw-finalize` sets `**Status:** done` and the merge date when the story's last subtask closes; `aw plan state` reports it; `aw-plan` treats `done` as finished; plans are not moved or deleted, so cited paths keep working.
- A dedicated branch for plans (e.g. an orphan `aw-plans` branch): versioned and pushed, so every clone and sandbox can fetch it, but never part of `main`'s tree or its reviews.
- The tracker: the plan as the story's description or an attached document; needs a tracker.
- A plans directory outside the repo, keyed by project: survives re-clones, but is machine-bound and depends on `$HOME`, which conflicts with sandboxed sessions.

**Needed whichever home wins:**
- `aw start-task --issue <id>`: when the primary checkout holds an untracked plan for the issue or its story (and untracked memory entries that reference it), move them into the new worktree, list what moved, and leave nothing behind; the first session commits them.
- `aw finish` and `aw merge`: before merging, name untracked files in the primary checkout that updating `main_branch` would overwrite, before anything changes.
- `aw-plan-story` outside a session: say where the plan landed and which session takes it over.

**Open first:** whether plans need review in pull requests at all, and how a sandboxed session receives its plan.

**Done when:** one home is the default, chosen against these cases (second machine, re-clone, sandbox, finished plan, planned outside a session), and `aw` supports it end to end; a plan written outside a session is in the worktree of the first `aw start-task --issue` for its story and gone from the primary checkout.

### [MEDIUM] Jira status checks in aw doctor

**Context:** On GitHub with `github_project`, `aw doctor` checks that every board column `aw` uses exists. On Jira it checks only credentials, the `/myself` login and `jira_project`. A `status_map` entry that names no status in the project's workflow surfaces only when it is used: `set-status` fails with "no transition to 'Backlog' (available: …)". The likely first hit: a new Jira issue starts in the workflow's initial status (often "To Do"), and `aw-backlog-item` then runs `aw issue set-status <id> backlog`, which looks for a status named "Backlog". Settle the details once Jira is tested live (see [Verify v1 in live agent sessions](#high-verify-v1-in-live-agent-sessions)).

**Scope:**
- `aw doctor` reads the project's statuses (`GET /rest/api/3/project/<key>/statuses`, per issue type) and checks the statuses `aw` uses (`backlog`, `in_progress`, `done`, plus every key in `status_map`), matched case-insensitively like the transitions.
- A missing one fails and lists the statuses that exist, with the `status_map` key to set (e.g. `status_map.backlog = "To Do"`).
- Decide from the live test: whether `backlog` should default to the workflow's initial status on Jira, and whether a status that exists but has no direct transition from the usual starting points deserves a warning.

**Done when:** `aw doctor` on a Jira project with a wrong `status_map` names the missing status and the fix, covered by recorded-response tests.

---

### [LOW] Multi-merge sessions across environments and repos

**Context:** Multi-merge sessions (`aw merge`, `/aw-checkpoint`) cover one shape: one environment and one repo, where the same branch merges into `main_branch` several times with new commits in between. Two other shapes need different machinery, and no adopting project has them yet:

- **Promotion across environments:** the same change merged to `dev`, then promoted to `staging` and `prod`. Either each merge targets another base branch (`env/prod`, often merged forward with the same commits), or each promotion is a new commit in another path (the prod overlay's image tag).
- **Changes split across repos:** for example the app repo builds the image, then the GitOps repo bumps it. That is two worktrees in two repos with an order between them; `aw` sessions are per repo.

**Open first:** which shape a real project has, and whether its promotions reuse the commits or create new ones. Design after that.

---

### [LOW] Stories left open in aw doctor

**Context:** The parent rollup (README, Parent rollup) moves a story to in progress with its first subtask and offers to close it after the last, at `/aw-finalize`'s merge gate. A story whose last subtask closed outside `aw` (a hand merge, a closing keyword with no `aw finish`), or where the user said no at the gate, stays open, and nobody is reminded.

**Scope:**
- `aw doctor` lists open stories (not epics: `epic_types`, Jira hierarchy level, GitHub card without a column) whose children are all closed, each with `aw issue rollup <child> --close`.
- GitHub: one GraphQL search over open issues with `subIssuesSummary { total completed }` and `issueType`, no call per issue. Jira: JQL for open issues of story level that have children; the closed check needs the children's status categories, so cap the count or skip it on large projects.
- An info line, not a failure: closing stays a decision.

**Done when:** `aw doctor` names a story whose children are all closed, on GitHub and Jira, covered by recorded-response tests.

---

### [LOW] Stacked sessions: cases not covered

**Context:** `aw start-task --base` and `aw restack` cover one level of stacking with a forge, for `merge`, `squash` and `rebase` (README "Stacked sessions"). Cut on purpose:

- **Stacked branch ready before its base:** merge the stacked request into the base, so both land together. `aw merge` / `aw finish` refuse in a stacked session today.
- **Part merges in the base session:** with `squash` or `rebase`, `aw merge` resets the base branch to `main` and deletes `origin/<base>`. The stacked session only gets a warning; whether `aw restack` should then treat the base as merged, or keep following the recreated branch, is open.
- **`forge = none`:** a squash merged by hand is invisible to git; `--base` refuses.
- **Stacks deeper than two;** `glab stack` and GitHub equivalents.
- **Live check:** `gh pr edit --base` and `glab mr update --target-branch` are taken from docs; add to "[HIGH] Verify v1 in live agent sessions".

**Done when:** each case is supported with tests, or moved to "Considered and not planned" with the reason.

---

### [MEDIUM] Project additions to skills

**Context:** Skills are installed once per machine (`~/.agents/skills`, linked into `~/.claude/skills`) and shared by every project. A project that wants a skill to behave a little differently can only set config keys, write a hook, or fork the whole skill. A forked copy drifts from `aw`: skills are tightly bound to the CLI (commands, flags, `allowed-tools`), so a copy breaks silently when `aw` changes, and every fix has to be carried into every repo. An earlier project's `start-task` shows the cost: a per-project copy with hardcoded paths and dev commands. Discussed 2026-10-07 together with the `on_start` hook.

**Where each kind of change belongs:**
- Mechanical steps that must always run (worktree setup: `direnv allow`, `uv sync`, `tofu init`) → hooks (`on_start`, `on_merge`, `on_issue_status`). They are deterministic and run without an agent.
- Rules for the whole project → `instructions_file` (`AGENTS.md`).
- Steps that need judgment at one point of one skill (for example "for changes under `infra/`, run `tofu plan` and put the summary in the merge request" in `aw-finalize`, or "read `docs/scheduler.md` before touching the scheduler" in `aw-start-task`) → project additions, this item.

**Scope:**
- An optional file per skill in the repo, e.g. `.agents/skills/<skill-name>.md` (decide the path; it must not look like a skill directory that agents load on their own).
- Each skill reads its addition at a defined point and follows it as part of that step. The addition can add steps and tighten rules; it cannot remove the skill's guards (merge gate, no tracker writes without a go).
- One place in each skill that loads it, worded the same everywhere, e.g. after loading settings: `aw skill addition <name>` prints the file, or nothing.
- `aw doctor` lists the additions a project has, and flags one for a skill that does not exist.
- README: when to use a hook, the instructions file, or an addition.

**Open first:** whether additions are per step (a heading per skill step, inserted there) or per skill (read once at the start), and whether a full override (a project copy that shadows the global skill) is ever needed, with `aw doctor` reporting drift; that is related to vendoring the skills into a project (copies pinned to an `aw` version).

**Done when:** a project adds a step to `aw-finalize` and a rule to `aw-start-task` through addition files, both are followed in a real session, and the global skills stay unchanged.

---

### [LOW] Backlog skill shows story descriptions when picking a parent

**Context:** `aw-backlog-item` step 5 picks the parent for a new tracker item from `aw issue children` output. That output has type and title only, so the model matches an item to a story by title alone. A story with a vague title can attract the wrong item.

**Problem:** a wrong parent hides the item from the team that owns the story, and moving it later costs a `set-parent` round trip.

**Scope:**

- In step 5, after the numbered list, run `aw issue view <id>` for the two or three candidates that best match the item.
- Show each candidate's description (trimmed) with the list, and base the recommendation on it.
- Skip the views when the tree has fewer than three candidates or the user names the parent.
- Update the skill text only; `aw issue view` already returns the description.

**Acceptance criteria:**

- The skill lists the exact `aw issue view` calls in `allowed-tools` (already present) and in step 5.
- For an epic with many stories, the shown candidates include description text.
- No `aw` code change is needed.

**Effort:** small, one skill edit.

---

### [LOW] Configurable story size limit in aw-plan-story

**Context:** Feedback from a real run. `skills/aw-plan-story/SKILL.md` (step 3) calls a story epic-sized when it has "more than about five session-sized slices". The rule fired on a plan with six sections whose last ones were small (docs, contract). A count treats a small slice like a large one.

**Scope:**
- Option A: add `max_story_sections` to `aw.toml` (`schema.toml`, default 5) and have the skill read it from `aw config`.
- Option B: weight sections by size (small, medium, large) and compare the total to a limit.
- Decide between A and B; A is the smaller change. Update the skill text and README to match.
- Keep the other two epic-sized rules (more than one deployable outcome, two personas) unchanged.

**Done when:** a project can raise the limit in `aw.toml`, and `aw-plan-story` uses it, or small sections no longer trigger the split on their own.

**Effort:** small for A; medium for B (a size field in the plan template).

---

### [LOW] Decisions in force filtered to the story's subject

**Context:** `aw-plan-story` step 4 copies "the decision index from step 2, as printed" into **Decisions in force**. Live test in an adopting project, 2026-10-07: the index has 111 decisions; for its tracker-migration story two applied. Pasting all 111 into every plan costs the context the gotcha design saved, and the agent filtered by text instead, which the skill does not say. Gotchas are already filtered by tags; that project's decisions carry no tags (`tags: []`), so the same filter finds nothing.

**Scope:**
- Decisions take tags from the same vocabulary (`aw memory add decision --tags`); `aw memory import` and a retag command let a project tag existing ones.
- `aw-plan-story` lists decisions with `aw memory find --kind decision --tags <story tags>` plus `--text` terms from the story, and writes the filter on the line above the list, as for gotchas.
- Below a size threshold (about 20 active decisions) the full index stays.

**Acceptance criteria:**
- A plan in a project above the threshold lists only decisions that match its tags or terms, and names the filter.
- A project below the threshold still gets the full index.

**Effort:** small to medium. Mostly skill text; retagging existing decisions is the project's work.

---

### [MEDIUM] Text-link children only from task lists that hold child refs

**Context:** live test in an adopting project, 2026-10-07: `aw issue children <story>` and `aw plan state <story>` reported one of its phase epics as a `[text link]` child of the story. The story's acceptance criterion "- [ ] Phase epics #A–#D are closed; …" is a checkbox line with an issue reference, and the GitHub adapter's `TASK_REF` pattern reads every such line as a task-list child. Acceptance criteria and checklists that name other issues are common, so `--text-only` migrations and `aw-to-subtasks` mappings get false children; `aw-to-subtasks` had to explain it away by hand.

**Scope:**
- Count a checkbox line as a child only when the reference is the line's subject: the line starts with the reference (`- [ ] #12`, `- [ ] #12 title`), or it sits under a heading such as `## Items`, `## Tasks`, `## Subtasks`.
- `aw issue children` keeps showing native children unchanged; ambiguous text matches are dropped, not guessed.
- Tests: an acceptance criterion naming issues mid-sentence yields no child; an `## Items` list and a bare `- [ ] #12` line still do.

**Acceptance criteria:**
- `aw issue children` on a story whose acceptance criteria mention other issues lists only real children.
- Existing text-linked trees (`## Items` lists) are still found by `--text-only`.

**Effort:** small. One pattern and its tests in the GitHub adapter.

---

### [MEDIUM] Repo-scoped forge token in aw init

**Context:** `gh auth login` and `glab auth login` default to account-wide tokens: GitHub's OAuth token carries `repo` (every repository the account reaches), GitLab's personal access token with `api` covers every project. `aw` needs far less for one repository: push, merge requests, checks, and issues when the forge is also the tracker. Found while finalizing 0.2.0 in this repo.

**Problem:** Setting up a project with `aw init` never asks how the forge CLI is authenticated, so most users run `aw` with a token that can write everywhere. The safe setup exists on both forges but takes several manual steps in a web UI that nobody remembers.

**Scope:**

- `aw init` (and `aw doctor`) reports the current `gh` / `glab` login and whether it is limited to this repository, without printing any token.
- An optional step in `aw init` that guides the user to a repository-scoped token and lists the permissions `aw` needs, derived from `forge`, `tracker` and `github_project`:
  - GitHub: fine-grained personal access token, "Only select repositories" → this repo; Contents RW, Pull requests RW, Commit statuses R, Actions R, Issues RW (tracker `github`), Projects (with `github_project`).
  - GitLab: project access token (or a personal token with the smallest scopes the project allows); `api` is the narrowest scope `glab mr` works with, so project-level is the limiting factor.
- It opens or prints the token creation URL with the repository preselected where the forge supports it; the user creates the token and logs in themselves (`gh auth login` / `glab auth login`, paste). `aw` never reads, stores or prints the token.
- Per-repo login without touching the global one: document `GH_TOKEN` / `GITLAB_TOKEN` from a secret manager in the repo's `.envrc` as the alternative to replacing the CLI's global login.
- Check which `aw` operations fail under a fine-grained token (e.g. check runs in `gh pr checks`), and list them.

**Acceptance criteria:**

- `aw doctor` says whether the forge login is repository-scoped, account-wide, or unknown, and never prints a token.
- `aw init` offers the token step with the permission list for the configured forge and tracker, and skips it on request.
- Every `aw mr` and `aw issue` operation used by the skills works with the suggested token, or the docs name the exception.

**Effort:** medium — no token handling in `aw`, but per-forge permission lists and a live check against both forges.

---

### [LOW] forge = none: a final merge by hand runs on_merge

**Context:** `aw finish` decides "nothing left to merge" when `main` holds every commit of the branch. With a forge, a merge outside `aw` is recognised by the merged request's head and handled as the last merge (`on_merge` runs with `final = true`). With `forge = none` there is no request to look at: a branch merged by hand into `main` and a branch whose every change already went in through `aw merge` look the same, and both take the nothing-left path. Found while fixing the nothing-left rule (hardening plan, S3, 2026-10-13); the behaviour predates it.

**Problem:** after a final merge by hand with `forge = none`, `on_merge` does not run, so a deploy or reconcile hook that should follow the last merge is skipped silently.

**Scope:**
- Tell the two cases apart with what git knows: the session's last `aw merge` records the main commit it left the branch at (session metadata); a branch head that `main` gained after that point was merged by hand.
- When it was merged by hand, run `on_merge` with `final = true` and log "merged by hand".
- Test both paths with `forge = none`.

**Done when:** `aw finish` after a final merge by hand with `forge = none` runs `on_merge` once with `final = true`, and after a last part merged through `aw merge` it still skips it.

---

### [LOW] Jira custom fields on create

**Context:** `aw issue create --field Name=Option` and `aw issue set-field` set single-select fields on a `github_project` board. On Jira the same flag is refused before the create ("Jira custom fields are not supported yet"). Jira select fields take `{"value": …}` and their allowed values come from createmeta, so the option check before the create needs a lookup of its own.

**Scope:**
- `--field` on Jira: resolve the field id by name (createmeta for the project and issue type), check the option against its allowed values before the create, send it in the create.
- `aw issue set-field` on Jira: the same field through `PUT /issue/{key}`.
- `board_fields` applies to Jira the same way (label prefix → field).
- `aw doctor` checks the mapped fields on Jira too.

**Done when:** a Jira issue filed with `--field Area=net` has the field set, and an unknown option creates nothing.

---

### [LOW] Show a comment-only review verdict in aw mr view

**Context:** two pull requests in an adopting project (2026-10-16). The claude-review GitHub workflow posts its review as an issue comment that ends with a `### Decision` line (`APPROVE`, ...). It cannot submit a formal review. `aw mr view` builds its `review` line from `reviewDecision` (`src/aw/forge.py`, printed at `src/aw/cli.py:342`), so it shows `review   none` while an APPROVE comment exists. The user read `none` as "the review did not run, or aw did not wait long enough".

**Problem:** the merge gate shows `aw mr view` as the review state. A comment-only review is invisible there, and nothing says which commit it covered. In that project the review workflow runs only on `opened, reopened`, so later pushes (a conflict resolution, a fix the review asked for) are never re-reviewed, and the gate does not show that either.

**Scope:**
- Detect a comment-only review verdict from a configured bot author (e.g. `claude[bot]`) and a verdict pattern; keep both configurable, not hard-coded.
- Show it on the `review` line next to the formal state, with the commit it covered or its time against the last push, e.g. `review   none (formal) · claude: APPROVE at 0a0fd77, 2 commits behind`.
- Leave `reviewDecision` as the formal state; do not count the comment as an approval.

**Acceptance criteria:**
- With an APPROVE comment from the configured author and no formal review, `aw mr view` shows the verdict and says whether commits came after it.
- Without such a comment, or without configuration, the output is unchanged.
- GitLab: same behaviour or a documented "not supported".

**Effort:** small — one comment fetch, one regex and a line format in `mr view`; tests with recorded responses.

---

### [MEDIUM] Tagged releases with built wheels

**Context:** S11 of the hardening plan (2026-10-18) made `aw` installable without a clone: `uv tool install git+https://github.com/jvosten/agentic-workflows`, then `aw install`, and `aw update` runs `uv tool upgrade`. CI installs that package non-editable and checks the skills link into the packaged `aw/_skills`. Asked at the end: is this now comparable to a binary install?

**Problem:** Not yet. The package bundles CLI and skills at one version, but:
- each install builds the wheel from git source, so it needs git, network access to the repository (credentials while it is private) and a build backend;
- `uv tool upgrade` follows the default branch's HEAD: there are no releases to pin or to move between, only commits;
- there is no artifact to checksum or to keep for an offline or sandboxed install;
- installing takes two steps: `aw install` must run after `uv tool install`, or no agent sees the skills, and a wheel cannot run that step on install.

**Scope:**
- A release workflow on version tags (`v0.1.14`): build the wheel and sdist with `uv build` and attach them to a GitHub release, with checksums. PyPI once the repository is public.
- The release process: the version bump commit gets its tag; a check that the tag, `pyproject.toml` and `aw --version` agree.
- Install from a release: `uv tool install <wheel URL>` or `agentic-workflows==X`, documented. `aw update` moves to the newest release for such an install, and says which release it left and which it installed.
- Open: whether `aw` links its skills on first run (any command, when `~/.agents/bin/aw` or the skill links are missing or point at another version), so the install becomes one step. It writes into `$HOME`, so it must stay off in a sandbox (`AW_SANDBOXED`).

**Acceptance criteria:**
- A pushed version tag produces a GitHub release with the wheel, the sdist and their checksums, and fails when the tag and the package version differ.
- A machine without a clone or git credentials installs a given release from its wheel, and `aw doctor` passes after `aw install`.
- `aw update` on a release install installs the newest release and names both versions.

**Effort:** medium; the workflow is small, `aw update` needs a third install kind, and first-run linking needs a design decision.

---

### [MEDIUM] aw mr create: warn when a description closes another pull request

**Context:** a pull request in another repository (2026-10-18). Its "Merge danger" section said "Renovate closes #A and #B …", and #A, an open Renovate pull request, was closed when that request merged. Nobody noticed until the dependency update was missing. `aw mr create` and `aw mr update` read what a request will close from `closingIssuesReferences` (`src/aw/forge.py`, `closes()`), which lists issues only, so the existing `also closes #N` warning cannot see a pull request.

**Open first:** confirm the mechanism in a scratch repository. GitHub documents closing keywords for issues. Whether a keyword in a merged pull request's description also closes another pull request, or whether Renovate closed its own pull request (for example because the merge changed the dependency it was updating), decides whether this item is needed at all.

**Problem:** if GitHub closes pull requests this way, prose in a description closes unrelated pull requests silently, and the check meant to catch accidental closing keywords covers only issues.

**Scope (GitHub only):**
- After create and update, scan the description with the existing `CLOSING` pattern (`src/aw/cli.py`; it already accepts `Closes: #N`), and resolve each reference (`#N`, `owner/repo#N`, a URL) with the forge: issue or pull request.
- Warn for each pull request, naming the phrase, like the existing `also closes #N` warning.
- Run the scan whatever the tracker. `_check_closes` (`src/aw/cli.py`) returns early without a session issue or when issues live elsewhere (Jira); this risk depends on the forge alone.
- Keep `closingIssuesReferences` as the source for the issue the request must close.
- GitLab needs nothing: `#N` always refers to an issue there, merge requests are `!N` with their own numbering, and closing patterns close issues only.

**Acceptance criteria:**
- A description containing "closes #<open PR>" or "Closes: #<open PR>" makes `aw mr create` warn, naming that pull request, also in a project whose tracker is Jira.
- Descriptions without such phrases produce no new output.
- Tests with recorded GitHub responses.

**Effort:** small once the mechanism is confirmed: one scan reusing `CLOSING`, one lookup per referenced number.

---

### [LOW] Claude Code worktrees go through aw start-task, with .worktreeinclude

**Context:** a review of worktree tools (2026-10-17) found two Claude Code features that touch what `aw start-task` does. Claude Code creates worktrees of its own (`claude --worktree`, subagents with worktree isolation, the desktop app), and its `WorktreeCreate` / `WorktreeRemove` hooks can replace that creation and removal. `.worktreeinclude` lists local files to copy into a new worktree; Claude Code documents it as "`.gitignore` syntax. Only files that match a pattern and are also gitignored are copied", and not applied when a `WorktreeCreate` hook replaces creation. Codex documents the same file for its managed desktop worktrees, and ccmanager implements it.

**Problem:** a worktree Claude Code creates bypasses `aw`: no session metadata, no branch naming, no `on_start`, and `aw finish` / `aw abandon` do not know it. A session worktree from `aw start-task` in turn lacks gitignored local files (`.env`, local config) unless `on_start` copies them by hand. And what `.worktreeinclude` usually lists is what a sandboxed worker must not receive.

**Scope:**
- A `WorktreeCreate` hook that calls `aw start-task`, so Claude Code's worktrees are sessions. Check the hook's input and output contract at the time; decide how the hook's worktree name maps to the session's slug and type.
- `WorktreeRemove`: decide whether it maps to `aw abandon`, or only reports. It must never delete work that is unpushed or not merged.
- `aw start-task` copies the files that match `.worktreeinclude` and are gitignored, from the primary checkout into the new worktree. Because Claude Code skips the file when the hook replaces creation, `aw` doing the copy keeps it meaningful.
- No copy when the session is sandboxed or the primary checkout is not reachable; `start-task` says so.
- README: the hook configuration and `.worktreeinclude`.

**Acceptance criteria:**
- With the hook configured, a worktree created by Claude Code is a session that `aw finish` and `aw abandon` recognise.
- Only files that match `.worktreeinclude` and are gitignored are copied; tracked files never are; no `.worktreeinclude` copies nothing.
- In a sandboxed session, or with no reachable primary checkout, nothing is copied and the output says why.
- The remove hook refuses on unpushed or unmerged work.

**Effort:** medium — the hook contract, the copy rules and the sandbox guard, tested with faked hook input.

---

### [MEDIUM] Finish cleanup after the forge deletes the merged remote branch

**Context:** A live session reported that `aw finish` refused after the merge because the forge had already deleted the remote source branch. The session skipped `aw finish` and needed manual cleanup. This report has not yet been reproduced here.

**Problem:** Remote branch deletion after a merge can block local branch and worktree cleanup and leave final tracker updates unfinished, even when the request contains all session work.

**Scope:**
- Reproduce the missing-remote-branch case with a local bare origin and fake forge responses, across merge, squash and rebase merges.
- Confirm the merged request covers the local session head without requiring the remote source branch to exist.
- Treat a confirmed missing remote branch as already removed; distinguish it from failed or uncertain remote queries.
- Preserve the existing checks for unmerged or unpushed work before local cleanup, tracker updates and hooks.

**Acceptance criteria:**
- `aw finish` completes its normal cleanup and final updates when the merged request covers the session head and the remote source branch is already gone.
- An absent remote branch alone never authorizes cleanup: unknown merge state, local commits not covered by the request, and failed remote queries still refuse without destructive effects.
- Tests cover forge-driven source branch deletion for merge, squash and rebase merges without network access.

**Effort:** medium; merge verification and cleanup must distinguish expected branch deletion from uncertain or incomplete work.

### [MEDIUM] Make `aw-finalize` merge-request waiting reliable

**Context:** In a docs session (AIDA-1937, MR !85) the wait after a push was slow and misleading. After a force-push `aw mr checks --watch` printed `1 passed` and `aw mr view` printed `mergeable: conflict` at once; both described the old state. GitLab computes the pipeline and the mergeability asynchronously. The conflict (a rebase onto `main`, in `CHANGELOG.md`) only appeared at step 9, after the merge request existed and CI had run. Piping the watch through `tail` hid all progress, and a `sed -i` call that works on Linux failed on macOS and cut off its `&&` chain without a visible error.

**Scope:**
- `aw mr checks --watch`: wait for the pipeline whose SHA equals local `HEAD`. No pipeline for that SHA yet counts as pending (exit 2). Do not report the previous pipeline.
- `aw mr wait` (new): block until the pipeline for `HEAD` finished and mergeability left `checking`/`unchecked`/`approvals syncing`. Print one summary line (SHA, checks, mergeable, unresolved threads); exit 0 ready, 1 failed or conflict, 2 timeout. Add `--timeout` and one output line per state change, so it works as a background process.
- Conflict preflight before the merge request opens (step 6 or 7 of `aw-finalize`): `git fetch` and `git merge-tree --write-tree origin/<main_branch> HEAD`. Name the conflicting files before CI runs.
- Changelog: `aw changelog add` or fragment files, so a top-of-file insert in a shared `CHANGELOG.md` no longer conflicts in every merge request. Also settle how the entry names the merge request number without a second commit and a second CI run.
- `aw-finalize` skill text: run `--watch` without a pipe; edit files with `aw` or a portable tool, never `sed -i` (BSD `sed` needs `-i ''`); do not chain a commit and push after an edit whose success is not checked.

**Done when:** a force-push followed by `aw mr wait` returns only after the new pipeline and mergeability are known, and a branch that conflicts with `main` fails the preflight before `aw mr create`.

---

### [MEDIUM] Keep verification usable when direnv activation is forbidden

**Context:** A reported agent session's default `aw verify` invocation exceeded the caller's 120-second limit although the configured `make check` passed directly. Its generated worktree `.envrc` delegated to a primary checkout whose environment template included vault-backed loading. Password-manager commands were forbidden. In that session, `AW_DIRENV=false aw verify` ran the original checks successfully in 12 seconds. The specific environment hook responsible for the timeout was not established.

**Additional evidence (2026-11-04):** A later reported finalization attempt identified a password-manager command in the repository's direnv startup path before execution. Direct checks worked in the already loaded environment. With `verify_cmd = "make check"`, the per-command override resolved `direnv` to `false` and the configured check passed. No password-manager command was run. This report does not establish the cause of the earlier timeout.

**Problem:** `aw.finish.verify` wraps `verify_cmd` in `direnv exec <checkout> sh -c ...` when `direnv` is enabled. A worktree can delegate environment setup to the primary checkout, so its visible `.envrc` does not bound the startup path. Environment activation therefore precedes verification and may run interactive or forbidden credential-loading hooks. A timeout does not by itself prove that the checks ran or identify which activation hook blocked. The wrapper behavior is confirmed in the source; the reported timeout has not been reproduced here.

**Scope:**
- Document the existing invocation-scoped workaround, `AW_DIRENV=false aw verify`, when the current environment already supplies the configured check's requirements. It leaves configuration files unchanged and skips environment bootstrapping, not the configured checks or merge gate.
- State that the override supplies no missing variables. If required values are unavailable, stop for operator setup; never retrieve credentials or run a password manager.
- Explain worktree-to-primary-checkout delegation so agents do not treat the visible worktree `.envrc` as the entire startup path. Cover delegated activation with fake processes, never live credential hooks.
- Show how to confirm the effective settings without activating the directory: `AW_DIRENV=false aw config --get direnv` and `AW_DIRENV=false aw config --get verify_cmd`. The first must resolve to `false`; the second must retain the original verification command.
- Update verification guidance in the README and calling skills to distinguish environment activation from the verification command. Do not recommend running a forbidden environment hook as a diagnostic step.
- Cover enabled and disabled direnv paths with fake processes; preserve the configured command and its exit status. Keep normal direnv activation available when the project requires it rather than silently disabling it by default.

**Acceptance criteria:**
- A restricted agent can find and use the documented environment override without running direnv, vault or password-manager commands, or displaying secret values.
- Tests prove that `AW_DIRENV=false` bypasses a simulated forbidden activation step, executes the unchanged verification command and returns its exit status.
- Project configuration and the merge gate remain unchanged; the enabled-direnv path remains covered.
- Guidance requires operator setup when the current environment lacks values needed by the configured check; it never recommends credential retrieval or password-manager execution.
- Documentation distinguishes the earlier unidentified timeout from the later pre-execution password-manager finding and does not claim that the later report establishes the earlier timeout's cause.

**Effort:** small; the override already exists, so the work is documentation and regression coverage, not a new CLI option.

---

### [HIGH] Audit destructive commands and gate force pushes

**Context:** A stacked-session report exposed an unrequested `git push --force-with-lease` during `aw restack --dry-run`. The current fix blocks dry-run pushes, but normal `aw restack` still force-pushes automatically after a rebase or manual conflict recovery. A lease checks the expected remote state; it does not establish user approval to rewrite published history.

**Problem:** Potentially destructive operations can sit inside otherwise routine workflow commands. A request to restack, verify or prepare a merge request must not implicitly authorize a force push, deletion or other destructive action. Skill instructions and agent tool allowlists are not sufficient runtime gates.

**Scope:**
- Audit mutating paths across the CLI, forge/tracker adapters, hooks and calling skills. Include force pushes, history rewrites and resets, local/remote branch deletion, worktree removal, merges, issue closure and deployment hooks.
- Record each operation's entry points, targets, possible loss, current approval checks and recovery options. Classify which operations need explicit approval.
- Gate force pushes, including `--force-with-lease`, in the CLI before the destructive action. Show the remote, branch, expected old/new tips and consequences; require explicit approval scoped to that action. Refuse when approval is absent, uncertain or stale, including in non-interactive use.
- Keep destructive-action authorization separate from merge approval: `merge_gate = auto`, a previous approval, a skill allowlist or a successful lease check must not authorize a force push.
- Update workflow guidance and add regression tests for every gated path, including restack recovery after `git rebase --continue`.

**Acceptance criteria:**
- A repository-wide inventory identifies destructive operations, their callers and their enforced gates; any remaining gaps have explicit follow-up work.
- Direct and indirect force-push paths refuse without explicit action-scoped approval. The refusal occurs before any destructive mutation, and the message identifies what needs approval.
- Tests cover denied, approved and stale approvals, plus dry runs and manual conflict recovery. Denied and dry-run paths do not push, delete, rewrite branch history or write session metadata.
- Documentation distinguishes concurrency protection (`--force-with-lease`) from authorization and explains the affected operations and recovery steps.

**Effort:** medium to large; the audit spans several modules and workflows, and approval enforcement needs tests at each destructive boundary.

---

### [MEDIUM] Offload finalize CI watching to a configurable low-cost subagent

**Context:** During a real `aw-finalize` run, the parent session spent minutes waiting on `aw mr checks --watch`. The user had to ask whether a lower-cost subagent could own that read-only watch while the main session remained available.

**Problem:** Routine CI-status follow-up occupies the main session and makes finalization look stalled. The goal is to release the parent and reduce the cost of status interpretation, not to make CI execute faster. CLI waiting itself does not require continuous model calls.

**Scope:**
- Let `aw-finalize` hand CI/review-status watching to a configurable low-cost subagent when the agent harness supports it; do not hardcode a provider or model.
- Give the watcher a bounded read-only brief: repository/session, merge request, expected HEAD, permitted status queries, completion conditions and when to escalate.
- Keep deterministic waiting in `aw`; avoid model-level polling loops. Reuse the CI-wait reliability work rather than creating a second pipeline-state implementation.
- Notify the parent on completion, failure, timeout or required attention. The parent owns fixes, review replies, pushes, merge approval and cleanup.
- Define explicit behavior when delegation is unavailable or fails. Never infer green status or silently bypass a gate.

**Acceptance criteria:**
- With delegation enabled and supported, finalization starts the configured low-cost watcher and returns control promptly instead of blocking the parent on the watch.
- The watcher cannot edit files, rerun local verification, change the merge request, push, merge or clean up.
- Reported status belongs to the expected HEAD and includes pending/failed downstream pipelines; a short parent-job success is not sufficient.
- Completion and failure notifications retain enough context for the parent to resume the same finalization safely, without duplicating a watcher or a merge attempt.
- Merge approval, unresolved-review and stacked-base gates remain unchanged.
- Output contains status and relevant links, not credentials or raw job-log payloads.
- Tests cover supported delegation, unavailable/failed delegation, stale or pending CI, timeout and successful handoff, without real network access.

**Effort:** medium — skill/configuration orchestration plus completion and failure handoff tests; the existing CLI remains the owner of CI-state logic.

**Related:** the existing CI-wait reliability and per-skill model-selection items cover adjacent concerns; this item specifically releases the parent session through a read-only delegated watch.

## Considered and not planned

- **Personas and multi-agent roles** (BMAD), **spec-driven phases** (spec-kit), **label-based handoff queues** (zaks-io): full methods of their own; out of scope for a session-workflow standard.
- **Central registry of project configs**: replaced by committed `.agents/aw.toml`, which travels with the repo.
