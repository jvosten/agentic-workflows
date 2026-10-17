"""aw verify, aw merge and aw finish: the deterministic end of a session part, and of the session.

aw merge   one merge of a multi-merge session: the branch catches up with main and the session goes on
aw finish  the last merge (or none, when every change already went through aw merge), then cleanup
aw abandon end the session without a merge: the issue goes back, worktree and branch go
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from aw import backlog, forge, rollup, session, trackers
from aw.config import STDERR_FD, AwError, Config, fast_forward, git
from aw.trackers import canonical

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
    dirty = [
        line
        for line in git("status", "--porcelain", cwd=worktree).splitlines()
        if not (inbox and line == f"?? {inbox}")
    ]
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
    """Merge the given request, or the branch's open one; returns its number. Already merged is fine (a resume).

    The request has to be at the branch's head, merged or not: a foreign request is never merged, and a merge that
    misses later commits never leads to cleanup.
    """
    root = cfg.root
    if pr is None:
        request = forge.find_open(kind, branch, worktree)
        if request is None:
            raise AwError(f"{branch} has no open merge request; open one with `aw mr create`, or pass --pr")
        pr = request.number
    merged = forge.is_merged(kind, pr, root)
    _require_head(kind, pr, branch, merged, worktree)
    if not merged:
        forge.merge(kind, pr, cfg.get("merge_method"), root)
        log.append(f"merged {PREFIX[kind]}{pr}")
    if not forge.is_merged(kind, pr, root):
        raise AwError(f"{PREFIX[kind]}{pr} is not merged (pending checks or auto-merge?); rerun when it is")
    return pr


def _require_head(kind: str, pr: str, branch: str, merged: bool, worktree: Path) -> None:
    """Refuse a request that is not at the branch's head: it is another branch's, or commits came after it."""
    at = forge.head(kind, pr, worktree)
    if at == git("rev-parse", "HEAD", cwd=worktree):
        return
    ref = f"{PREFIX[kind]}{pr}"
    if not merged:
        raise AwError(
            f"{ref} is at another commit than {branch}'s head; it is not this branch's merge request, "
            "or one of them moved since. Nothing merged"
        )
    try:
        lost = git("log", "--format=%h %s", f"{at}..HEAD", cwd=worktree).splitlines()
    except AwError:  # the merged commit is not in this clone
        lost = []
    raise AwError(
        f"{ref} was merged at another commit than {branch}'s head; the commits after it would be lost"
        + (f": {'; '.join(lost)}" if lost else "")
        + ". Push them into a new part first"
    )


def _merged_outside(kind: str, branch: str, worktree: Path) -> str | None:
    """The merged request from branch whose head is the branch's head: someone merged it without aw."""
    head = git("rev-parse", "HEAD", cwd=worktree)
    hits = [m.number for m in forge.merged(kind, branch, worktree) if m.head == head]
    return hits[-1] if hits else None


def _merged_by_hand(root: Path, main: str, branch: str) -> None:
    git("fetch", "--quiet", "origin", main, cwd=root)
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", branch, f"origin/{main}"], cwd=root, check=False
    ).returncode:
        raise AwError(f"{branch} is not merged into origin/{main}; merge it first")


def _refuse_stacked(meta: dict[str, Any]) -> None:
    if base := meta.get("base"):
        raise AwError(f"{meta['branch']} is stacked on {base}; run `aw restack` once {base} has merged")


def _warn_stacked(root: Path, branch: str, log: list[str]) -> None:
    """Sessions in other worktrees stacked on branch have to restack."""
    for line in git("worktree", "list", "--porcelain", cwd=root).splitlines():
        if not line.startswith("worktree "):
            continue
        try:
            other = session.read(line.removeprefix("worktree "))
        except session.NoSession:
            continue
        except AwError as e:
            log.append(f"warning: cannot tell whether a session is stacked on {branch}: {e}")
            continue
        if other.get("base") == branch:
            log.append(f"warning: {other['branch']} is stacked on {branch}; run `aw restack` in {other['worktree']}")


def _update_main(root: Path, main: str, log: list[str]) -> None:
    try:
        log.append(fast_forward(root, main))
    except AwError as e:  # the merge happened; a stale local main is for the user to sort out
        log.append(f"warning: {main} not updated: {e}")


def _on_merge(cfg: Config, meta: dict[str, Any], pr: str, final: bool, log: list[str]) -> None:
    if not cfg.values["on_merge"]:
        return
    cmd = cfg.command(
        "on_merge",
        pr=pr,
        final=str(final).lower(),
        issue=meta.get("issue") or "",
        slug=meta.get("slug", ""),
        type=meta.get("type", ""),
        date=date.today().strftime("%Y%m%d"),
    )
    r = subprocess.run(cmd, shell=True, cwd=cfg.root, stdout=STDERR_FD, check=False)  # noqa: S602 - hooks are shell commands the user configured
    log.append(f"on_merge: {cmd}" if r.returncode == 0 else f"warning: on_merge exited {r.returncode}: {cmd}")


def _ignored(cfg: Config) -> list[str]:
    """The trusted keys the branch sets and aw did not take: the primary checkout's values decide."""
    return [f"ignored from the branch: {', '.join(cfg.ignored)}"] if cfg.ignored else []


def merge(cfg: Config, meta: dict[str, Any], pr: str | None) -> list[str]:
    """Merge one part and bring the branch to main's tip; worktree, branch and issue stay."""
    cfg.on_host("aw merge")
    root, main, branch = cfg.root, cfg.get("main_branch"), meta["branch"]
    worktree, kind = Path(meta["worktree"]), cfg.get("forge")
    if branch == main:
        raise AwError(f"on {main}: aw merge runs in a session worktree")
    _refuse_stacked(meta)
    _preflight(cfg, worktree, branch, ignore_inbox=True)
    log = _ignored(cfg)

    if kind == "none":
        _merged_by_hand(root, main, branch)
        pr = ""
    else:
        pr = _merge_request(cfg, kind, branch, pr, worktree, log)
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
    _warn_stacked(root, branch, log)

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
    _on_merge(cfg, meta, pr, False, log)
    return log


def run(cfg: Config, meta: dict[str, Any], pr: str | None, close_parent: bool = False) -> list[str]:
    """The last merge, then cleanup: worktree, branch, main, issue. Nothing left to merge skips the merge.

    close_parent: also close the issue's parent story, when nothing else keeps it open (rollup.close).
    """
    cfg.on_host("aw finish")
    root, main, branch = cfg.root, cfg.get("main_branch"), meta["branch"]
    if close_parent and not meta.get("issue"):
        raise AwError("--close-parent needs a session with an issue")
    worktree = Path(meta["worktree"])
    kind = cfg.get("forge")
    log = _ignored(cfg)
    _refuse_stacked(meta)

    if backlog.home(cfg) == "tracker" and cfg.get("backlog_file") and (left := backlog.titles(cfg, worktree)):
        raise AwError(
            f"{cfg.get('backlog_file')} still holds {len(left)} item(s): {'; '.join(left)}. "
            "Send each to the tracker or discard it (aw-finalize step 5), then commit"
        )
    _preflight(cfg, worktree, branch, ignore_inbox=False)

    git("fetch", "--quiet", "origin", main, cwd=worktree)
    # Commits main lacks, not differing files: once main moved on after the last part, the files differ although
    # nothing of this branch is left. A squash or rebase merge outside aw leaves commits that main holds under other
    # ids, so that case is recognised first, by the merged request's head.
    nothing_left = git("rev-list", "--count", f"origin/{main}..HEAD", cwd=worktree) == "0"
    if kind != "none" and pr is None and (outside := _merged_outside(kind, branch, worktree)):
        # Merged on the forge by hand: the last merge happened, so it is handled as one (on_merge runs).
        nothing_left, pr = False, outside
        log.append(f"{PREFIX[kind]}{pr} was merged outside aw")
    elif nothing_left:
        log.append(f"nothing left to merge: {branch} has no changes against {main}")
    elif kind == "none":
        _merged_by_hand(root, main, branch)
    else:
        pr = _merge_request(cfg, kind, branch, pr, worktree, log)

    issue = meta.get("issue")
    tracker = trackers.get(cfg)
    if issue and cfg.get("sync_issue_status"):
        try:
            if nothing_left and not tracker.has_states() and cfg.get("tracker") != "none":
                log.append(tracker.set_status(issue, "done"))  # no closing keyword merged; close it here
            log += tracker.advance(issue, "done")
        except AwError as e:
            log.append(f"warning: issue status not updated: {e}")
    if issue and (close_parent or cfg.get("sync_issue_status")):
        try:  # the story closes only when asked: work never cut into a subtask is the user's call
            if close_parent:
                log += rollup.close(cfg, tracker, issue)
            else:
                result = rollup.check(cfg, tracker, issue)
                hint = rollup.report(tracker, issue, result)
                if isinstance(result, rollup.CanClose):
                    log.append(f"{hint}; `aw issue rollup {issue} --close` closes it")
                elif isinstance(result, rollup.Unknown):
                    log.append(f"warning: {hint}")
                elif isinstance(result, rollup.Blocked):
                    log.append(hint)
        except AwError as e:
            log.append(f"warning: parent story: {e}")

    git("worktree", "remove", str(worktree), cwd=root)
    log.append(f"removed {worktree}")
    _update_main(root, main, log)
    if not nothing_left:
        _on_merge(cfg, meta, pr or "", True, log)
    # Squash and rebase merges leave the branch unmerged in git's view; the forge confirmed it.
    git("branch", "-D", branch, cwd=root)
    log.append(f"deleted branch {branch}")
    if git("ls-remote", "--heads", "origin", branch, cwd=root):
        git("push", "--quiet", "origin", "--delete", branch, cwd=root)
        log.append(f"deleted origin/{branch}")
    git("remote", "prune", "origin", cwd=root)
    _warn_stacked(root, branch, log)
    return log


def abandon(cfg: Config, meta: dict[str, Any], discard: bool = False, status: str = "backlog") -> list[str]:
    """End a session without merging: the issue goes back to status, the worktree and branch are removed.

    Work that exists only on this branch (uncommitted changes, commits main lacks, locally or on origin) is
    never dropped silently: it refuses unless discard. An open merge request is never left dangling.
    """
    root, main, branch = cfg.root, cfg.get("main_branch"), meta["branch"]
    worktree, kind = Path(meta["worktree"]), cfg.get("forge")
    git("fetch", "--quiet", "origin", main, cwd=worktree)
    remote = bool(git("ls-remote", "--heads", "origin", branch, cwd=root))
    if remote:
        git("fetch", "--quiet", "origin", branch, cwd=worktree)
    heads = ["HEAD", *([f"origin/{branch}"] if remote else [])]
    ahead = int(git("rev-list", "--count", *heads, "--not", f"origin/{main}", cwd=worktree))
    dirty = bool(git("status", "--porcelain", cwd=worktree))
    if (ahead or dirty) and not discard:
        what = " and ".join(
            filter(None, (f"{ahead} commit(s) {main} lacks" if ahead else "", "uncommitted changes" if dirty else ""))
        )
        raise AwError(f"{branch} has {what}; pass --discard to drop them, or keep the session")
    if kind != "none" and (request := forge.find_open(kind, branch, worktree)):
        raise AwError(f"{branch} has an open merge request {PREFIX[kind]}{request.number}; close it first")

    log: list[str] = []
    if kind != "none" and (parts := forge.merged(kind, branch, worktree)):
        log.append(f"note: {len(parts)} part(s) of this session are already in {main}")
    issue = meta.get("issue")
    tracker = trackers.get(cfg)
    if issue and cfg.get("sync_issue_status") and tracker.has_states():
        try:  # the start moved it to in progress; anything else someone chose, so it stays
            current = tracker.current_status(issue)
            if current is None or canonical(cfg, current) != "in_progress":
                log.append(
                    f"{tracker.ref(issue)} stays at {current or 'no status'}: only an issue in progress goes back"
                )
            else:
                log.append(tracker.set_status(issue, status))
                if hook := trackers.status_hook(cfg, issue, status):
                    log.append(hook)
        except AwError as e:
            log.append(f"warning: issue status not updated: {e}")

    if remote:
        git("push", "--quiet", "origin", "--delete", branch, cwd=root)
        log.append(f"deleted origin/{branch}")
    git("worktree", "remove", *(["--force"] if dirty else []), str(worktree), cwd=root)
    log.append(f"removed {worktree}")
    git("branch", "-D", branch, cwd=root)
    log.append(f"deleted branch {branch}")
    return log
