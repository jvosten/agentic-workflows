from datetime import date

from aw import cli, doctor, start_task, trackers
from aw.config import git, load
from aw.trackers.jira import Jira

TODAY = date.today().isoformat()

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


def test_plan_path_composes_the_file_to_create(repo, capsys, monkeypatch):
    project(repo, 'plan_dir = "docs/planning"\nplan_file = "{issue}-{slug}.md"\n')
    monkeypatch.setattr(Jira, "parent", lambda self, i: None)
    assert cli.main(["plan", "path", "proj-12", "--slug", "retry-failed-runs"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == str(repo / "docs/planning/PROJ-12-retry-failed-runs.md")


def test_default_plan_goes_under_its_epic_in_agents_plans(repo, capsys, monkeypatch):
    project(repo)
    monkeypatch.setattr(Jira, "parent", lambda self, i: trackers.Row("PROJ-1", "Upload: Retries & backoff!"))
    assert cli.main(["plan", "path", "proj-12", "--slug", "retry-failed-runs"]) == 0
    expected = repo / f".agents/plans/PROJ-1-upload-retries-backoff/PROJ-12-retry-failed-runs-{TODAY}.md"
    assert capsys.readouterr().out.strip() == str(expected)

    monkeypatch.setattr(Jira, "parent", lambda self, i: None)
    assert cli.main(["plan", "path", "proj-13", "--slug", "standalone"]) == 0
    assert capsys.readouterr().out.strip() == str(repo / f".agents/plans/PROJ-13-standalone-{TODAY}.md")


def test_plan_lookup_does_not_mistake_a_date_or_longer_id_for_the_issue(repo, capsys):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('tracker = "none"\n')
    plans = repo / ".agents/plans/7-epic"
    plans.mkdir(parents=True)
    (plans / "102-other-2026-10-04.md").write_text("# other\n")
    (plans / "10-mine-2026-09-01.md").write_text("# mine\n")
    assert cli.main(["plan", "path", "10"]) == 0
    assert capsys.readouterr().out.strip() == str(plans / "10-mine-2026-09-01.md")
    assert cli.main(["plan", "path", "4"]) == 1


def test_local_plans_live_in_the_primary_checkout(repo, tmp_path, capsys, monkeypatch):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(f'tracker = "none"\nworktree_root = "{tmp_path}/wt"\n')
    (repo / ".agents/aw.local.toml").write_text('plan_scope = "local"\n')
    git("add", ".agents/aw.toml", cwd=repo)
    git("commit", "-qm", "cfg", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    assert [m for lvl, m in doctor.run() if "plan_scope" in m] == [
        f"plan_scope = local but {repo}/.agents/plans is not gitignored"]
    (repo / ".agents/.gitignore").write_text("aw.local.toml\nplans/\n")
    assert not [m for lvl, m in doctor.run() if "plan_scope" in m]

    worktree = start_task.run(load(), "feat", "retries", None)["worktree"]
    monkeypatch.chdir(worktree)
    assert cli.main(["plan", "path", "12", "--slug", "retries"]) == 0
    assert capsys.readouterr().out.strip() == str(repo / f".agents/plans/12-retries-{TODAY}.md")


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


def test_plan_state_of_a_story_under_an_epic_stays_on_the_story(repo, capsys, monkeypatch):
    project(repo, 'plan_dir = "docs/planning"\n')
    (repo / "docs/planning").mkdir(parents=True)
    (repo / "docs/planning/PROJ-1-the-epic.md").write_text("# epic plan\n")
    epic = trackers.Row("PROJ-1", type="Epic", link="native")
    monkeypatch.setattr(Jira, "parent", lambda self, i: epic)
    monkeypatch.setattr(Jira, "children", lambda self, i: [trackers.Row("PROJ-13")] if i == "PROJ-12" else [])
    assert cli.main(["plan", "state", "proj-12"]) == 0
    assert capsys.readouterr().out == "issue=PROJ-12\nplan=none\nsubtasks=PROJ-13\n"
