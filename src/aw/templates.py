"""Document templates: bundled defaults, overridable per project."""

from __future__ import annotations

from importlib import resources

from aw.config import AwError, Config

NAMES = ("story", "subtask", "plan")


def read(cfg: Config, name: str) -> str:
    if name not in NAMES:
        raise AwError(f"unknown template: {name} (known: {', '.join(NAMES)})")
    override = cfg.get("templates").get(name)
    if override:
        path = cfg.checkout / cfg.expand(override)
        if not path.is_file():
            raise AwError(f"templates.{name}: {path} not found")
        return path.read_text()
    return resources.files("aw").joinpath(f"templates/{name}.md").read_text()
