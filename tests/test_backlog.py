import pytest

from aw import cli, finish
from aw.config import AwError, load

ITEMS = """# Backlog

Deferred work.

## Items

### [HIGH] First item

Context: one.

### [LOW] Second item

Context: two.

## Considered and not planned

- Nothing yet.
"""


def body(tmp_path, text):
    path = tmp_path / "item.md"
    path.write_text(text)
    return str(path)


def test_backlog_add_places_the_item_with_the_others(repo, tmp_path):
    (repo / "BACKLOG.md").write_text(ITEMS)
    assert (
        cli.main(
            ["backlog", "add", "--title", "[MEDIUM] Third item", "--body-file", body(tmp_path, "Context: three.\n")]
        )
        == 0
    )
    text = (repo / "BACKLOG.md").read_text()
    assert text.index("### [LOW] Second item") < text.index("### [MEDIUM] Third item")
    assert text.index("### [MEDIUM] Third item") < text.index("## Considered and not planned")
    assert "Context: three." in text


def test_backlog_pop_removes_one_item_only(repo):
    (repo / "BACKLOG.md").write_text(ITEMS)
    assert cli.main(["backlog", "pop", "--title", "[LOW] Second item"]) == 0
    text = (repo / "BACKLOG.md").read_text()
    assert "Second item" not in text and "Context: two." not in text
    assert "### [HIGH] First item" in text and "Context: one." in text
    assert text.rstrip().endswith("- Nothing yet.")


def test_backlog_add_stays_above_the_rule_that_closes_the_items(repo, tmp_path):
    (repo / "BACKLOG.md").write_text(ITEMS.replace("\n## Considered", "\n---\n\n## Considered"))
    assert (
        cli.main(["backlog", "add", "--title", "[LOW] Third item", "--body-file", body(tmp_path, "Context: three.\n")])
        == 0
    )
    text = (repo / "BACKLOG.md").read_text()
    assert "Context: two.\n\n### [LOW] Third item\n\nContext: three.\n\n---\n\n## Considered" in text


FLAT = """# Backlog

## First item

Context: one.

---

## Second item

Context: two.
"""


def test_backlog_handles_a_flat_file_with_separators(repo, tmp_path):
    (repo / "BACKLOG.md").write_text(FLAT)
    cli.main(["backlog", "add", "--title", "Third item", "--body-file", body(tmp_path, "Context: three.\n")])
    assert cli.main(["backlog", "pop", "--title", "First item"]) == 0
    text = (repo / "BACKLOG.md").read_text()
    assert "First item" not in text and "Context: one." not in text
    assert text.index("## Second item") < text.index("## Third item")
    assert not text.lstrip("# Backlog\n").startswith("---")
    assert "\n\n\n" not in text


def test_inbox_lists_items_and_disappears_when_emptied(repo, tmp_path, capsys):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('tracker = "github"\nbacklog_home = "tracker"\n')
    for title in ("Retry uploads", "Drop old flag"):
        assert (
            cli.main(["backlog", "add", "--title", title, "--body-file", body(tmp_path, "Noted mid-session.\n")]) == 0
        )
    capsys.readouterr()
    assert cli.main(["backlog", "list"]) == 0
    assert capsys.readouterr().out == "Retry uploads\nDrop old flag\n"
    assert cli.main(["backlog", "pop", "--title", "Retry uploads"]) == 0
    assert (repo / "BACKLOG.md").is_file()
    assert cli.main(["backlog", "pop", "--title", "Drop old flag"]) == 0
    assert capsys.readouterr().out.splitlines()[-1].endswith("no items left, file deleted")
    assert not (repo / "BACKLOG.md").exists()
    assert cli.main(["backlog", "list"]) == 0
    assert capsys.readouterr().out == "no items\n"


def test_a_file_backlog_stays_when_emptied(repo):
    (repo / "BACKLOG.md").write_text(FLAT)
    for title in ("First item", "Second item"):
        assert cli.main(["backlog", "pop", "--title", title]) == 0
    assert (repo / "BACKLOG.md").is_file()


def test_finish_refuses_while_the_inbox_holds_items(repo, tmp_path):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('tracker = "jira"\nbacklog_home = "tracker"\n')
    (repo / "BACKLOG.md").write_text("# Backlog\n\n## Retry uploads\n\nx\n")
    meta = {"branch": "main", "worktree": str(repo)}
    with pytest.raises(AwError, match=r"BACKLOG\.md still holds 1 item\(s\): Retry uploads"):
        finish.run(load(), meta, None)
    (repo / ".agents/aw.toml").write_text('tracker = "jira"\nbacklog_home = "file"\n')
    with pytest.raises(AwError, match="uncommitted changes"):
        finish.run(load(), meta, None)
