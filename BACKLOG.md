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
- Codex finds `~/.agents/skills/aw-start-task` and honours `agents/openai.yaml` (`allow_implicit_invocation: false`).

**Done when:** one real session per agent has started through the skill, and the findings are in the README.

### [HIGH] aw-finalize skill

**Context:** Second half of the session workflow. A typical project `finalize` skill mixes judgement (docs, changelog text, PR description) with deterministic steps (commit, push, PR, CI wait, merge, worktree removal, branch deletion, prune).

**Scope:**
- `aw finish` subcommand for the deterministic tail: run `verify_cmd`, merge without `--delete-branch`, remove the worktree, delete the local branch, `git remote prune origin`.
- Skill keeps: update docs, changelog, and the session log row; write the PR body; review the diff; hand back to the user before merging.
- New keys, likely: `changelog_file`, `session_log_row` (row template), `pr_close_keyword` (`Fixes`, `Closes`).
- User-invoked only, like `aw-start-task`.

### [HIGH] Tracker operation contract (GitHub, GitLab, Jira)

**Context:** Borrowed from [agent-issue-tracker](https://github.com/maxdimitrov/agent-issue-tracker): skills name an operation, one adapter per backend implements it. Today `aw-start-task` branches on `tracker` in prose (`gh` vs `glab`).

**Scope:**
- `aw issue <op>` with a fixed set: `view`, `set-status`, `link-pr`, `create`, `comment`.
- Adapters: `github` (`gh`), `gitlab` (`glab`), `jira` (Jira CLI or REST; decide).
- Add `jira` to the `tracker` choices and the `aw init` prompt; detect Jira from the remote or an existing config.
- `on_issue_start` stays as a project hook for extras such as moving an issue on a project board.

### [MEDIUM] Status mapping per tracker

**Context:** From zaks-io/skills. Skills should speak canonical states (`backlog`, `ready`, `in_progress`, `done`); each project maps them to tracker names (`"In progress"`, Jira transitions). Needed once `set-status` exists.

**Scope:** a `status_map` table key in the schema (needs table support in `config.py` and `dump_toml`).

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

### [LOW] Session number race

**Context:** Two `aw start-task` runs at the same moment compute the same number; the second fails on "path exists" only if the slug matches too. Rare with one user.

**Scope:** take a lock file in the git common dir while computing the number and creating the worktree.

### [LOW] Session title hook

**Context:** From agent-issue-tracker. Set the agent session title to `s<N> <slug> (#issue)` so parallel sessions are distinguishable. Claude Code hook; other agents vary.

---

## Considered and not planned

- **Personas and multi-agent roles** (BMAD), **spec-driven phases** (spec-kit), **label-based handoff queues** (zaks-io): full methods of their own; out of scope for a session-workflow standard.
- **Central registry of project configs**: replaced by committed `.agents/aw.toml`, which travels with the repo.
