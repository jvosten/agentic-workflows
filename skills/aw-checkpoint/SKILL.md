---
name: aw-checkpoint
description: Merge one part of a session and keep going - verify, open a part merge request, pass CI and the merge gate, merge with aw merge, check the change live, then continue the session. Use at a plan's "Checkpoint:" step, when a change has to be live before the next one can be built or checked (GitOps reconcile, a migration, a deploy), or when the user says "checkpoint", "merge this part", "ship this step".
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw session) Bash(~/.agents/bin/aw verify) Bash(~/.agents/bin/aw issue ref:*) Bash(~/.agents/bin/aw template mr) Bash(~/.agents/bin/aw mr create:*) Bash(~/.agents/bin/aw mr update:*) Bash(~/.agents/bin/aw mr view:*) Bash(~/.agents/bin/aw mr checks:*) Bash(~/.agents/bin/aw mr comments:*) Bash(~/.agents/bin/aw merge:*) Bash(~/.agents/bin/aw restack:*)
metadata:
  package: agentic-workflows
---

# Checkpoint

Request: $ARGUMENTS

One merge in the middle of a session. The worktree, the branch and the issue stay; the session goes on after the live check. The end of the session is `/aw-finalize`, not this.

## 1. Load the session and find where it stands

```bash
~/.agents/bin/aw session
~/.agents/bin/aw config
```

Not in a session worktree, or `forge = none` without a manual merge in mind → say so and stop.

Stacked session (`aw session` shows a non-empty `base`) → the dependency blocks merging, not preparation for review. Continue verification, commit/push, draft part-MR creation or update, CI and review (steps 2–4). Check the base before the merge gate in step 5; do not stop here just because its request is open.

Resume from what the forge and git say, not from memory of an earlier turn:

| State | Continue at |
|---|---|
| uncommitted or unpushed work for this part | step 2 |
| an open merge request for the branch (`aw mr view` shows it) | step 4, or step 5 when CI is through |
| the request merged, branch not yet at `main`'s tip | step 6 (`aw merge` picks up a merged request) |
| merged and caught up | step 7 |

## 2. Make the part consistent

- `~/.agents/bin/aw verify`; non-zero → fix and re-run.
- Docs: apply the documentation rules in `instructions_file` to what this part makes wrong. `main` has to be consistent after every merge, not only the last one.
- Not now: memory, leftovers, the backlog inbox and the changelog. They are `/aw-finalize`'s, at the end of the session. The inbox file stays untracked; `aw merge` ignores it.
- Commit with the project's conventions and push: `git -C <worktree> push -u origin <branch>`.

## 3. Open the part's merge request

Load `aw-merge-request` for this part:

- `--part` on `aw mr create`: it links the issue as `Refs #12 (part N)`, which does not close it, and prints the part number in the dry run.
- Title: the project's format from `contributing_file`, if it has one; otherwise the usual title with ` (part N)` appended.
- The body covers this part only: what it changes and what the live check will look at.
- Stacked with an open base request: `--part --draft`. Target the recorded `base` and link its merge request in the description as a dependency.
- Reuse the branch's existing open request when resuming; update it through `aw mr update` when needed. A dependency wait does not start a new part.

## 4. CI and review

```bash
~/.agents/bin/aw mr checks --watch
~/.agents/bin/aw mr comments
```

CI failure → fix, push, wait again. Exit 2 (pending, or `no checks yet` although CI is configured) is not green: watch again, and report instead of merging if the checks never appear. An unresolved review point, something unplanned in the diff, or an unclear risk → stop and report; never merge past it.

## 5. Merge gate

For a stacked session, inspect the base request with `~/.agents/bin/aw mr view <base>`:

- Base still open, closed without merging, or state uncertain → stop before `aw merge`. Report the part-MR link, CI/review state and base dependency. This is a workflow wait, not an observed CLI refusal; do not call `aw merge` to probe it.
- Base merged → run `~/.agents/bin/aw restack` to move onto `main_branch` and retarget the existing part request. Resolve any conflicts as instructed. Re-run `aw verify` and step 4 on the new HEAD, inspect the updated target and diff, then return to this gate. Do not reuse CI results or approval from before the restack. The base's worktree and branches may already be deleted. A rebase still active → resolve it and `git rebase --continue` before rerunning restack. A completed rebase with a recorded target, or a failed push or retarget → rerun restack to finish; do not edit the session's fork point by hand.

The part request must no longer be draft before merging. If it is still draft, ask the user to mark the existing request ready in the forge, then re-read `aw mr view`.

Every merge here deploys, so the gate holds for every part. `merge_gate = approve`: show `~/.agents/bin/aw mr view` as it is, the few lines of what this part changes, and what the live check will be; wait for an explicit go. No go → stop and say that `/aw-checkpoint` resumes here. `merge_gate = auto`: continue.

## 6. Merge

```bash
~/.agents/bin/aw merge      # forge = none: after merging by hand
```

It merges the branch's open request, refuses commits the request does not contain, updates `main_branch`, moves the branch to `main`'s tip (after a squash or rebase merge it also deletes the merged remote branch; the next `git push -u` recreates it), comments on the issue, and runs `on_merge`. A session stacked on this branch gets a warning line: tell the user to run `aw restack` there.

`on_merge` warned (exited non-zero) → stop and report before the live check: checking a system that did not reconcile tells nothing.

`ignored from the branch: <keys>` → this part changes trusted keys (hooks, `merge_gate`, `merge_method`); the merge ran with the primary checkout's values, and the branch's apply now that they are in `main_branch`. Tell the user. `sandboxed: aw merge runs on the host` → stop: the session runs in a sandbox, and the host merges the part; report that it is pushed and green.

## 7. Live check

What to check: the plan section's **Checks** for this part, and what `instructions_file` says about verifying deployments. Check read-only, the way the project's rules allow (for GitOps: the reconciled resources and their state, not a manual apply).

- Passes → report it in two lines and go on with the session's next task.
- Fails → the change is live. Stop and ask: **fix forward** (new commits on the same branch, then the next checkpoint) or **revert** (a revert commit through a checkpoint of its own)? Recommend fix forward unless the failure hurts now; the choice is the user's.

## Rules

- Never `aw finish` from this skill; the session is not over.
- One merge request per part; never merge two parts in one request after the fact.
- No secret values in titles, bodies or comments.
