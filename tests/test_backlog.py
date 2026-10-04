from aw import cli

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
    assert cli.main(["backlog", "add", "--title", "[MEDIUM] Third item",
                     "--body-file", body(tmp_path, "Context: three.\n")]) == 0
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
    assert cli.main(["backlog", "add", "--title", "[LOW] Third item", "--body-file", body(tmp_path, "Context: three.\n")]) == 0
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
