---
name: aw-finalize
description: Finish an implementation session - document, verify, commit, open the pull request, add the changelog entry, wait for CI, then merge after your approval (or directly with merge_gate = auto) and clean up the worktree. Use only when the user invokes it.
disable-model-invocation: true
allowed-tools: Bash(~/.agents/bin/aw session) Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw verify) Bash(~/.agents/bin/aw issue ref:*) Bash(~/.agents/bin/aw issue pr-text:*) Bash(~/.agents/bin/aw memory add:*) Bash(~/.agents/bin/aw backlog add:*) Bash(~/.agents/bin/aw backlog list) Bash(~/.agents/bin/aw backlog pop:*) Bash(~/.agents/bin/aw issue dupes:*) Bash(~/.agents/bin/aw issue children:*) Bash(~/.agents/bin/aw issue create:*) Bash(~/.agents/bin/aw issue set-parent:*) Bash(~/.agents/bin/aw issue set-status:*)
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

## 5. Leftovers and the backlog inbox

Work this session deliberately did not do — deferred scope, a refactor the change made obvious, a pitfall worth fixing later — goes into the backlog, not into the pull request text. Load the `aw-backlog-item` skill once per item. Never let a leftover leave the session as a sentence nobody will read again.

Then, with `backlog_home = tracker` (and a tracker set), empty the session inbox: the items noted during the session plus the leftovers just added.

```bash
~/.agents/bin/aw backlog list
```

- `no items` → nothing to do.
- Otherwise load `aw-backlog-item` to empty the inbox: per item, the user decides **send** to the tracker or **discard**. Nothing stays in the file; `aw finish` refuses while it holds items.
- The emptied file is deleted. It was committed earlier in the session → commit its deletion with the rest of the work.

With `backlog_home = file`, the items stay in `backlog_file` and are committed with the session.

## 6. Verify

```bash
~/.agents/bin/aw verify
```

Non-zero exit → fix the cause and re-run. Do not continue on a failing check.

## 7. Commit and open the pull request

- Commit in logical units, using the project's commit conventions (conventional commits unless `instructions_file` says otherwise). Push with `git -C <worktree> push -u origin <branch>`.
- Open the PR against `main_branch`. With an issue: put `aw issue ref <issue>` in the title (Jira links PRs by key) and the line from `aw issue pr-text <issue>` in the body. The body summarizes the change and risks.
  - `forge = github`: `gh pr create --base <main_branch> --title ... --body ...`
  - `forge = gitlab`: `glab mr create --target-branch <main_branch> --title ... --description ...`
  - `forge = none`: skip; tell the user to merge by hand.

## 8. Changelog

If `changelog_file` is set: add one entry for this session, matching the file's existing format (position, heading style, level of detail) and naming the PR. Commit and push.

## 9. Review and CI

- Read the PR diff and all review comments (`gh pr view <pr> --comments` / `glab mr view <pr> --comments`).
- Wait for CI (`gh pr checks <pr> --watch` / `glab ci status --live`).
- CI failure → fix, push, wait again.
- Stop and report instead of merging when: a reviewer raised an unresolved point, the diff contains something unplanned, or you are unsure about a risk. This holds under either `merge_gate`.

## 10. Merge gate

`merge_gate = approve` (the default): stop here. A merge to `main_branch` may be a deploy, and the permission prompt on `aw finish` is not a gate: an allowlist removes it silently. Show:

- the PR link and title;
- CI: every check and its result (`gh pr checks <pr>` / `glab ci status`);
- review: approvals and unresolved comments, or "none";
- the diff summary: files changed with lines added and removed, and the few lines of step 2;
- what `aw finish` will do: merge with `merge_method`, move the issue, remove the worktree, delete the branch.

Then ask whether to merge, and wait for an explicit go ("merge", "go", "yes"). Anything else, or no answer → stop, report as in step 12, and say that `/aw-finalize` resumes at this step or `aw finish --pr <pr>` merges by hand. A push after the go (a late fix) means CI again, and the gate again.

`merge_gate = auto`: continue without asking.

## 11. Merge and clean up

```bash
~/.agents/bin/aw finish --pr <pr>      # forge = none: after the manual merge, without --pr
```

It merges with `merge_method`, moves the issue to done where a closing keyword does not (`sync_issue_status`) and runs `on_issue_status`, removes the worktree, updates `main_branch` in the primary checkout, and deletes the local and remote branch. It refuses on uncommitted or unpushed work, and while the backlog inbox holds items.

## 12. Report

Print the PR link, what was merged (or that the PR waits at the gate), what went to the tracker (issue refs) or was discarded, and the first step for the next session.
