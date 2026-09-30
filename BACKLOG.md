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
- Codex finds `~/.agents/skills/aw-start-task` and honours `agents/openai.yaml` (`allow_implicit_invocation: false`).

**Done when:** one real session per agent has run through both skills, and the findings are in the README.

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

---

## Considered and not planned

- **Personas and multi-agent roles** (BMAD), **spec-driven phases** (spec-kit), **label-based handoff queues** (zaks-io): full methods of their own; out of scope for a session-workflow standard.
- **Central registry of project configs**: replaced by committed `.agents/aw.toml`, which travels with the repo.
