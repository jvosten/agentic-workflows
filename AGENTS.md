# Agent instructions

`aw` is a session workflow for coding agents: skills under `skills/` carry the judgement, the `aw` CLI under `src/aw/` does every step that must happen the same way each time. This repo builds both, and uses them on itself.

## Checks

`make check` is what CI runs and the `verify_cmd` of sessions here. Run it before every commit.

| Target | Runs |
|---|---|
| `make test` | `pytest` |
| `make lint` | `ruff check` and `ruff format --check` on `src` and `tests` |
| `make types` | `ty check` on `src` and `tests` |
| `make format` | `ruff check --fix` and `ruff format`: run it before `make lint` complains |

`ruff` and `ty` are pinned exactly in the dev group of `pyproject.toml`; bump them on purpose, in their own change. The ruff rule set is strict; every exception in `pyproject.toml` or in a `# noqa` carries its reason. Add a new exception the same way, or fix the finding.

CI (`.github/workflows/ci.yml`) runs the tests on Python 3.11 (the `requires-python` floor) and 3.13, and ruff and ty once, on every pull request and push to `main`.

## Tests

- Tests never reach the network. `tests/conftest.py` makes sockets refuse, puts failing `gh` and `glab` stand-ins
  first on `PATH`, and clears `AW_*`, `JIRA_*`, `GH_*`, `GITHUB_*`, `GITLAB_*` and `GLAB_*`. Fake forge and tracker
  calls with `monkeypatch`; never depend on credentials or a live service.
- `origin` is a local bare repository in `tmp_path` (fixture `repo`).
- A session worktree reads `.agents/aw.toml` from its own checkout. A config written to the primary checkout and not
  committed is invisible there: set the value with `monkeypatch.setenv("AW_<KEY>", …)` instead.
- Isolation lives in the test suite, not in `.envrc`: `make check` must behave the same with or without direnv, in CI
  and in agent shells.
- A bug fix starts with a test that fails without it.

## Rules

- **Deterministic steps go into `aw`, judgement into skills.** A skill calls `aw` for anything that must not vary (branches, merges, tracker writes); `aw` never asks the model to decide.
- **The CLI output is a contract.** Skills read `aw`'s output: `key=value` lines from `start-task` and `session`, the JSON of `aw issue rollup --json`, issue rows and their markers, and the phrases skills branch on. `tests/test_cli_protocol.py` pins them. Do not reword them in passing; a change to them is a change to every skill that reads them, made in the same change.
- **Safety before convenience.** Anything that closes, merges or deletes refuses on an uncertain fact (a failed or partial listing, unpushed work, a request that does not cover HEAD). Report-only paths may say "unknown".
- **Sandbox-ready.** Skills will run in micro-VMs that see only the project. New code adds no runtime dependence on `$HOME` paths, makes network calls only through the provider adapters (with a timeout), never assumes the primary checkout is reachable, and never checks a credential's shape (sandboxes pass placeholders).
- **Docs move with the code.** `README.md` (commands, configuration, trackers), `docs/boards.md` (status moves), and the skills that call a changed command.

## Changes

- Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `style:`, `refactor:`), subjects that say what changed, as in `git log` here. No `Co-Authored-By` or "Generated with" lines in commits or pull requests.
- One `CHANGELOG.md` entry per merge request, under the version it ships in.
- Ideas and deferred work go to `BACKLOG.md` (`aw backlog add`): one `###` item per entry with a priority tag; resolved items are deleted, not struck through.
- Plans are local (`plan_scope = "local"`, gitignored under `.agents/plans/`); the current one is `.agents/plans/hardening-2026-10-10.md` in the primary checkout.
- Public repository: nothing here names private projects, hosts or people; examples use neutral names.
