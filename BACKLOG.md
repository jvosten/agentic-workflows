# Backlog

Deferred features and open checks. Each entry has enough context to be picked up in a later session.

**Conventions:** every item is a `###` entry with a priority tag — no tables of items, so entries have room for context. Resolved items are **deleted**, not struck through; the record lives in git history. Tables inside an entry are fine where they carry data.

---

## Items

### [HIGH] Verify v1 in live agent sessions

**Context:** v1 is tested with pytest and the CLI, but not yet from inside an agent. Unconfirmed:

- Claude Code accepts `~` in `allowed-tools: Bash(~/.agents/bin/aw start-task:*)`. If not, every `aw` call prompts for permission; fallback is a permission rule in `~/.claude/settings.json`.
- `disable-model-invocation: true` hides `aw-start-task` from the model while `/aw-start-task` still works.
- The model continues into implementation in the same turn after the handover.
- `aw-finalize` end to end on a real PR, including the permission prompt on `aw finish`.
- `forge = gitlab` / `tracker = gitlab`: `glab` JSON fields and flags are taken from docs, not tested.
- `tracker = jira` against a real instance: `aw doctor`, `aw issue view|children|list|comment|set-status`, status sync on start and finish, and ADF rendering of real descriptions (tested only with recorded responses).
- Native parent links, mutations tested only with recorded responses: GitHub `aw issue create --parent --type` (one `createIssue` call with `parentIssueId`, `issueTypeId`) on an org-owned repo, `aw issue set-parent` link, re-parent and `--none` (`addSubIssue` with `replaceParent`, `removeSubIssue`); Jira `aw issue set-parent` including `--none` (`fields.parent = null`) and a refused hierarchy. Then move one text-linked GitHub project (homelab) until `aw issue children <root> --text-only` is empty.
- GitHub Projects board (`github_project`), tested with recorded responses and read-only against the homelab board: a homelab session moves its card Backlog → In progress → Done through `aw` alone (create, `start-task`, `finish`), then `scripts/project/board-sync.sh` and its hook entry are deleted there. Also an organization-owned board.
- Multi-merge session in the homelab: `/aw-checkpoint` twice (part merge requests with `Refs`, `aw merge` catching the branch up, `on_merge` running the Flux reconcile, issue comments), then `/aw-finalize` with and without a remaining diff. Also a squash-merge repo (the reset path and the deleted remote branch).
- Codex finds `~/.agents/skills/aw-start-task` and honours `agents/openai.yaml` (`allow_implicit_invocation: false`).

**Done when:** one real session per agent has run through both skills, and the findings are in the README.

### [LOW] Project memory follow-ups

**Context:** project memory as one file per entry under `memory_dir`, `aw memory add|find|show|supersede`, the `aw-remember` skill and the `aw-plan-story` / `aw-finalize` / `aw-start-task` hooks are in. What was scoped and not built:

- `aw init` adds a pointer to `memory_dir` in `instructions_file`, so a model that never loads a skill still finds it.
- Option: `autoMemoryEnabled: false` in Claude Code project settings, so Claude keeps one project memory, not two.
- Personal memory stays in each agent's native store; only project memory is committed. Confirm this split survives contact with a real multi-session week.

### [MEDIUM] Experiment: gotchas retrieved by tag, not preloaded

**Context:** `aw-start-task` used to read every gotcha at session start. The first large adopter (homelab) had 203 gotchas, ~23,500 tokens, loaded every session whatever the task; context loaded at session start is also the first to be compacted away. Pure on-demand lookup fails the other way: the agent must suspect there is something to find. The middle path, settled in design sessions on 2026-10-04 and 2026-10-06, is built (see README, Project memory): one file per entry under `.agents/memory/{gotchas,decisions}/`, a tag vocabulary in `tags.toml`, `aw memory add|find|show|tags|supersede|import|load|log`, `gotchas_load = full | tags`, plan-time pulls into the plan's **Known gotchas** and **Decisions in force**, and a gitignored per-session log written by `aw-finalize`.

**Next:** homelab adopts it (its issue #322): import its gotchas table (201 entries after merging two duplicates) and decision log (109 decisions; the phase docs own the D-numbers), set `gotchas_load = "tags"`, point its rules at `aw memory`, freeze the two old docs. Then run ten sessions and read `.agents/gotchas-experiment.log`. Hooks that inject entries before an edit (Claude Code only) are the fallback if plan-time pulls miss too often.

**After the first results:** `tag_map` (path glob → tag) if model-chosen tags miss too often; `gotchas_load = none`; `aw doctor` suggesting `tags` past a size threshold; whether `full` stays the default; in homelab, rewriting the 33 files that link the old docs and deleting them.

**Done when:** the ten sessions are recorded in the README, and the defaults are set from the result.

### [MEDIUM] Spec element above the story

**Context:** Requirements that arrive from outside often exceed one story (Jira epic). `aw-plan-story` currently stops and proposes a sibling split instead.

**Scope:** `aw-to-spec` skill (synthesis of a conversation, no interview, after `mattpocock/skills` `to-spec`), a `spec` template, a committed spec document under `spec_dir` that optionally publishes as an epic, and `aw-to-story` deriving stories from it. Decide the home first: repo document with a tracker pointer, as the planning decision records.

### [LOW] Native blocking links between subtasks

**Context:** `aw-to-subtasks` writes blocking edges as a `## Blocked by` section in the body, because Jira link types are per-instance (`Blocks`, `is blocked by`, renamed schemes). GitHub now has native issue dependencies: GraphQL `addBlockedBy` / `removeBlockedBy`, and `blockedBy` / `blocking` on issues (also `gh issue view --json blockedBy,blocking`).

**Scope:** `aw issue link <id> blocks <other>`: GitHub through `addBlockedBy`, Jira with link-type discovery, text fallback elsewhere; `aw issue view` shows blocked-by and blocking; `aw doctor` reports the available Jira link types.

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

### [LOW] Drop the session number

**Context:** `aw start-task` counts sessions per clone (`.git/aw-last-session`) and uses the number only to name the worktree (`s12-retries`). It is never committed, nothing else reads it, and computing it races when two sessions start at once in the same clone. Session state that matters (the issue) lives in the worktree's session metadata; merged parts come from the forge.

**Scope:** worktrees named `{slug}`, or `{issue}-{slug}` with an issue; drop `{n}`, `--number` and the counter file; `aw start-task` refuses an existing path as today. Update `worktree_name` defaults, docs and skills that print `s<session>`.

### [LOW] Session title hook

**Context:** From agent-issue-tracker. Set the agent session title to `<slug> (#issue)` so parallel sessions are distinguishable. Claude Code hook; other agents vary.

### [LOW] Mark finished plans as history

**Context:** With `plan_scope = repo`, plans stay in `.agents/plans/` after their story is done. A later session that finds one cannot tell a live plan from a finished one, and may read old steps as current requirements. [encephalon](https://github.com/isaachinman/encephalon) keeps its old plans and specs for the record but marks them as history, "not current requirements".

**Scope:**

- `aw-finalize`, when the merged work closes the last subtask of a story, sets the plan's `**Status:**` line to `done` and adds the merge date, in the same PR.
- `aw plan state` reports the status; `aw-plan` routes a `done` plan to "nothing pending" instead of offering to cut subtasks.
- Plans are not moved or deleted; the path that subtasks and comments cite keeps working.

**Done when:** a finished story's plan reads `Status: done` without a manual edit, and `aw-plan` treats it as finished.

### [MEDIUM] Republish the repo with a clean author history

**Context:** Four commits on `main` (`02118ae` to `0089b86`) were made under a work identity instead of `jvo <21955156+jvosten@users.noreply.github.com>`. Only commit metadata carries it; no file in any commit mentions it, and this item does not name it either, so it never lands in a file. A rewrite plus force-push is not enough: GitHub keeps the commits of every pull request for good (PR #6 is built on top of the four), so the old commits stay reachable until the repository is recreated. Do this before the repo goes public.

**Steps:**

1. Find the identity to replace: `git log --all --format='%an <%ae> | %cn <%ce>' | sort | uniq -c`.
2. Start from a clean, current `main` with nothing unmerged worth keeping: `git switch main && git pull --ff-only`.
3. Rewrite every ref, keeping the commit dates:

   ```bash
   export OLD_EMAIL='<work email from step 1>'
   export NEW_NAME='jvo' NEW_EMAIL='21955156+jvosten@users.noreply.github.com'
   git filter-branch -f --env-filter '
     if [ "$GIT_AUTHOR_EMAIL" = "$OLD_EMAIL" ]; then
       export GIT_AUTHOR_NAME="$NEW_NAME" GIT_AUTHOR_EMAIL="$NEW_EMAIL"
     fi
     if [ "$GIT_COMMITTER_EMAIL" = "$OLD_EMAIL" ]; then
       export GIT_COMMITTER_NAME="$NEW_NAME" GIT_COMMITTER_EMAIL="$NEW_EMAIL"
     fi' -- --all
   ```

4. Check: step 1 again shows only the personal identity.
5. Drop the old commits locally:

   ```bash
   git for-each-ref --format='%(refname)' refs/original | xargs -rn1 git update-ref -d
   git reflog expire --expire=now --all && git gc --prune=now
   ```

6. Recreate the GitHub repo. First note what lives only there (issues, pull requests, settings, secrets); everything goes with the delete.

   ```bash
   gh auth refresh -s delete_repo
   gh repo delete jvosten/agentic-workflows --yes
   gh repo create jvosten/agentic-workflows --private --source . --remote origin
   git push -u origin main && git push origin --tags
   ```

7. Re-clone every other checkout. Pushing from an old clone would bring the old commits back.
8. Keep it from happening again: `git config user.email '21955156+jvosten@users.noreply.github.com'` in each clone, or an `includeIf "gitdir:~/projects/"` block in `~/.gitconfig` that sets the personal identity.

**Done when:** a fresh clone shows only the personal identity in `git log --all`, and the GitHub repo has no pull request that references the old commits.

---

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

### [MEDIUM] Stacked branches: start a session on a pending branch

**Context:** The start-task skill of an earlier project (before `aw`) had `--base <branch>`: a session forked from a branch whose merge request was still in review, so dependent work did not wait for the merge. `aw start-task` always branches from `main_branch`, and `aw mr create` and `aw finish` assume `main_branch` as the target. Work that builds on an unmerged change has to wait, or is cut from `main` and conflicts later.

**Scope:**
- `aw start-task <type> <slug> --base <branch>`: fetch the base, create the worktree from `origin/<base>`, and record the base in the session metadata (the old skill used `git config branch.<branch>.stacked-on <base>`; the session file is the `aw` place for it).
- `aw mr create` targets the base branch while it is unmerged, and `main_branch` once it has merged.
- The base updated while the stacked session runs: rebase onto `origin/<base>`, through `aw` or as documented skill steps.
- The base merged first: rebase onto `origin/<main_branch>` (`push --force-with-lease`) and retarget the open merge request to `main_branch`. With squash or rebase merges, the base's commits are in main under other ids, so a plain rebase replays them; decide between `rebase --onto` and the reset `aw merge` already does.
- The stacked branch ready first: merge it into the base, so both land together.
- `aw finish` and `aw merge` know the target: the base, or main once the base has merged. `aw-start-task`, `aw-checkpoint`, `aw-finalize` and `aw-merge-request` name the base wherever they say `main_branch` now.
- Out of scope unless needed: stacks deeper than two.

**Open first:** whether `aw` does the rebase and retarget itself, or detects that the base merged and tells the agent the steps; and how GitHub and GitLab differ when the base branch is deleted after its merge (GitHub retargets the open pull request to main automatically, GitLab does not).

**Done when:** a session started with `--base` opens its merge request against the base, survives the base merging first (rebased, retargeted, merged into `main_branch` by `aw finish`) and the stacked branch merging first, covered by tests for both paths.

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

## Considered and not planned

- **Personas and multi-agent roles** (BMAD), **spec-driven phases** (spec-kit), **label-based handoff queues** (zaks-io): full methods of their own; out of scope for a session-workflow standard.
- **Central registry of project configs**: replaced by committed `.agents/aw.toml`, which travels with the repo.
