---
name: aw-finalize
description: Finish an implementation session - document, verify, add the changelog entry, commit, open the pull request, wait for CI, then merge after your approval (or directly with merge_gate = auto) and clean up the worktree. Use only when the user invokes it.
disable-model-invocation: true
allowed-tools: Bash(~/.agents/bin/aw session) Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw verify) Bash(~/.agents/bin/aw issue ref:*) Bash(~/.agents/bin/aw template mr) Bash(~/.agents/bin/aw mr next) Bash(~/.agents/bin/aw mr create:*) Bash(~/.agents/bin/aw mr update:*) Bash(~/.agents/bin/aw mr view:*) Bash(~/.agents/bin/aw mr checks:*) Bash(~/.agents/bin/aw mr comments:*) Bash(~/.agents/bin/aw memory add:*) Bash(~/.agents/bin/aw memory log:*) Bash(~/.agents/bin/aw memory implemented:*) Bash(~/.agents/bin/aw memory supersede:*) Bash(~/.agents/bin/aw memory find:*) Bash(~/.agents/bin/aw memory show:*) Bash(~/.agents/bin/aw memory tags:*) Bash(~/.agents/bin/aw backlog add:*) Bash(~/.agents/bin/aw backlog list) Bash(~/.agents/bin/aw backlog pop:*) Bash(~/.agents/bin/aw issue dupes:*) Bash(~/.agents/bin/aw issue children:*) Bash(~/.agents/bin/aw issue create:*) Bash(~/.agents/bin/aw issue set-parent:*) Bash(~/.agents/bin/aw issue set-status:*) Bash(~/.agents/bin/aw issue rollup --json:*) Bash(~/.agents/bin/aw restack:*)
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

- `git -C <worktree> status` and `git -C <worktree> diff <target>...HEAD`. `<target>` is the session's `base` while it is stacked, else `main_branch`.
- List what changed and why, in a few lines. You need this for docs, the PR, and the changelog.
- After checkpoints (`/aw-checkpoint`), earlier parts are already in `main`: the diff holds only what came after the last one, and may be empty. Fill only what is missing below; never redo what a part already merged.

## 3. Documentation

Apply the documentation rules in `<worktree>/<instructions_file>`: decision records, reference docs, runbooks, known pitfalls — whatever the project requires for this kind of change. No rules there → update docs the change makes wrong, nothing more.

## 4. Project memory

Something in this session cost you time and is not visible in the code, then record it, one entry each, following the `aw-remember` skill:

- external tool behavior (a version pin, an API quirk, a tool that lies) → a gotcha, tagged, with Symptom / Cause / Fix: `~/.agents/bin/aw memory add gotcha --title "<claim>" --tags <tag,tag> --body-file - --ref <issue>`;
- a workflow pitfall that bites whatever the tool → no memory entry: propose the rule text for `instructions_file` and let the user decide.

Only what this session ran into counts: a symptom you saw, a cause you verified, a fix you tested. A pitfall you only expect goes to the backlog (step 5), not into memory.

This session built a decision recorded as intent (`aw memory find --kind decision --compact` marks them `(intent: …)`) → `~/.agents/bin/aw memory implemented <id> --ref <issue>`. It built it differently → write the new decision and `aw memory supersede <old> --by <new>`.

It is committed with this session, so it lands in the same review. Nothing cost you time and no intent was built → write nothing.

Then record the session for the gotchas experiment (the log is gitignored, one line per session):

```bash
~/.agents/bin/aw memory log --relevant <gotcha ids that mattered, or none> --missed <ids that bit although they existed, or none> [--note "<one line>"]
```

- **relevant**: gotchas whose knowledge changed what you did this session, whether you had them from the plan or looked them up.
- **missed**: a gotcha that bit although an entry for it existed, because nobody looked or the plan did not pull it. A gotcha recorded new this session is neither.
- `--note`: a tag that was missing or wrong, a lookup that found nothing although it should have.

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

## 7. Changelog

The entry is part of the work: it is in the commits the merge request opens with, so a reviewer or review bot that runs once on open sees it. Never a commit after the request opened.

If `changelog_file` is set: add one entry for this session, matching the file's existing format (position, heading style, level of detail). When the format names the merge request, take its number from

```bash
~/.agents/bin/aw mr next      # the number the next merge request gets, e.g. #12
```

and remember it for step 8. `forge = none` → no number; name what the format allows without one.

After checkpoints: one entry for the whole session, naming every part, this one by `aw mr next`. A part already merged it → do not write a second one. It misses later parts → extend it in the final merge request, but never open a merge request just for that.

## 8. Commit and open the merge request

- Commit in logical units, using the project's commit conventions: `contributing_file` (default `CONTRIBUTING.md`) first, then `instructions_file`, else conventional commits. The changelog entry goes with them, not in a commit of its own after the request. Push with `git -C <worktree> push -u origin <branch>`.
- Load the `aw-merge-request` skill to write and open the merge request against `main_branch`, or against the base while the session is stacked. It follows the contribution rules and the merge request template, and `aw mr create` adds the issue's closing line. The entry names a number → pass it as `--expect <N>`.
- `the next request is #M, not #N` → nothing was created: another request or issue took the number. Change the entry to `#M`, commit, push, and create with `--expect M`.
- `#M opened, not #N` (exit 1; the request exists) → a race between the check and the create. Change the entry to `#M`, commit and push; the only changelog commit after opening, and only then.
- `forge = none`: no merge request; tell the user to merge by hand.
- Nothing left to commit after checkpoints → no merge request; go to step 11. `aw finish` sees that nothing is left to merge, skips the merge and the gate does not apply, and closes the issue itself.

## 9. Review and CI

```bash
~/.agents/bin/aw mr checks --watch      # waits; prints one line per failing check; exit 0 passed, 1 failed, 2 pending or no checks yet
~/.agents/bin/aw mr comments            # unresolved review threads, then general comments
```

- CI failure → fix, push, wait again.
- Exit 2 (pending, or `no checks yet` although CI is configured) is not green: watch again; if the checks never appear, report it and do not merge.
- Every unresolved thread: fix it and push, or answer it; never resolve someone else's point silently.
- Stop and report instead of merging when: a reviewer raised an unresolved point, the diff contains something unplanned, or you are unsure about a risk. This holds under either `merge_gate`.

## 10. Merge gate

`merge_gate = approve` (the default): stop here. A merge to `main_branch` may be a deploy, and the permission prompt on `aw finish` is not a gate: an allowlist removes it silently. Show:

- `~/.agents/bin/aw mr view`: link and title, state, CI, review and unresolved threads, files changed with lines added and removed — print it as it is;
- the few lines of step 2: what changed and why;
- what `aw finish` will do: merge with `merge_method`, move the issue, remove the worktree, delete the branch;
- with an `issue`, the parent story: `~/.agents/bin/aw issue rollup --json <issue>` — print its `line` as it is. Keep `--json` first: only that form is pre-approved, and it can never close (`--json` and `--close` exclude each other).

Then ask whether to merge, and wait for an explicit go ("merge", "go", "yes"). When its `decision` is `can_close`, ask too whether to close the story with the merge; that answer is separate, and only an explicit yes closes it. A story can hold work never cut into a subtask, so never assume it. Anything else, or no answer → stop, report as in step 12, and say that `/aw-finalize` resumes at this step or `aw finish --pr <pr>` merges by hand. A push after the go (a late fix) means CI again, and the gate again.

`merge_gate = auto`: continue without asking.

`merge_gate` is the primary checkout's: a branch that changes it does not change this gate (`aw config` in the worktree already prints the value that applies).

## 11. Merge and clean up

Stacked session (`aw session` shows a non-empty `base`) → `aw finish` refuses until the base merged. Base not merged yet → stop and report: the session waits for the base, and `/aw-finalize` resumes here. Base merged:

```bash
~/.agents/bin/aw restack      # rebases onto main_branch, force-pushes, retargets the merge request, clears base
```

Tell the user its summary line. The merged base's worktree and branches need not exist. A conflict → name the files to the user, resolve them, `git add`, `git rebase --continue`, then `aw restack` again. Do not start another rebase while one is active. A rebase completed onto the recorded target, or a failed push or retarget → rerun `aw restack` to finish; do not edit the session's fork point by hand. `--dry-run` previews recovery without pushing or changing session metadata. The push restarts CI: back to step 9, then the gate.

```bash
~/.agents/bin/aw finish      # the branch's open request; forge = none: after the manual merge
```

It merges the branch's open request with `merge_method` (a request you merged on the forge yourself counts as that merge; it skips the merge when nothing is left after checkpoints), moves the issue to done where a closing keyword does not (`sync_issue_status`) and runs `on_issue_status`, removes the worktree, fast-forwards the local `main_branch` (whatever the primary checkout has checked out), runs `on_merge`, and deletes the local and remote branch. It refuses on uncommitted or unpushed work, and while the backlog inbox holds items.

- `ignored from the branch: <keys>` → the branch changes trusted keys (hooks, `merge_gate`, `merge_method`); this merge ran with the primary checkout's values, the branch's apply from now on. Tell the user.
- `sandboxed: aw finish runs on the host` → stop: the session runs in a sandbox. Report that the branch is pushed and the request is green; the merge happens on the host.

The user said yes to closing the parent story at the gate → `~/.agents/bin/aw finish --close-parent`: after the issue, it moves the story to done and comments with its children. It leaves the story open with a warning when something still keeps it open; report that. No yes, `merge_gate = auto`, or a gate that did not apply → never pass it; `aw finish` then prints whether the story can close.

## 12. Report

Print the PR link, what was merged (or that the PR waits at the gate), what went to the tracker (issue refs) or was discarded, the parent story's state (closed, or `aw finish`'s line on it), and the first step for the next session.
