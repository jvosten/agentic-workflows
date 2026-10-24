"""Document templates: bundled defaults, overridable per project.

The merge request template has one more source between the two: the forge's own template file.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from aw.config import AwError, Config

NAMES = ("story", "subtask", "plan", "mr")
GITHUB_DEFAULTS = (
    ".github/pull_request_template.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "pull_request_template.md",
    "docs/pull_request_template.md",
)


def _find(directory: Path, name: str) -> Path | None:
    """<name>.md in directory, case-insensitively."""
    if not directory.is_dir():
        return None
    wanted = f"{name}.md".casefold()
    return next((p for p in sorted(directory.iterdir()) if p.name.casefold() == wanted), None)


def forge_template(cfg: Config) -> Path | None:
    """The forge's own merge request template: the one mr_template names, else the forge's default file.

    A named template that does not exist is an error, not a silent fallback.
    """
    root, kind, named = cfg.checkout, cfg.get("forge"), cfg.get("mr_template")
    if kind == "gitlab":
        directory = root / ".gitlab/merge_request_templates"
        found = _find(directory, named or "Default")
        if named and found is None:
            available = ", ".join(sorted(p.stem for p in directory.glob("*.md"))) or "none"
            raise AwError(
                f"mr_template {named!r}: no {directory.relative_to(root)}/{named}.md (available: {available})"
            )
        return found
    if kind == "github":
        if named:
            directory = root / ".github/PULL_REQUEST_TEMPLATE"
            found = _find(directory, named)
            if found is None:
                raise AwError(f"mr_template {named!r}: no .github/PULL_REQUEST_TEMPLATE/{named}.md")
            return found
        return next((root / p for p in GITHUB_DEFAULTS if (root / p).is_file()), None)
    return None


def source(cfg: Config, name: str) -> Path | None:
    """Where the template comes from; None for the bundled default."""
    if name not in NAMES:
        raise AwError(f"unknown template: {name} (known: {', '.join(NAMES)})")
    override = cfg.get("templates").get(name)
    if override:
        path = cfg.inside("templates", cfg.checkout / cfg.expand(override))
        if not path.is_file():
            raise AwError(f"templates.{name}: {path} not found")
        return path
    return forge_template(cfg) if name == "mr" else None


def read(cfg: Config, name: str) -> str:
    path = source(cfg, name)
    if path is not None:
        return path.read_text()
    return resources.files("aw").joinpath(f"templates/{name}.md").read_text()
