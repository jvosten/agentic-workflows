"""Terminal output shared by the commands: styles, short paths, counts."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BOLD, DIM, RED, GREEN, YELLOW, CYAN = "1", "2", "31", "32", "33", "36"


def style(text: str, code: str) -> str:
    """ANSI style on a terminal; plain text when piped or with NO_COLOR."""
    if not sys.stdout.isatty() or "NO_COLOR" in os.environ:
        return text
    return f"\033[{code}m{text}\033[0m"


def home(text: str | Path) -> str:
    """Paths under the home directory as ~/..."""
    return str(text).replace(str(Path.home()), "~")


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def warn(text: str) -> None:
    print(style(f"! {text}", YELLOW))
