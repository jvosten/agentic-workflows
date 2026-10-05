"""aw verify and aw finish: the deterministic end of a session."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from aw import backlog, forge, trackers
from aw.config import AwError, Config, git


def verify(cfg: Config) -> int:
    cmd = cfg.get("verify_cmd")
    if not cmd:
        print("verify_cmd is not set; nothing to run", file=sys.stderr)
        return 0
    args = ["direnv", "exec", str(cfg.checkout), "sh", "-c", cmd] if cfg.get("direnv") else ["sh", "-c", cmd]
    return subprocess.run(args, cwd=cfg.checkout, check=False).returncode


def run(cfg: Config, meta: dict[str, Any], pr: str | None) -> list[str]:
    """Merge (if a forge is set), then remove the worktree, update main, delete the branch."""
    root, main, branch = cfg.root, cfg.get("main_branch"), meta["branch"]
    worktree = Path(meta["worktree"])
    kind = cfg.get("forge")
    log: list[str] = []

    if backlog.home(cfg) == "tracker" and cfg.get("backlog_file") and (left := backlog.titles(cfg, worktree)):
        raise AwError(f"{cfg.get('backlog_file')} still holds {len(left)} item(s): {'; '.join(left)}. "
                      "Send each to the tracker or discard it (aw-finalize step 5), then commit")
    if git("status", "--porcelain", cwd=worktree):
        raise AwError(f"{worktree} has uncommitted changes")
    try:
        unpushed = git("rev-list", "--count", f"@{{upstream}}..{branch}", cwd=worktree)
    except AwError:
        raise AwError(f"{branch} has no upstream; push it first") from None
    if unpushed != "0":
        raise AwError(f"{branch} has unpushed commits")

    if kind == "none":
        git("fetch", "--quiet", "origin", main, cwd=root)
        if subprocess.run(["git", "merge-base", "--is-ancestor", branch, f"origin/{main}"],
                          cwd=root, check=False).returncode:
            raise AwError(f"{branch} is not merged into origin/{main}; merge it first")
    else:
        if not pr:
            raise AwError(f"forge = {kind}: pass --pr N")
        if not forge.is_merged(kind, pr, root):
            forge.merge(kind, pr, cfg.get("merge_method"), root)
            log.append(f"merged {pr}")
        if not forge.is_merged(kind, pr, root):
            raise AwError(f"{pr} is not merged (pending checks or auto-merge?); rerun when it is")

    issue = meta.get("issue")
    if issue and cfg.get("sync_issue_status"):
        try:
            log += trackers.get(cfg).advance(issue, "done")
        except AwError as e:
            log.append(f"warning: issue status not updated: {e}")

    git("worktree", "remove", str(worktree), cwd=root)
    log.append(f"removed {worktree}")
    if git("branch", "--show-current", cwd=root) == main:
        git("pull", "--ff-only", "--quiet", "origin", main, cwd=root)
        log.append(f"updated {main}")
    else:
        log.append(f"warning: {root} is not on {main}; not pulled")
    # Squash and rebase merges leave the branch unmerged in git's view; the forge confirmed it.
    git("branch", "-D", branch, cwd=root)
    log.append(f"deleted branch {branch}")
    if git("ls-remote", "--heads", "origin", branch, cwd=root):
        git("push", "--quiet", "origin", "--delete", branch, cwd=root)
        log.append(f"deleted origin/{branch}")
    git("remote", "prune", "origin", cwd=root)
    return log
