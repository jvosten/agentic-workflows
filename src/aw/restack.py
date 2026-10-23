"""aw restack: move a stacked session onto its base's new tip, or onto main once the base merged.

The session records the fork point, the base commit it was cut from or last restacked onto. Every restack is
`git rebase --onto <upstream> <fork point>`: only the session's own commits are replayed, whatever happened to
the base (new commits, a force-push, a squash or rebase merge into main).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aw import forge, session
from aw.config import AwError, Config, git
from aw.finish import PREFIX
from aw.ui import plural


@dataclass
class Result:
    state: str  # restacked | up_to_date | conflict | not_stacked
    branch: str = ""
    base: str = ""
    base_merged: bool = False
    upstream: str = ""
    fork_point: str = ""
    commits: int = 0
    retargeted: str = ""
    conflicts: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def summary(self) -> str:
        if self.state == "restacked":
            onto = self.upstream.removeprefix("origin/")
            merged = f" (base {self.base} merged)" if self.base_merged else ""
            moved = f"; {self.retargeted} → {onto}" if self.retargeted else ""
            verb = "would restack" if self.dry_run else "restacked"
            return f"{verb} {self.branch}: {plural(self.commits, 'commit')} onto {onto}{merged}{moved}"
        if self.state == "conflict":
            return (
                f"conflict in {', '.join(self.conflicts)}: resolve, `git add`, `git rebase --continue`, "
                "then `aw restack` again"
            )
        if self.state == "up_to_date":
            return f"{self.branch} is up to date with {self.base}"
        return "not a stacked session; nothing to restack"


def _rebase(worktree: Path, onto: str, fork_point: str) -> list[str]:
    """Rebase the session's own commits onto onto; returns the conflicting files, empty on success."""
    r = subprocess.run(
        ["git", "rebase", "--quiet", "--onto", onto, fork_point],
        cwd=worktree,
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode == 0:
        return []
    return git("diff", "--name-only", "--diff-filter=U", cwd=worktree).splitlines() or ["(see git status)"]


def _rebasing(worktree: Path) -> bool:
    return any(
        (worktree / git("rev-parse", "--git-path", d, cwd=worktree)).exists() for d in ("rebase-merge", "rebase-apply")
    )


def _contains(worktree: Path, commit: str) -> bool:
    return (
        subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=worktree, check=False).returncode
        == 0
    )


def _base_merged(kind: str, base: str, cwd: Path) -> bool:
    """A merged request from the base and none open: the base is in main."""
    return bool(forge.merged(kind, base, cwd)) and forge.find_open(kind, base, cwd) is None


def _retarget(kind: str, branch: str, main: str, cwd: Path) -> str:
    """Point the open request at main when the forge did not; returns its number when it moved."""
    request = forge.find_open(kind, branch, cwd)
    if request is None or forge.target(kind, request.number, cwd) == main:
        return ""
    forge.retarget(kind, request.number, main, cwd)
    return request.number


def run(cfg: Config, meta: dict[str, Any], dry_run: bool = False) -> Result:
    """Restack the session; result.log holds one line per action taken."""
    base = meta.get("base")
    if not base:
        return Result("not_stacked")
    worktree, fork_point = Path(meta["worktree"]), meta["fork_point"]
    if _rebasing(worktree):
        raise AwError("rebase in progress: resolve the conflicts, `git rebase --continue`, then `aw restack` again")
    branch, pending = meta["branch"], meta.get("restack_onto", "")
    recovered = bool(pending) and _contains(worktree, pending)
    if not recovered and not _contains(worktree, fork_point):
        raise AwError(
            f"fork point {fork_point[:12]} is not in {branch}; set fork_point in the session to the "
            "base commit the branch builds on"
        )
    main, kind = cfg.get("main_branch"), cfg.get("forge")
    merged = _base_merged(kind, base, worktree)
    target = main if merged else base
    git("fetch", "--quiet", "origin", target, cwd=worktree)
    upstream = f"origin/{target}"
    onto = git("rev-parse", upstream, cwd=worktree)
    result = Result("restacked", branch, base, merged, upstream, fork_point, dry_run=dry_run)
    log = result.log
    if merged:
        log.append(f"base {base} merged into {main}")
    if recovered and pending == onto:
        result.commits = int(git("rev-list", "--count", f"{onto}..HEAD", cwd=worktree))
        if dry_run:
            log.insert(0, f"DRY RUN: finish restack onto {upstream} ({plural(result.commits, 'commit')})")
            return result
    elif onto == fork_point and not merged and not recovered:
        result.state = "up_to_date"
        return result
    else:
        if recovered:
            fork_point = pending
        result.commits = int(git("rev-list", "--count", f"{fork_point}..HEAD", cwd=worktree))
        if dry_run:
            log.insert(
                0, f"DRY RUN: git rebase --onto {upstream} {fork_point[:12]} ({plural(result.commits, 'commit')})"
            )
            return result
        session.update(worktree, fork_point=fork_point, restack_onto=onto)
        if conflicts := _rebase(worktree, onto, fork_point):
            result.state, result.conflicts = "conflict", conflicts
            log.append(f"rebase onto {upstream} stopped; left in progress")
            return result
        log.append(f"rebased {plural(result.commits, 'commit')} onto {upstream} ({onto[:12]})")
    git("push", "--quiet", "--force-with-lease", "origin", branch, cwd=worktree)
    log.append(f"pushed {branch} (--force-with-lease)")
    if merged and (number := _retarget(kind, branch, main, worktree)):
        result.retargeted = f"{PREFIX[kind]}{number}"
        log.append(f"retargeted {result.retargeted} to {main}")
    session.update(worktree, fork_point=onto, restack_onto="", **({"base": ""} if merged else {}))
    result.fork_point = onto
    if merged:
        log.append(f"session base cleared; it now targets {main}")
    return result
