# Changelog

## 0.2.0 — 2026-10-13

### Added

- Stacked sessions: `aw start-task --base <branch>` starts a session on another session's unmerged branch, and
  `aw restack` follows the base or moves onto `main` once it merged, for `merge`, `squash` and `rebase` merges.
  `aw mr create` targets the base; `aw merge` / `aw finish` refuse while it is unmerged and warn in the base session.
  Skills and README describe the flow (README "Stacked sessions").

### Changed

- Tests never reach the network: sockets refuse, `gh` and `glab` fail, forge and tracker credentials are cleared.
- This repository uses `forge = "github"`.

## 0.1.0

- First version: `aw` CLI with layered project config, sessions in worktrees, the planning and session skills,
  tracker adapters for GitHub, GitLab and Jira, merge requests through `aw mr`, multi-merge sessions, project
  memory and the backlog.
