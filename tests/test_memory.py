from aw import cli


def body(tmp_path, text):
    path = tmp_path / "body.md"
    path.write_text(text)
    return str(path)


def test_memory_add_writes_a_decision_entry(repo, tmp_path):
    assert cli.main(["memory", "add", "decision", "--title", "Plans live in git", "--ref", "PROJ-12",
                     "--body-file", body(tmp_path, "Tracker holds tickets only.\n")]) == 0
    text = (repo / ".agents/memory/decisions.md").read_text()
    assert "# Decisions" in text
    assert "## Plans live in git" in text
    assert "PROJ-12" in text and "Tracker holds tickets only." in text


def test_memory_add_appends_without_touching_earlier_entries(repo, tmp_path):
    cli.main(["memory", "add", "gotcha", "--title", "First", "--body-file", body(tmp_path, "one\n")])
    cli.main(["memory", "add", "gotcha", "--title", "Second", "--body-file", body(tmp_path, "two\n")])
    text = (repo / ".agents/memory/gotchas.md").read_text()
    assert text.index("## First") < text.index("## Second")
    assert text.count("# Gotchas") == 1


def test_memory_supersede_moves_the_entry_and_keeps_the_reason(repo, tmp_path):
    cli.main(["memory", "add", "gotcha", "--title", "boto3 is pinned", "--body-file", body(tmp_path, "keep below 1.36\n")])
    cli.main(["memory", "add", "gotcha", "--title", "prek, not pre-commit", "--body-file", body(tmp_path, "use prek\n")])
    assert cli.main(["memory", "supersede", "gotcha", "--title", "boto3 is pinned",
                     "--reason", "OBS compatibility fixed upstream"]) == 0
    text = (repo / ".agents/memory/gotchas.md").read_text()
    assert "\n## boto3 is pinned" not in text
    assert text.index("## prek, not pre-commit") < text.index("## Superseded") < text.index("### boto3 is pinned")
    assert "keep below 1.36" in text and "OBS compatibility fixed upstream" in text


def test_doctor_warns_when_memory_outgrows_a_session(repo, tmp_path):
    from aw import doctor

    (repo / ".agents").mkdir(exist_ok=True)
    (repo / ".agents/aw.toml").write_text("aw_version = 1\n")
    cli.main(["memory", "add", "gotcha", "--title", "Long", "--body-file", body(tmp_path, "x\n" * 250)])
    messages = [m for level, m in doctor.check_project() if level == "warn"]
    assert any("gotchas.md" in m and "200 lines" in m for m in messages)
