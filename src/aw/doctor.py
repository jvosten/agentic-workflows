"""aw doctor: check the installation and the current project's configuration."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from aw import install, plan, trackers
from aw.config import PROJECT_FILE, AwError, Config, load, load_schema, repo_root

NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TRACKER_CLI = {"github": "gh", "gitlab": "glab"}
MEMORY_LIMIT = 200

Result = tuple[str, str]  # (ok | info | warn | fail, message); info is advice, not a problem
WORKFLOW_ADVICE = {
    "Item closed": "issues closed outside aw finish stay out of Done",
    "Item added to project": "cards added by hand get no status; aw issue create sets Backlog itself",
}


def frontmatter(skill_md: Path) -> dict[str, str]:
    """Top-level scalar keys of a SKILL.md frontmatter block."""
    lines = skill_md.read_text().splitlines()
    if not lines or lines[0] != "---":
        return {}
    fields = {}
    for line in lines[1:]:
        if line == "---":
            break
        if m := re.match(r"^([a-z][a-z0-9-]*):\s*(.*)$", line):
            fields[m.group(1)] = m.group(2).strip().strip("\"'")
    return fields


def check_skill(skill: Path) -> list[Result]:
    fm = frontmatter(skill / "SKILL.md")
    name, desc = fm.get("name", ""), fm.get("description", "")
    problems = []
    if name != skill.name:
        problems.append(f"name {name!r} does not match directory")
    if not NAME.match(name) or len(name) > 64:
        problems.append("name must be 1-64 chars of a-z, 0-9, single hyphens")
    if not 1 <= len(desc) <= 1024:
        problems.append("description must be 1-1024 chars")
    if problems:
        return [("fail", f"skill {skill.name}: {p}") for p in problems]
    return [("ok", f"skill {skill.name}: frontmatter valid")]


def check_cli() -> list[Result]:
    bin_link = install.agents_home() / "bin/aw"
    results: list[Result] = [("ok", f"{bin_link}") if bin_link.exists()
                             else ("fail", f"{bin_link} missing; run `aw install`")]
    if not shutil.which("aw"):
        results.append(("warn", "`aw` is not on your PATH; skills still work. For your shell: `uv tool update-shell`"))
    return results


def check_skills() -> list[Result]:
    results: list[Result] = []
    home = install.agents_home()
    for skill in install.source_skills():
        results += check_skill(skill)
        dest = home / "skills" / skill.name
        if dest.resolve() == skill.resolve():
            results.append(("ok", f"{dest}"))
        else:
            results.append(("fail", f"{dest} does not point to {skill}; run `aw install`"))
        for agent, rel in install.AGENT_DIRS.items():
            link = Path.home() / rel / skill.name
            if link.resolve() == skill.resolve():
                results.append(("ok", f"{link}"))
            else:
                results.append(("warn", f"{link} missing; run `aw install --agent {agent}` if you use {agent}"))
    return results


def _tool(name: str, why: str) -> Result:
    return ("ok", f"{name} found") if shutil.which(name) else ("fail", f"{name} not found ({why})")


def check_install() -> list[Result]:
    return check_cli() + check_skills()


def _project_config() -> tuple[Config | None, list[Result]]:
    """The project's config, or the result that ends the project checks early."""
    try:
        repo_root()
    except AwError:
        return None, [("warn", "not in a git repository; project checks skipped")]
    try:
        cfg = load()
    except AwError as e:
        return None, [("fail", str(e))]
    path = cfg.checkout / PROJECT_FILE
    if not path.is_file():
        return None, [("warn", f"{path} missing; run `aw init`")]
    return cfg, []


def check_project() -> list[Result]:
    cfg, early = _project_config()
    return early if cfg is None else check_config(cfg) + check_tools(cfg)


def check_config(cfg: Config) -> list[Result]:
    results: list[Result] = []
    current = load_schema()["version"]
    if cfg.file_version is None:
        results.append(("fail", f"{PROJECT_FILE}: aw_version missing; run `aw init`"))
    elif cfg.file_version < current:
        results.append(("warn", f"{PROJECT_FILE}: aw_version {cfg.file_version} < {current}; run `aw init`"))
    elif cfg.file_version > current:
        results.append(("fail", f"{PROJECT_FILE}: aw_version {cfg.file_version} needs a newer aw"))
    else:
        results.append(("ok", f"{PROJECT_FILE}: aw_version {current}"))
    results += [("warn", f"{layer}: unknown key {key!r}") for layer, key in cfg.unknown]

    results.append(("ok", f"instructions_file {cfg.get('instructions_file')}")
                   if (cfg.checkout / cfg.get("instructions_file")).is_file()
                   else ("fail", f"instructions_file {cfg.get('instructions_file')} not found"))
    value = cfg.get("changelog_file")
    if value and not (cfg.checkout / value).exists():
        results.append(("warn", f"changelog_file {value} not found"))
    if cfg.get("plan_scope") == "local" and not plan.ignored(cfg):
        results.append(("warn", f"plan_scope = local but {plan.directory(cfg)} is not gitignored"))
    results += check_memory(cfg)
    return results


def check_tools(cfg: Config) -> list[Result]:
    results: list[Result] = [_tool("git", "required")]
    if cfg.get("direnv"):
        results.append(_tool("direnv", "direnv = true"))
    clis = {TRACKER_CLI[cfg.get(k)]: k for k in ("forge", "tracker") if cfg.get(k) in TRACKER_CLI}
    for cli, key in clis.items():
        results.append(_tool(cli, f"{key} = {cfg.get(key)}"))
        if shutil.which(cli):
            authed = subprocess.run([cli, "auth", "status"], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, check=False).returncode == 0
            results.append(("ok", f"{cli} authenticated") if authed
                           else ("fail", f"{cli} not authenticated; run `{cli} auth login`"))
    if cfg.get("tracker") == "jira":
        results += check_jira(cfg)
    if cfg.get("tracker") == "github" and cfg.get("github_project"):
        results += check_board(cfg)
    return results


def _gh_scopes() -> list[str] | None:
    """Scopes of the gh token, None when gh does not list them (e.g. a fine-grained GH_TOKEN)."""
    r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, check=False)
    m = re.search(r"Token scopes: (.*)", r.stdout + r.stderr)
    return re.findall(r"'([^']+)'", m.group(1)) if m else None


def check_board(cfg) -> list[Result]:
    from aw import trackers

    spec, field = cfg.get("github_project"), cfg.get("status_field")
    results: list[Result] = []
    scopes = _gh_scopes()
    if scopes is not None and "project" not in scopes:
        return [("fail", "gh token lacks the project scope; run `gh auth refresh -s project`")]
    try:
        board = trackers.get(cfg).board
    except AwError as e:
        return [("fail", str(e))]
    results.append(("ok", f"board {spec} ({board['title']}), field {field}"))
    columns = {o["name"].casefold() for o in board["field"]["options"]}
    used = [s for s in trackers.STATUSES if s in ("backlog", "in_progress", "done") or s in cfg.get("status_map")]
    missing = [f"{s} → {trackers.status_name(cfg, s)}" for s in used
               if trackers.status_name(cfg, s).casefold() not in columns]
    if missing:
        available = ", ".join(o["name"] for o in board["field"]["options"])
        results.append(("fail", f"board has no column for {', '.join(missing)} (columns: {available}); set status_map"))
    else:
        results.append(("ok", f"board columns for {', '.join(used)}"))
    for workflow in board.get("workflows", {}).get("nodes", []):
        if workflow["name"] in WORKFLOW_ADVICE and not workflow["enabled"]:
            results.append(("info", f"board workflow '{workflow['name']}' is off: {WORKFLOW_ADVICE[workflow['name']]}"))
    return results


def check_memory(cfg) -> list[Result]:
    from aw import memory

    results: list[Result] = []
    for kind in memory.KINDS:
        path = memory.file(cfg, kind)
        if not path.is_file():
            continue
        lines = len(path.read_text().splitlines())
        results.append(("warn", f"{path.name}: {lines} lines, over 200 lines; retire what no longer holds")
                       if lines > MEMORY_LIMIT else ("ok", f"{path.name}: {lines} lines"))
    return results


def check_jira(cfg) -> list[Result]:
    from aw.trackers.jira import CREDENTIALS

    results: list[Result] = []
    for var in CREDENTIALS:
        results.append(("ok", f"{var} is set") if os.environ.get(var) else ("fail", f"{var} is not set"))
    if not (cfg.get("jira_base_url") or os.environ.get("JIRA_BASE_URL")):
        results.append(("fail", "jira_base_url is not set"))
    if not cfg.get("jira_project"):
        results.append(("warn", "jira_project is not set; aw issue list and create need it"))
    if all(r[0] != "fail" for r in results):
        try:
            trackers.get(cfg).request("GET", "/rest/api/3/myself")
            results.append(("ok", "jira authenticated"))
        except Exception as e:  # noqa: BLE001 - any failure is a doctor finding
            results.append(("fail", f"jira: {e}"))
    return results


def sections() -> list[tuple[str, list[Result]]]:
    """Results grouped by what they check, for display."""
    groups = [("CLI", check_cli()), (f"Skills ({len(install.source_skills())})", check_skills())]
    cfg, early = _project_config()
    if cfg is None:
        return [*groups, ("Project", early)]
    return [*groups, ("Project", check_config(cfg)), ("Tools", check_tools(cfg))]


def run() -> list[Result]:
    return [result for _, results in sections() for result in results]
