---
name: aw-finalize
description: Finish an implementation session - document, verify, commit, open the pull request, add the changelog entry, wait for CI, merge, and clean up the worktree. Use only when the user invokes it.
disable-model-invocation: true
allowed-tools: Bash(~/.agents/bin/aw session) Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw verify) Bash(~/.agents/bin/aw issue ref:*) Bash(~/.agents/bin/aw issue pr-text:*) Bash(~/.agents/bin/aw memory add:*)
metadata:
  package: agentic-workflows
---

# Finalize

Request: $ARGUMENTS

## 1. Load session and settings

Run both from the session worktree:

```bash
~/.agents/bin/aw session
~/.agents/bin/aw config
```

On error, show it and stop. `session` gives `branch`, `worktree`, `issue`; all paths below are under `worktree`.

## 2. Review the work

- `git -C <worktree> status` and `git -C <worktree> diff <main_branch>...HEAD`.
- List what changed and why, in a few lines. You need this for docs, the PR, and the changelog.

## 3. Documentation

Apply the documentation rules in `<worktree>/<instructions_file>`: decision records, reference docs, runbooks, known pitfalls — whatever the project requires for this kind of change. No rules there → update docs the change makes wrong, nothing more.

## 4. Project memory

Something in this session cost you time and is not visible in the code — a version pin, an API quirk, an ordering rule, a tool that lies — then record it, one entry each:

```bash
~/.agents/bin/aw memory add gotcha --title "<the constraint as a claim>" --body-file - --ref <issue>
```

It is committed with this session, so it lands in the same review. Nothing cost you time → write nothing.

## 5. Verify

```bash
~/.agents/bin/aw verify
```

Non-zero exit → fix the cause and re-run. Do not continue on a failing check.

## 6. Commit and open the pull request

- Commit in logical units, using the project's commit conventions (conventional commits unless `instructions_file` says otherwise). Push with `git -C <worktree> push -u origin <branch>`.
- Open the PR against `main_branch`. With an issue: put `aw issue ref <issue>` in the title (Jira links PRs by key) and the line from `aw issue pr-text <issue>` in the body. The body summarizes the change and risks.
  - `forge = github`: `gh pr create --base <main_branch> --title ... --body ...`
  - `forge = gitlab`: `glab mr create --target-branch <main_branch> --title ... --description ...`
  - `forge = none`: skip; tell the user to merge by hand.

## 7. Changelog

If `changelog_file` is set: add one entry for this session, matching the file's existing format (position, heading style, level of detail) and naming the PR. Commit and push.

## 8. Review and CI

- Read the PR diff and all review comments (`gh pr view <pr> --comments` / `glab mr view <pr> --comments`).
- Wait for CI (`gh pr checks <pr> --watch` / `glab ci status --live`).
- CI failure → fix, push, wait again.
- Stop and report instead of merging when: a reviewer raised an unresolved point, the diff contains something unplanned, or you are unsure about a risk.

## 9. Merge and clean up

```bash
~/.agents/bin/aw finish --pr <pr>      # forge = none: after the manual merge, without --pr
```

It merges with `merge_method`, moves the issue to done where a closing keyword does not (`sync_issue_status`), removes the worktree, updates `main_branch` in the primary checkout, and deletes the local and remote branch. It refuses on uncommitted or unpushed work.

## 10. Report

Print the PR link, what was merged, anything deferred, and the first step for the next session.
