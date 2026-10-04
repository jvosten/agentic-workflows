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
- Codex finds `~/.agents/skills/aw-start-task` and honours `agents/openai.yaml` (`allow_implicit_invocation: false`).

**Done when:** one real session per agent has run through both skills, and the findings are in the README.

### [LOW] Project memory follow-ups

**Context:** `aw memory add|supersede`, the two files under `memory_dir`, the `aw-remember` skill and the `aw-plan-story` / `aw-finalize` / `aw-start-task` hooks are in. What was scoped and not built:

- `aw init` adds a pointer to `memory_dir` in `instructions_file`, so a model that never loads a skill still finds it.
- `.gitattributes` `merge=union` for both files, so two sessions appending in parallel merge without a conflict.
- Option: `autoMemoryEnabled: false` in Claude Code project settings, so Claude keeps one project memory, not two.
- Personal memory stays in each agent's native store; only project memory is committed. Confirm this split survives contact with a real multi-session week.

### [MEDIUM] Experiment: gotchas retrieved by tag, not preloaded

**Context:** `aw-start-task` reads `<memory_dir>/decisions.md` and `gotchas.md` in full at session start; `aw doctor` warns past 200 lines. The first large adopter (homelab) has 201 gotchas, ~23,500 tokens, in a table grouped by tool, with numbers cited 144 times from code, CI and docs. Loading all of it costs that much every session, whatever the task. A typical session needs a handful of entries; the rest dilute the relevant ones. Context loaded at session start is the first to be compacted away, so a gotcha is often gone by the time the agent edits the file it is about. And the 200-line warning pushes toward deleting knowledge to fit a budget. Pure on-demand lookup has the opposite failure: the agent must suspect there is something to find, and a missed gotcha shows only as a repeated mistake. A design session on 2026-10-04 settled on a middle path, to be tried as an experiment.

**Settled in that discussion:**
- A gotcha is external tool behavior: symptom, cause, fix. A workflow pitfall that bites regardless of tool becomes a rule in `instructions_file`; `aw-finalize` proposes the rule text, the user decides.
- One file per gotcha: `<gotchas_dir>/<slug>.md`, and the slug is the permanent id. Frontmatter `tools`, `status` (active | retired), `superseded_by`, `issue`, `date`, and `aliases` for the numbers of imported entries, so existing citations still resolve. Entries are retired, never deleted. Two gotchas get two slugs and never collide; the same slug twice is a real duplicate, and git shows it as a conflict. No new numbers: parallel sessions take the same next free one (the homelab table has 15 such duplicates), and renumbering breaks citations.
- Decisions use the same layout, one file per decision with a slug id: same code path, and it ends append conflicts on `decisions.md`. Coordinate with [Configurable decision records](#medium-configurable-decision-records-for-aw-domain-modeling).
- Tags name tools, from a fixed vocabulary; `aw memory add` rejects unknown tags, so a new tag is a deliberate addition. No hierarchy.
- Session start loads only the tag list with counts (`flux 34 · talos 21 · …`, ~150 tokens): enough to know which tools have known traps, so the agent knows when to look.
- `aw-plan-story` writes compact lines (`id · claim`) for the entries that match the story's tags into the plan file, with `aw memory show <id>` for the full entry. The plan is on disk and survives compaction, and the CLI picks the entries, not the model. Full entries are not copied: they would go stale in the plan when one is retired.
- Debugging and unplanned work: two-step search, compact hits (`id · claim`, ~20 tokens each) first, then one full entry.
- Decisions: the decision index goes into the plan at planning time (`aw-plan-story`, grilling); a session without a plan loads the decision index at start, so unplanned work still sees them. Full records on demand.
- Prior art: [encephalon](https://github.com/isaachinman/encephalon). Pointer block in `AGENTS.md`, literal AND search, `--compact` then full, append-only with `supersedes`. It preloads no index at all; this design preloads the tag list on purpose, so the agent knows when to search.

**Scope, first cut** (what the experiment needs):
- Config: `gotchas_dir`; `gotcha_tags` (the vocabulary); `gotchas_load = full | tags` (default `full`).
- `aw memory add gotcha --tags a,b` writes `<slug>.md`; `aw memory find --tags|--text [--compact]`; `aw memory show <id>` (slug or alias); `aw memory tags` (vocabulary with counts); `aw memory supersede` sets `status` and `superseded_by`. The same commands for decisions.
- `aw doctor`: unknown tags, `superseded_by` pointing nowhere, an alias claimed by two entries.
- Skills: `aw-start-task` loads gotchas per `gotchas_load`, and the decision index only when there is no plan; `aw-plan-story` derives tags from the story and the paths the plan touches, and writes the compact gotcha lines and the decision index into the plan; `aw-finalize` and `aw-remember` write files, not appends, and propose rules for workflow pitfalls.
- `aw-finalize` appends one line per session to a gitignored log (`.agents/gotchas-experiment.log`): tokens loaded at start, entries pulled at plan time, whether the gotcha that mattered was among them, gotchas that bit although an entry existed, tag rejections. Nobody records ten sessions by hand.

**Scope, after the first results:** `tag_map` (path glob → tag), `aw memory import` for an existing table, `gotchas_load = none`, and `aw doctor` suggesting `tags` past a size threshold.

**Experiment:** run it in the homelab for ten sessions and read the log. Hooks that inject entries before an edit (Claude Code only) are the fallback if plan-time pulls miss too often.

**Open:**
- `tag_map` alone, model-chosen tags alone, or both (current lean: both).
- Converting an existing table: a one-off in the adopting project, or `aw memory import`. The homelab conversion gives each entry a slug and keeps its number as an alias; a duplicated number stays the alias of the entry its citations mean, and the other entry keeps only its slug.
- Whether `full` stays the default once `tags` has a track record.

**Done when:** the ten sessions are recorded in the README, and the defaults are set from the result.

### [MEDIUM] Spec element above the story

**Context:** Requirements that arrive from outside often exceed one story (Jira epic). `aw-plan-story` currently stops and proposes a sibling split instead.

**Scope:** `aw-to-spec` skill (synthesis of a conversation, no interview, after `mattpocock/skills` `to-spec`), a `spec` template, a committed spec document under `spec_dir` that optionally publishes as an epic, and `aw-to-story` deriving stories from it. Decide the home first: repo document with a tracker pointer, as the planning decision records.

### [LOW] Native blocking links between subtasks

**Context:** `aw-to-subtasks` writes blocking edges as a `## Blocked by` section in the body, because Jira link types are per-instance (`Blocks`, `is blocked by`, renamed schemes) and GitHub has no native equivalent.

**Scope:** `aw issue link <id> blocks <other>`, link-type discovery for Jira, text fallback elsewhere, `aw doctor` reporting the available link types.

### [MEDIUM] Forge operations through aw

**Context:** Skills no longer call trackers directly, but `aw-finalize` still runs `gh pr create`, `gh pr checks`, `glab mr create` itself. Same pattern as the tracker contract, for pull/merge requests.

**Scope:** `aw pr create|checks|comments` per forge; `aw-finalize` calls only `aw`.

### [MEDIUM] Fetch linked design docs (Confluence)

**Context:** Jira stories often link a Confluence page with the design decision. `aw-plan-story` reads linked docs, but has no way to fetch a Confluence page.

**Scope:** `aw doc fetch <url|page-id> [--out DIR]` → Markdown (Confluence REST v2 `body-format=atlas_doc_format` through the existing ADF converter), same credentials as Jira.

### [LOW] GitLab tracker parity

**Context:** The GitLab adapter lacks `children` and `create` and is untested.

**Scope:** implement both with `glab`; test against a GitLab instance.

### [MEDIUM] Configurable decision records for aw-domain-modeling

**Context:** The copied `aw-domain-modeling` skill writes ADRs to `docs/adr/NNNN-slug.md` and terms to `GLOSSARY.md`. Projects that already keep a decision log elsewhere would get a second, competing record.

**Scope:** keys `decision_dir` (or `decision_log` for a single-file log) and `glossary_file`; the skill reads them from `aw config` before writing. Keep the upstream text otherwise, so updates from mattpocock/skills stay easy to merge.

### [MEDIUM] Schema migrations

**Context:** From copier's answers file. `aw init` already asks new questions on re-run and warns about unknown keys, but a renamed or retyped key would drop the old value silently.

**Scope:** a migrations list in `schema.toml` (`{from_version, rename, retype}`); `aw init` applies them and bumps `aw_version`; `aw doctor` points at them.

### [MEDIUM] Vendor skills into a repo

**Context:** From zaks-io/skills. CI agents (e.g. review bots in GitHub Actions) and cloud sessions have no `~/.agents`.

**Scope:** `aw init --vendor` copies skills into `<repo>/.agents/skills` (Codex) and `.claude/skills` (Claude), pinned to an aw version; `aw doctor` reports drift from the installed version. Skills then need a path to `aw` that works without `~/.agents/bin` — decide (`uvx`, vendored script, or skip deterministic steps in CI).

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

### [MEDIUM] Sessions that need several merges

**Context:** A GitOps repo can need more than one merge for one session's work (environment promotion, staged merges with a reconcile gate in between, or a change split across repos). `aw finish` assumes one: it merges the pull request, deletes the branch, removes the worktree and moves the issue to done in a single step, so it cannot survive "merged once, more to go".

**Open first:** which shape the project actually has, and whether the later merges carry the same commits (cherry-pick or merge forward) or new ones (an image tag bump per environment). Design after that is answered; parked until then.

### [LOW] Per-skill model override for Claude Code

**Context:** Frontmatter `model:` is Claude-only and static. With symlinked skills all agents share one `SKILL.md`, so it cannot be set per machine. With the deterministic steps in `aw`, the saving is small.

**Scope, if wanted:** a `--copy` install mode for Claude that renders `model:` from the user or local layer.

### [LOW] More install targets and copy mode

**Context:** From vercel `npx skills` (symlink or copy, `--agent` targets). Only `claude` needs links today. Windows and some sync tools handle symlinks badly.

**Scope:** `--copy` mode with a marker file so `aw install` can safely replace its own copies; add agents to `AGENT_DIRS` as needed.

### [LOW] Non-editable install and publishing

**Context:** `pyproject.toml` force-includes `skills/` into the wheel as `aw/_skills`, and `install.skills_source()` falls back to it, but only the editable install is tested.

**Scope:** test `uv tool install git+<url>`; check that `npx skills add <repo>` finds the skills (layout is spec-compliant).

### [MEDIUM] Changelog fragments for shared repos

**Context:** Session ids are no longer committed, but every PR still edits the same `CHANGELOG.md`, so parallel PRs conflict. towncrier and changesets solve this with one file per change (`changelog.d/<branch>.md`), compiled at release.

**Scope:** `changelog_mode = file | fragments` plus `changelog_dir`; `aw-finalize` writes a fragment in fragments mode; `aw changelog build` compiles and removes fragments.

### [LOW] Session number race

**Context:** Two `aw start-task` runs in the same clone at the same moment compute the same number; the second fails on "path exists" only if the slug matches too.

**Scope:** take a lock file next to `aw-last-session` while computing the number and creating the worktree.

### [LOW] Session title hook

**Context:** From agent-issue-tracker. Set the agent session title to `s<N> <slug> (#issue)` so parallel sessions are distinguishable. Claude Code hook; other agents vary.

### [LOW] Mark finished plans as history

**Context:** With `plan_scope = repo`, plans stay in `.agents/plans/` after their story is done. A later session that finds one cannot tell a live plan from a finished one, and may read old steps as current requirements. [encephalon](https://github.com/isaachinman/encephalon) keeps its old plans and specs for the record but marks them as history, "not current requirements".

**Scope:**
- `aw-finalize`, when the merged work closes the last subtask of a story, sets the plan's `**Status:**` line to `done` and adds the merge date, in the same PR.
- `aw plan state` reports the status; `aw-plan` routes a `done` plan to "nothing pending" instead of offering to cut subtasks.
- Plans are not moved or deleted; the path that subtasks and comments cite keeps working.

**Done when:** a finished story's plan reads `Status: done` without a manual edit, and `aw-plan` treats it as finished.

---

## Considered and not planned

- **Personas and multi-agent roles** (BMAD), **spec-driven phases** (spec-kit), **label-based handoff queues** (zaks-io): full methods of their own; out of scope for a session-workflow standard.
- **Central registry of project configs**: replaced by committed `.agents/aw.toml`, which travels with the repo.
