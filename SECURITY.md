# Security

## Reporting a vulnerability

Report it in private: on GitHub, open the repository's **Security** tab and choose **Report a vulnerability**. Do not open a public issue or pull request for it.

Include the `aw --version`, the command or skill, the configuration keys involved, and the steps to reproduce.

## Scope

`aw` runs `git`, `gh` and `glab` with your credentials, and its skills let a coding agent merge, close and delete. Reports of interest:

- a command that merges, closes, deletes or force-pushes without the checks the README describes;
- text from an issue, a comment or a review by someone without write access that steers the agent or passes as a go;
- a committed configuration value or a path that reaches outside the repository;
- a secret or a private term that `aw` writes to a tracker, a forge or the repository.

`AW_SANDBOXED` is a contract for sandbox runners, not a security boundary.

## Supported versions

Only the latest release gets fixes. Before 1.0, a minor version may break commands, output and configuration.
