"""aw doctor: check the installation and the current project's configuration."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from aw import install, memory, plan, templates, trackers, ui, update
from aw.config import PROJECT_FILE, AwError, Config, git, load, load_schema, repo_root
from aw.trackers.github import GitHub
from aw.trackers.jira import CREDENTIALS, Jira

# A quoted string with a placeholder in it, "text {x}": the migration only rewrites a placeholder quoted alone.
QUOTED_TEXT_WITH_PLACEHOLDER = re.compile(r"""(["'])[^"']*\{\w+\}[^"']*\1""")

NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TRACKER_CLI = {"github": "gh", "gitlab": "glab"}

Result = tuple[str, str]  # (ok | info | warn | fail, message); info is advice, not a problem
WORKFLOW_ADVICE = {
    "Item closed": "issues closed outside aw finish stay out of Done",
    "Item added to project": "cards added by hand get no status; aw issue create sets Backlog itself",
}


def raw_frontmatter(skill_md: Path) -> dict[str, str]:
    """Top-level scalar keys of a SKILL.md frontmatter block, each value as written (quotes kept)."""
    lines = skill_md.read_text().splitlines()
    if not lines or lines[0] != "---":
        return {}
    fields = {}
    for line in lines[1:]:
        if line == "---":
            break
        if m := re.match(r"^([a-z][a-z0-9-]*):\s*(.*)$", line):
            fields[m.group(1)] = m.group(2).strip()
    return fields


def frontmatter(skill_md: Path) -> dict[str, str]:
    """Top-level scalar keys of a SKILL.md frontmatter block."""
    return {key: value.strip("\"'") for key, value in raw_frontmatter(skill_md).items()}


def yaml_problem(value: str) -> str | None:
    """What a YAML parser (the agent's) does to an unquoted value that this reader takes whole."""
    if value[:1] in ("'", '"'):
        return None
    if " #" in value:
        return "' #' starts a YAML comment"
    if ": " in value:
        return "': ' is a YAML mapping"
    return None


def check_skill(skill: Path) -> list[Result]:
    raw = raw_frontmatter(skill / "SKILL.md")
    fm = frontmatter(skill / "SKILL.md")
    name, desc = fm.get("name", ""), fm.get("description", "")
    problems = [
        f"{key}: {problem} in an unquoted value; quote the value"
        for key, value in raw.items()
        if (problem := yaml_problem(value))
    ]
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
    results: list[Result] = [
        ("ok", f"{bin_link}") if bin_link.exists() else ("fail", f"{bin_link} missing; run `aw install`")
    ]
    if not shutil.which("aw"):
        results.append(("warn", "`aw` is not on your PATH; skills still work. For your shell: `uv tool update-shell`"))
    return results + check_source(update.source_clone())


def check_source(clone: Path | None) -> list[Result]:
    """An editable install runs whatever its clone has checked out, as aw in every project and as every agent's
    skills: a pull request checked out there to review it would run with the user's credentials."""
    if clone is None:
        return []
    branch, current = update.default_branch(clone), git("branch", "--show-current", cwd=clone)
    results: list[Result] = []
    if current != branch:
        results.append(
            (
                "warn",
                f"editable install: {clone} has {current or 'a detached HEAD'} checked out, not {branch}; aw and its "
                "skills run that code in every project. Check out other branches in a worktree",
            )
        )
    if git("status", "--porcelain", "--", "src", "skills", cwd=clone):
        results.append(
            (
                "warn",
                f"editable install: {clone} has uncommitted changes in src/ or skills/; aw runs them in every project",
            )
        )
    return results or [("ok", f"editable install: {clone} on {branch}")]


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
    results += [
        ("warn", f"{layer}: {key} is set by the environment only (AW_{key.upper()}); ignored")
        for layer, key in cfg.misplaced
    ]
    if cfg.ignored:
        results.append(
            (
                "info",
                f"ignored from the branch: {', '.join(cfg.ignored)}; the primary checkout's {PROJECT_FILE} decides "
                "what runs and merges on the host, the branch's values apply once it merged",
            )
        )
    for layer, note in cfg.migrated:
        fix = "`aw init` applies it" if layer == "project" else "edit that file"
        results.append(("warn", f"{layer}: pending migration {note}; {fix}"))
    untracked = [
        name
        for name in (PROJECT_FILE, ".agents/.gitignore")
        if (cfg.checkout / name).is_file()
        and subprocess.run(
            ["git", "ls-files", "--error-unmatch", name], cwd=cfg.checkout, capture_output=True, check=False
        ).returncode
    ]
    if untracked:
        results.append(
            (
                "warn",
                (
                    f"{', '.join(untracked)} not committed: session worktrees start from "
                    f"{cfg.get('main_branch')} and run aw there with defaults; "
                    "git add .agents && git commit"
                ),
            )
        )
    for hook in ("on_start", "on_issue_status", "on_merge"):
        if cfg.values[hook]:
            results.append(("ok", f"hook {hook}: {cfg.values[hook]}"))
        if QUOTED_TEXT_WITH_PLACEHOLDER.search(cfg.values[hook]):
            results.append(
                (
                    "warn",
                    f"{hook}: a placeholder inside quotes; aw quotes placeholder values itself, so the quotes "
                    "become part of the value. Move the placeholder out of the quoted text",
                )
            )

    for key, spec in cfg.schema.items():  # skills read some of these files themselves, past any check in aw
        names = cfg.get(key).values() if spec["type"] == "table" else [cfg.get(key)]
        for name in (n for n in names if n) if spec.get("path") else ():
            try:
                cfg.inside(key, cfg.checkout / name)
            except AwError as e:
                results.append(("fail", str(e)))
    results.append(
        ("ok", f"instructions_file {cfg.get('instructions_file')}")
        if (cfg.checkout / cfg.get("instructions_file")).is_file()
        else ("fail", f"instructions_file {cfg.get('instructions_file')} not found")
    )
    value = cfg.get("changelog_file")
    if value and not (cfg.checkout / value).exists():
        results.append(("warn", f"changelog_file {value} not found"))
    if cfg.get("forge") != "none":
        try:
            source = templates.source(cfg, "mr")
            shown = (
                (source.relative_to(cfg.checkout) if source.is_relative_to(cfg.checkout) else ui.home(source))
                if source
                else None
            )
            results.append(("ok", f"merge request template: {shown or 'bundled'}"))
        except AwError as e:
            results.append(("fail", str(e)))
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
            authed = (
                subprocess.run(
                    [cli, "auth", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
                ).returncode
                == 0
            )
            results.append(
                ("ok", f"{cli} authenticated")
                if authed
                else ("fail", f"{cli} not authenticated; run `{cli} auth login`")
            )
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


def check_board(cfg: Config) -> list[Result]:
    spec, field = cfg.get("github_project"), cfg.get("status_field")
    results: list[Result] = []
    scopes = _gh_scopes()
    if scopes is not None and "project" not in scopes:
        return [("fail", "gh token lacks the project scope; run `gh auth refresh -s project`")]
    tracker = trackers.get(cfg)
    if not isinstance(tracker, GitHub):
        return [("fail", "github_project needs tracker = github")]
    try:
        board = tracker.board
    except AwError as e:
        return [("fail", str(e))]
    results.append(("ok", f"board {spec} ({board['title']}), field {field}"))
    columns = {o["name"].casefold() for o in board["field"]["options"]}
    used = [s for s in trackers.STATUSES if s in ("backlog", "in_progress", "done") or s in cfg.get("status_map")]
    missing = [
        f"{s} → {trackers.status_name(cfg, s)}" for s in used if trackers.status_name(cfg, s).casefold() not in columns
    ]
    if missing:
        available = ", ".join(o["name"] for o in board["field"]["options"])
        results.append(("fail", f"board has no column for {', '.join(missing)} (columns: {available}); set status_map"))
    else:
        results.append(("ok", f"board columns for {', '.join(used)}"))
    results += _check_board_fields(cfg, tracker)
    for name in cfg.get("board_required"):
        try:
            results.append(("ok", f"board_required: field {tracker.field_options(name)[0]}"))
        except AwError as e:
            results.append(("fail", f"board_required: {e}"))
    for workflow in board.get("workflows", {}).get("nodes", []):
        if workflow["name"] in WORKFLOW_ADVICE and not workflow["enabled"]:
            results.append(("info", f"board workflow '{workflow['name']}' is off: {WORKFLOW_ADVICE[workflow['name']]}"))
    return results


def _check_board_fields(cfg: Config, tracker: GitHub) -> list[Result]:
    """Each board_fields field exists, and each label with its prefix names one of its options."""
    mapped = cfg.get("board_fields")
    if not mapped:
        return []
    try:
        labels = tracker.labels()
    except AwError as e:
        return [("fail", f"board_fields: labels unknown: {e}")]
    results: list[Result] = []
    for prefix, name in mapped.items():
        try:
            field = tracker.board_field(name)
        except AwError as e:
            results.append(("fail", f"board_fields.{prefix}: {e}"))
            continue
        options = {o["name"].casefold() for o in field["options"]}
        matching = [label for label in labels if trackers.label_values(prefix, [label]) not in ([], [""])]
        missing = [label for label in matching if label[len(prefix) :].casefold() not in options]
        available = ", ".join(o["name"] for o in field["options"])
        results += [
            ("fail", f"board field {field['name']} has no option for label {label} (options: {available})")
            for label in missing
        ]
        if not missing:
            results.append(("ok", f"board field {field['name']} for {prefix} labels ({len(matching)})"))
    return results


def check_memory(cfg: Config) -> list[Result]:
    try:
        every, vocab = memory.entries(cfg), memory.vocabulary(cfg)
    except AwError as e:
        return [("fail", f"memory: {e}")]
    if not every:
        return []
    results: list[Result] = []
    slugs = {e.slug for e in every}
    unknown = sorted({f"{e.slug} ({t})" for e in every for t in e.tags if t not in vocab})
    if unknown:
        results.append(
            (
                "fail",
                f"memory: unknown tags on {', '.join(unknown[:5])}"
                + (f" and {len(unknown) - 5} more" if len(unknown) > 5 else ""),
            )
        )
    kinds: dict[str, set[str]] = {}
    for e in every:
        kinds.setdefault(e.slug, set()).add(e.kind)
    if clashes := sorted(slug for slug, held in kinds.items() if len(held) > 1):
        results.append(("fail", f"memory: slugs used by a decision and a gotcha: {', '.join(clashes)}"))
    dangling = [e.slug for e in every if e.superseded_by and e.superseded_by not in slugs]
    if dangling:
        results.append(("fail", f"memory: superseded_by points nowhere in {', '.join(dangling)}"))
    owners: dict[str, list[str]] = {}
    for e in every:
        for alias in e.aliases:
            owners.setdefault(alias.casefold(), []).append(e.slug)
    claimed = [f"{a} ({', '.join(o)})" for a, o in owners.items() if len(o) > 1]
    if claimed:
        results.append(("fail", f"memory: aliases claimed twice: {'; '.join(claimed)}"))
    active = {k: sum(e.kind == k and e.status == "active" for e in every) for k in memory.KINDS}
    load = memory.tokens(memory.start_text(cfg, has_plan=False))
    results.append(
        (
            "ok",
            (
                f"memory: {active['gotcha']} gotchas, {active['decision']} decisions active; "
                f"session start loads ~{load} tokens (gotchas_load = {cfg.get('gotchas_load')})"
            ),
        )
    )
    return results


def check_jira(cfg: Config) -> list[Result]:
    results: list[Result] = []
    for var in CREDENTIALS:
        results.append(("ok", f"{var} is set") if os.environ.get(var) else ("fail", f"{var} is not set"))
    if not (cfg.get("jira_base_url") or os.environ.get("JIRA_BASE_URL")):
        results.append(("fail", "jira_base_url is not set"))
    if not cfg.get("jira_project"):
        results.append(("warn", "jira_project is not set; aw issue list and create need it"))
    if all(r[0] != "fail" for r in results):
        tracker = trackers.get(cfg)
        try:
            if not isinstance(tracker, Jira):
                raise AwError("the Jira checks need tracker = jira")
            tracker.request(
                "GET", "/rest/api/3/search/jql", {"jql": "created >= -1d", "maxResults": 1, "fields": "summary"}
            )
            results.append(("ok", "jira authenticated"))
        except Exception as e:
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
