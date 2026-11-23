### Added

- The `changelog` key chooses where a session's entry goes: `file` (one shared `changelog_file`), `dir` (one
  fragment per session in `changelog_dir`) or `none`. A config with only `changelog_file` reads as
  `changelog = "file"`, or `none` when it is empty; `aw init` writes it. `aw init` proposes `dir` when
  `changelog.d/` exists.
- `aw changelog target`, `check` and `collect [--heading LINE]`: where the entry goes, whether it exists, and
  folding the fragments into `changelog_file` at a release. `aw` knows no categories, heading format or versioning
  scheme. `aw template changelog` is the outline of a new fragment.

### Changed

- `/aw-finalize` writes the entry where `aw changelog target` says and confirms it with `aw changelog check`. The
  entry names no request number and no version.
- This repository keeps one fragment per pull request in `changelog.d/`; a release collects them and sets the
  version.
- `aw doctor` checks only the changelog paths the configured strategy uses.

### Removed

- `aw mr next` and `aw mr create --expect`: no entry names its request number before the request opens.
