from aw import cli, trackers
from aw.trackers.jira import Jira

def project(repo, extra=""):
    (repo / ".agents").mkdir(exist_ok=True)
    (repo / ".agents/aw.toml").write_text('tracker = "jira"\njira_project = "PROJ"\n' + extra)


def test_template_prints_bundled_story(repo, capsys):
    assert cli.main(["template", "story"]) == 0
    out = capsys.readouterr().out
    assert "As a " in out and "## Acceptance criteria" in out


def test_template_project_override_wins(repo, capsys):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('templates = { story = "docs/story.md" }\n')
    (repo / "docs").mkdir()
    (repo / "docs/story.md").write_text("ours\n")
    assert cli.main(["template", "story"]) == 0
    assert capsys.readouterr().out == "ours\n"


def test_template_subtask_is_a_thin_ticket(repo, capsys):
    assert cli.main(["template", "subtask"]) == 0
    out = capsys.readouterr().out
    assert "## What to build" in out and "## Acceptance criteria" in out and "## Blocked by" in out


def test_template_plan_has_sections_and_grilling_record(repo, capsys):
    assert cli.main(["template", "plan"]) == 0
    out = capsys.readouterr().out
    for heading in ("## Summary", "## Decisions from grilling", "### S1", "**Subtask:**", "## Open questions"):
        assert heading in out


def test_plan_path_finds_the_plan_of_a_story(repo, capsys):
    project(repo, 'plan_dir = "docs/planning"\n')
    (repo / "docs/planning/epic-1").mkdir(parents=True)
    plan = repo / "docs/planning/epic-1/PROJ-12-retry-failed-runs.md"
    plan.write_text("# plan\n")
    assert cli.main(["plan", "path", "proj-12"]) == 0
    assert capsys.readouterr().out.strip() == str(plan)


def test_plan_path_composes_the_file_to_create(repo, capsys):
    project(repo, 'plan_dir = "docs/planning"\n')
    assert cli.main(["plan", "path", "proj-12", "--slug", "retry-failed-runs"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == str(repo / "docs/planning/PROJ-12-retry-failed-runs.md")


def test_plan_path_of_a_subtask_resolves_through_its_parent(repo, capsys, monkeypatch):
    project(repo, 'plan_dir = "docs/planning"\n')
    (repo / "docs/planning").mkdir(parents=True)
    plan = repo / "docs/planning/PROJ-12-retry-failed-runs.md"
    plan.write_text("# plan\n")
    monkeypatch.setattr(Jira, "parent", lambda self, i: trackers.Row("PROJ-12", link="native"))
    assert cli.main(["plan", "path", "proj-13"]) == 0
    assert capsys.readouterr().out.strip() == str(plan)


def test_template_reports_a_missing_override(repo, capsys):
    project(repo, 'templates = { plan = "docs/plan.md" }\n')
    assert cli.main(["template", "plan"]) == 1
    assert "templates.plan" in capsys.readouterr().err


def test_plan_state_reports_plan_and_subtasks(repo, capsys, monkeypatch):
    project(repo, 'plan_dir = "docs/planning"\n')
    (repo / "docs/planning").mkdir(parents=True)
    plan = repo / "docs/planning/PROJ-12-retry-failed-runs.md"
    plan.write_text("# plan\n")
    monkeypatch.setattr(Jira, "children", lambda self, i: [trackers.Row("PROJ-13"), trackers.Row("PROJ-14")])
    assert cli.main(["plan", "state", "proj-12"]) == 0
    assert capsys.readouterr().out == f"issue=PROJ-12\nplan={plan}\nsubtasks=PROJ-13 PROJ-14\n"
