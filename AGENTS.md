# Agent instructions

## Checks

- `make check` runs the test suite. Run it before every commit.

## Tests

- Tests never reach the network. `tests/conftest.py` makes sockets refuse, puts failing `gh` and `glab` stand-ins
  first on `PATH`, and clears `AW_*`, `JIRA_*`, `GH_*`, `GITHUB_*`, `GITLAB_*` and `GLAB_*`. Fake forge and tracker
  calls with `monkeypatch`; never depend on credentials or a live service.
- `origin` is a local bare repository in `tmp_path` (fixture `repo`).
- A session worktree reads `.agents/aw.toml` from its own checkout. A config written to the primary checkout and not
  committed is invisible there: set the value with `monkeypatch.setenv("AW_<KEY>", …)` instead.
- Isolation lives in the test suite, not in `.envrc`: `make check` must behave the same with or without direnv, in CI
  and in agent shells.

## Changes

- Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- One `CHANGELOG.md` entry per merge request, under the version it ships in.
- Ideas and deferred work go to `BACKLOG.md` (`aw backlog add`).
