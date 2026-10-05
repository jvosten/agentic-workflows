"""aw verify, aw merge and aw finish: the deterministic end of a session part, and of the session.

aw merge   one merge of a multi-merge session: the branch catches up with main and the session goes on
aw finish  the last merge (or none, when every change already went through aw merge), then cleanup
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from aw import backlog, forge, trackers
from aw.config import AwError, Config, git

PREFIX = {"github": "#", "gitlab": "!"}


def verify(cfg: Config) -> int:
    cmd = cfg.get("verify_cmd")
    if not cmd:
        print("verify_cmd is not set; nothing to run", file=sys.stderr)
        return 0
    args = ["direnv", "exec", str(cfg.checkout), "sh", "-c", cmd] if cfg.get("direnv") else ["sh", "-c", cmd]
    return subprocess.run(args, cwd=cfg.checkout, check=False).returncode


def _preflight(cfg: Config, worktree: Path, branch: str, ignore_inbox: bool) -> None:
    """Clean and pushed. An intermediate merge ignores the untracked backlog inbox: the session goes on.

    Pushed means in the remote branch or already in main: after an intermediate merge the branch sits at
    main's tip, ahead of its remote (or, after a squash, without one), and none of that is unpushed work.
    """
    inbox = cfg.get("backlog_file") if ignore_inbox and backlog.home(cfg) == "tracker" else ""
    dirty = [line for line in git("status", "--porcelain", cwd=worktree).splitlines()
             if not (inbox and line == f"?? {inbox}")]
    if dirty:
        raise AwError(f"{worktree} has uncommitted changes")
    main = cfg.get("main_branch")
    git("fetch", "--quiet", "origin", main, cwd=worktree)
    try:
        upstream = [git("rev-parse", "--abbrev-ref", "@{upstream}", cwd=worktree)]
        git("rev-parse", "--verify", "--quiet", upstream[0], cwd=worktree)
    except AwError:
        upstream = []
    unpushed = git("rev-list", "--count", "HEAD", "--not", f"origin/{main}", *upstream, cwd=worktree)
    if unpushed != "0":
        raise AwError(f"{branch} has unpushed commits" if upstream else f"{branch} has no upstream; push it first")


def _merge_request(cfg: Config, kind: str, branch: str, pr: str | None, worktree: Path, log: list[str]) -> str:
    """Merge the given request, or the branch's open one; returns its number. Already merged is fine (a resume)."""
    root = cfg.root
    if pr is None:
        request = forge.find_open(kind, branch, worktree)
        if request is None:
            raise AwError(f"{branch} has no open merge request; open one with `aw mr create`, or pass --pr")
        pr = request.number
    if not forge.is_merged(kind, pr, root):
        forge.merge(kind, pr, cfg.get("merge_method"), root)
        log.append(f"merged {PREFIX[kind]}{pr}")
    if not forge.is_merged(kind, pr, root):
        raise AwError(f"{PREFIX[kind]}{pr} is not merged (pending checks or auto-merge?); rerun when it is")
    return pr


def _merged_by_hand(root: Path, main: str, branch: str) -> None:
    git("fetch", "--quiet", "origin", main, cwd=root)
    if subprocess.run(["git", "merge-base", "--is-ancestor", branch, f"origin/{main}"],
                      cwd=root, check=False).returncode:
        raise AwError(f"{branch} is not merged into origin/{main}; merge it first")


def _update_main(root: Path, main: str, log: list[str]) -> None:
    if git("branch", "--show-current", cwd=root) == main:
        git("pull", "--ff-only", "--quiet", "origin", main, cwd=root)
        log.append(f"updated {main}")
    else:
        log.append(f"warning: {root} is not on {main}; not pulled")


def _on_merge(cfg: Config, pr: str, final: bool, log: list[str]) -> None:
    if not cfg.values["on_merge"]:
        return
    cmd = cfg.get("on_merge", pr=pr, final=str(final).lower())
    r = subprocess.run(cmd, shell=True, cwd=cfg.root, stdout=sys.stderr, check=False)
    log.append(f"on_merge: {cmd}" if r.returncode == 0 else f"warning: on_merge exited {r.returncode}: {cmd}")


def merge(cfg: Config, meta: dict[str, Any], pr: str | None) -> list[str]:
    """Merge one part and bring the branch to main's tip; worktree, branch and issue stay."""
    root, main, branch = cfg.root, cfg.get("main_branch"), meta["branch"]
    worktree, kind = Path(meta["worktree"]), cfg.get("forge")
    if branch == main:
        raise AwError(f"on {main}: aw merge runs in a session worktree")
    _preflight(cfg, worktree, branch, ignore_inbox=True)
    head = git("rev-parse", "HEAD", cwd=worktree)
    log: list[str] = []

    if kind == "none":
        _merged_by_hand(root, main, branch)
        pr = ""
    else:
        pr = _merge_request(cfg, kind, branch, pr, worktree, log)
        if forge.head(kind, pr, root) != head:
            raise AwError(f"{PREFIX[kind]}{pr} was merged at another commit than {branch}'s head; "
                          "the commits after it would be lost. Push them into a new part first")
    _update_main(root, main, log)

    git("fetch", "--quiet", "origin", main, cwd=worktree)
    if kind == "none" or cfg.get("merge_method") == "merge":
        git("merge", "--ff-only", "--quiet", f"origin/{main}", cwd=worktree)
    else:  # squash or rebase: the branch's commits are in main under other ids, so it moves to main's tip
        git("reset", "--keep", "--quiet", f"origin/{main}", cwd=worktree)
        if git("ls-remote", "--heads", "origin", branch, cwd=root):
            git("push", "--quiet", "origin", "--delete", branch, cwd=root)
            log.append(f"deleted origin/{branch}; the next `git push -u` recreates it")
    log.append(f"{branch} is at {main}'s tip; the session goes on")

    issue = meta.get("issue")
    if issue and cfg.get("tracker") != "none":
        tracker = trackers.get(cfg)
        parts = len(forge.merged(kind, branch, root)) if kind != "none" else 0
        what = f"Part {parts} merged: {PREFIX[kind]}{pr}" if parts else f"A part of this work merged into {main}"
        try:
            tracker.comment(issue, what)
            log.append(f"commented on {tracker.ref(issue)}: {what}")
        except AwError as e:
            log.append(f"warning: issue not commented: {e}")
    _on_merge(cfg, pr, False, log)
    return log


def run(cfg: Config, meta: dict[str, Any], pr: str | None) -> list[str]:
    """The last merge, then cleanup: worktree, branch, main, issue. Nothing left to merge skips the merge."""
    root, main, branch = cfg.root, cfg.get("main_branch"), meta["branch"]
    worktree = Path(meta["worktree"])
    kind = cfg.get("forge")
    log: list[str] = []

    if backlog.home(cfg) == "tracker" and cfg.get("backlog_file") and (left := backlog.titles(cfg, worktree)):
        raise AwError(f"{cfg.get('backlog_file')} still holds {len(left)} item(s): {'; '.join(left)}. "
                      "Send each to the tracker or discard it (aw-finalize step 5), then commit")
    _preflight(cfg, worktree, branch, ignore_inbox=False)

    git("fetch", "--quiet", "origin", main, cwd=worktree)
    nothing_left = subprocess.run(["git", "diff", "--quiet", f"origin/{main}", "HEAD"],
                                  cwd=worktree, check=False).returncode == 0
    if nothing_left:
        log.append(f"nothing left to merge: {branch} has no changes against {main}")
    elif kind == "none":
        _merged_by_hand(root, main, branch)
    else:
        pr = _merge_request(cfg, kind, branch, pr, worktree, log)

    issue = meta.get("issue")
    if issue and cfg.get("sync_issue_status"):
        try:
            tracker = trackers.get(cfg)
            if nothing_left and not tracker.has_states() and cfg.get("tracker") != "none":
                log.append(tracker.set_status(issue, "done"))  # no closing keyword merged; close it here
            log += tracker.advance(issue, "done")
        except AwError as e:
            log.append(f"warning: issue status not updated: {e}")

    git("worktree", "remove", str(worktree), cwd=root)
    log.append(f"removed {worktree}")
    _update_main(root, main, log)
    if not nothing_left:
        _on_merge(cfg, pr or "", True, log)
    # Squash and rebase merges leave the branch unmerged in git's view; the forge confirmed it.
    git("branch", "-D", branch, cwd=root)
    log.append(f"deleted branch {branch}")
    if git("ls-remote", "--heads", "origin", branch, cwd=root):
        git("push", "--quiet", "origin", "--delete", branch, cwd=root)
        log.append(f"deleted origin/{branch}")
    git("remote", "prune", "origin", cwd=root)
    return log
