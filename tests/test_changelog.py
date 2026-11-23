"""Tests for the changelog strategies: where an entry goes, whether it exists, and collect."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aw import changelog
from aw.config import git, load


def head(repo: Path) -> str:
    return git("rev-parse", "HEAD", cwd=repo)


def test_file_strategy_points_at_the_file_and_sees_a_new_entry(repo, monkeypatch):
    monkeypatch.setenv("AW_CHANGELOG", "file")
    log = changelog.open_changelog(load(), repo, head(repo))
    assert log.target() == changelog.FileTarget(repo / "CHANGELOG.md")
    assert not log.has_entry()

    (repo / "CHANGELOG.md").write_text("# Changelog\n\n- an entry\n")
    assert log.has_entry()


def test_no_changelog_has_no_target_and_never_misses_an_entry(repo):
    log = changelog.open_changelog(load(), repo, head(repo))
    assert log.target() == changelog.NoTarget()
    assert log.has_entry()
    assert log.collect(None) == ()


def at(hour: int):
    return lambda: datetime(2026, 11, 23, hour, 5, 9, tzinfo=UTC)


def test_dir_strategy_names_one_fragment_per_session_and_keeps_it(repo, monkeypatch):
    monkeypatch.setenv("AW_CHANGELOG", "dir")
    log = changelog.open_changelog(load(), repo, head(repo), now=at(10))
    fragment = repo / "changelog.d/20261123T100509Z-proj.md"
    assert log.target() == changelog.FileTarget(fragment)
    assert not log.has_entry()

    fragment.parent.mkdir()
    fragment.write_text("### Fixed\n\n- a fix\n")
    assert log.has_entry()
    later = changelog.open_changelog(load(), repo, head(repo), now=at(12))
    assert later.target() == changelog.FileTarget(fragment)


def test_dir_strategy_ignores_another_sessions_fragment(repo, monkeypatch):
    monkeypatch.setenv("AW_CHANGELOG", "dir")
    (repo / "changelog.d").mkdir()
    (repo / "changelog.d/20261122T080000Z-other-proj.md").write_text("- other\n")
    log = changelog.open_changelog(load(), repo, head(repo), now=at(10))
    assert not log.has_entry()
    assert log.target() == changelog.FileTarget(repo / "changelog.d/20261123T100509Z-proj.md")


def fragments(repo: Path, **texts: str) -> None:
    (repo / "changelog.d").mkdir(exist_ok=True)
    for name, text in texts.items():
        (repo / f"changelog.d/{name}.md").write_text(text)


def test_collect_without_heading_copies_fragments_newest_first_above_the_last_release(repo, monkeypatch):
    monkeypatch.setenv("AW_CHANGELOG", "dir")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\nIntro.\n\n## 2026-11-01 — Old\n\n- old\n")
    fragments(
        repo,
        **{
            "20261120T090000Z-first": "## 2026-11-20 — First\n\n- one\n",
            "20261121T090000Z-second": "## 2026-11-21 — Second\n\n- two\n\n",
        },
    )
    log = changelog.open_changelog(load(), repo, head(repo))

    assert log.collect(None) == ("20261121T090000Z-second.md", "20261120T090000Z-first.md")
    assert (repo / "CHANGELOG.md").read_text() == (
        "# Changelog\n\nIntro.\n\n"
        "## 2026-11-21 — Second\n\n- two\n\n"
        "## 2026-11-20 — First\n\n- one\n\n"
        "## 2026-11-01 — Old\n\n- old\n"
    )
    assert list((repo / "changelog.d").iterdir()) == []
    assert log.collect(None) == ()


def test_collect_under_a_heading_merges_the_fragments_sections_by_name(repo, monkeypatch):
    monkeypatch.setenv("AW_CHANGELOG", "dir")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0\n\n- old\n")
    fragments(
        repo,
        **{
            "20261120T090000Z-first": "### Added\n\n- a\n",
            "20261121T090000Z-second": "### Fixed\n\n- fix\n\n### Added\n\n- b\n",
        },
    )
    changelog.open_changelog(load(), repo, head(repo)).collect("## 0.2.0 — 2026-11-23")
    assert (repo / "CHANGELOG.md").read_text() == (
        "# Changelog\n\n## 0.2.0 — 2026-11-23\n\n### Fixed\n\n- fix\n\n### Added\n\n- b\n- a\n\n## 0.1.0\n\n- old\n"
    )


def test_collect_appends_to_a_file_without_a_release(repo, monkeypatch):
    monkeypatch.setenv("AW_CHANGELOG", "dir")
    fragments(repo, **{"20261120T090000Z-first": "- one\n"})
    changelog.open_changelog(load(), repo, head(repo)).collect(None)
    assert (repo / "CHANGELOG.md").read_text() == "# Changelog\n\n- one\n"


@dataclass
class FakeChangelog:
    """Stands in for a strategy run by external commands: only files, no git, no layout."""

    root: Path
    collected: list[str] = field(default_factory=list)

    def target(self) -> changelog.Target:
        return changelog.FileTarget(self.root / "entry.txt")

    def has_entry(self) -> bool:
        return (self.root / "entry.txt").exists()

    def collect(self, heading: str | None) -> tuple[str, ...]:
        if not self.has_entry():
            return ()
        self.collected.append((self.root / "entry.txt").read_text())
        (self.root / "entry.txt").unlink()
        return ("entry.txt",)


@pytest.fixture(params=["file", "dir", "fake"])
def entry_log(request, repo, monkeypatch) -> changelog.Changelog:
    if request.param == "fake":
        return FakeChangelog(repo)
    monkeypatch.setenv("AW_CHANGELOG", request.param)
    (repo / "changelog.d").mkdir()
    return changelog.open_changelog(load(), repo, head(repo))


def test_contract_an_entry_written_at_the_target_is_found(entry_log):
    target = entry_log.target()
    assert isinstance(target, changelog.FileTarget)
    assert not entry_log.has_entry()

    target.path.write_text(target.path.read_text() + "- entry\n" if target.path.exists() else "- entry\n")
    assert entry_log.has_entry()
    assert entry_log.target() == target


def test_contract_collect_twice_changes_nothing_the_second_time(entry_log):
    target = entry_log.target()
    assert isinstance(target, changelog.FileTarget)
    target.path.write_text("- entry\n")
    entry_log.collect("## next")
    assert entry_log.collect("## next") == ()


def test_doctor_warns_about_the_paths_the_strategy_uses(repo, monkeypatch):
    from aw import doctor

    def warnings() -> list[str]:
        return [text for level, text in doctor.check_config(load()) if "changelog" in text]

    (repo / "CHANGELOG.md").unlink()
    assert warnings() == []
    monkeypatch.setenv("AW_CHANGELOG", "dir")
    assert warnings() == ["changelog_file CHANGELOG.md not found", "changelog_dir changelog.d not found"]
    monkeypatch.setenv("AW_CHANGELOG", "file")
    assert warnings() == ["changelog_file CHANGELOG.md not found"]
