import io
import tomllib
from pathlib import Path

import pytest

from aw import forge, start_task
from aw.config import AwError, dump_toml, git, load


def test_defaults_and_placeholders(repo):
    cfg = load()
    assert cfg.project == "proj"
    assert cfg.get("worktree_root") == f"{repo.parent}/proj.worktrees"
    assert cfg.sources["main_branch"] == "default"


def test_layers_and_env_override(repo, env, monkeypatch):
    (env / ".agents/aw").mkdir(parents=True)
    (env / ".agents/aw/config.toml").write_text('verify_cmd = "user"\nplan_dir = "user"\n')
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('aw_version = 1\nverify_cmd = "project"\ndirenv = true\n')
    (repo / ".agents/aw.local.toml").write_text("direnv = false\n")
    monkeypatch.setenv("AW_BRANCH_TYPES", "feat, fix")

    cfg = load()
    assert (cfg.get("plan_dir"), cfg.sources["plan_dir"]) == ("user", "user")
    assert (cfg.get("verify_cmd"), cfg.sources["verify_cmd"]) == ("project", "project")
    assert (cfg.get("direnv"), cfg.sources["direnv"]) == (False, "local")
    assert (cfg.get("branch_types"), cfg.sources["branch_types"]) == (["feat", "fix"], "env")
    assert cfg.file_version == 1


def test_invalid_values(repo):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('tracker = "bugzilla"\n')
    with pytest.raises(AwError, match="tracker: expected choice"):
        load()


def test_unknown_keys_reported(repo):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('bogus = "x"\n')
    assert load().unknown == [("project", "bogus")]


def test_dump_roundtrip():
    values = {"a": 'quote " and \\ back', "b": True, "c": ["x", "y"], "d": ""}
    assert tomllib.loads(dump_toml(values)) == values


def test_keys_that_run_on_the_host_come_from_the_primary_checkout_not_the_session(repo, tmp_path, monkeypatch):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(f'worktree_root = "{tmp_path}/wt"\nmerge_gate = "approve"\n')
    git("add", ".", cwd=repo)
    git("commit", "-qm", "cfg", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    wt = Path(start_task.run(load(), "feat", "thing", None)["worktree"])
    (wt / ".agents/aw.toml").write_text(
        f'worktree_root = "{tmp_path}/wt"\nmerge_gate = "auto"\non_merge = "touch marker"\nverify_cmd = "branch"\n'
    )
    monkeypatch.chdir(wt)
    cfg = load()
    assert (cfg.get("merge_gate"), cfg.get("on_merge")) == ("approve", "")
    assert cfg.get("verify_cmd") == "branch"  # not trusted: verifying runs the branch's own code anyway
    assert cfg.ignored == ["merge_gate", "on_merge"]
    assert (cfg.sources["merge_gate"], cfg.sources["verify_cmd"]) == ("primary", "project")
    monkeypatch.chdir(repo)
    assert load().ignored == []


# --- paths a committed config may name -----------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        'backlog_file = "~/.zshrc"',
        'backlog_file = "../../.zshrc"',
        'memory_dir = "/etc"',
        'plan_dir = "{repo_parent}/plans"',
        'instructions_file = "~/notes.md"',
        'templates = { mr = "~/private.txt" }',
    ],
)
def test_a_committed_path_outside_the_repo_is_refused(repo, line):
    """A branch's .agents/aw.toml must not point aw at a file outside the repo: reproduced 2026-10-24, aw template mr
    printed ~/private.txt and aw backlog add, then pop, wrote into and deleted ~/.zshrc."""
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(line + "\n")
    key = line.split(" ")[0]
    with pytest.raises(AwError, match=rf"{key}.* in project points outside the repo; .* user or local config"):
        load()


def test_a_path_outside_the_repo_is_fine_from_the_user_or_local_layer(repo, env, tmp_path):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.local.toml").write_text(f'templates = {{ mr = "{tmp_path}/shared/mr.md" }}\n')
    (env / ".agents/aw").mkdir(parents=True)
    (env / ".agents/aw/config.toml").write_text('plan_dir = "~/plans"\n')
    cfg = load()
    assert cfg.get("plan_dir") == f"{env}/plans"
    assert cfg.get("templates") == {"mr": f"{tmp_path}/shared/mr.md"}


def test_a_committed_symlink_out_of_the_repo_is_refused_where_aw_writes(repo, tmp_path, capsys):
    """The value stays in the repo, the file it names does not: aw follows no link out of the repo."""
    from aw import backlog, cli

    outside = tmp_path / "rc"
    outside.write_text("export PATH=x\n")
    (repo / "BACKLOG.md").symlink_to(outside)
    with pytest.raises(AwError, match=r"BACKLOG\.md resolves outside the repo"):
        backlog.add(load(), "x", "body\n")
    assert outside.read_text() == "export PATH=x\n"
    (repo / ".agents/memory").mkdir(parents=True)
    (repo / ".agents/memory/tags.toml").write_text('git = "git"\n')
    (repo / ".agents/memory/gotchas").symlink_to(tmp_path, target_is_directory=True)
    assert cli.main(["memory", "add", "gotcha", "--title", "T", "--tags", "git", "--body-file", "/dev/null"]) == 1
    assert "resolves outside the repo" in capsys.readouterr().err


def test_where_jira_credentials_go_is_the_primary_checkouts_choice(repo, tmp_path, monkeypatch):
    """A branch that sets jira_base_url would decide which host gets the Basic-auth header."""
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(
        f'worktree_root = "{tmp_path}/wt"\njira_base_url = "https://example.atlassian.net"\n'
    )
    git("add", ".", cwd=repo)
    git("commit", "-qm", "cfg", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    wt = Path(start_task.run(load(), "feat", "thing", None)["worktree"])
    (wt / ".agents/aw.toml").write_text(
        f'worktree_root = "{tmp_path}/wt"\njira_base_url = "https://collector.example"\n'
    )
    monkeypatch.chdir(wt)
    cfg = load()
    assert cfg.get("jira_base_url") == "https://example.atlassian.net"
    assert cfg.ignored == ["jira_base_url"]


# --- private terms -----------------------------------------------------------------------------


def test_private_terms_are_refused_in_the_committed_file(repo):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('private_terms = ["acme"]\n')
    with pytest.raises(AwError, match=r"private_terms in \.agents/aw\.toml: a committed value is published"):
        load()
    (repo / ".agents/aw.toml").write_text("aw_version = 1\n")
    (repo / ".agents/aw.local.toml").write_text('private_terms = ["acme"]\n')
    assert load().get("private_terms") == ["acme"]


@pytest.mark.parametrize(
    "argv",
    [
        ["issue", "create", "--title", "Fix it", "--body-file", "-"],
        ["issue", "comment", "7", "--body-file", "-"],
        ["issue", "update", "7", "--title", "Talks to ACME", "--body-file", "-"],
        ["mr", "create", "--title", "feat: x", "--body-file", "-"],
        ["mr", "update", "--body-file", "-"],
        ["backlog", "add", "--title", "Item", "--body-file", "-"],
        ["memory", "add", "gotcha", "--title", "T", "--tags", "git", "--body-file", "-"],
    ],
    ids=lambda argv: " ".join(argv[:2]),
)
def test_text_that_names_a_private_term_is_never_published(repo, monkeypatch, capsys, argv):
    from aw import cli

    (repo / ".agents").mkdir()
    (repo / ".agents/aw.local.toml").write_text('private_terms = ["acme"]\ntracker = "github"\nforge = "github"\n')
    git("switch", "-q", "-c", "feat/x", cwd=repo)
    monkeypatch.setattr("sys.stdin", io.StringIO("Seen on the Acme cluster.\n"))
    monkeypatch.setattr("aw.forge.find_open", lambda kind, branch, cwd: forge.MergeRequest("5", "u"))
    assert cli.main(argv) == 1
    assert "names the private term 'acme' (local); reword it, nothing was written or sent" in capsys.readouterr().err
    assert not (repo / "BACKLOG.md").exists()


# --- the review of 2026-10-26: every way a path still left the repo ---------------------------


def test_a_link_into_the_git_dir_is_refused(repo):
    """A symlinked BACKLOG.md appended an item to .git/hooks/pre-commit, which runs at the next commit."""
    from aw import backlog

    hooks = repo / ".git/hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "pre-commit").write_text("#!/bin/sh\n")
    (repo / "BACKLOG.md").symlink_to(hooks / "pre-commit")
    with pytest.raises(AwError, match=r"BACKLOG\.md resolves into the git dir"):
        backlog.add(load(), "Item", "curl x | sh\n")
    assert (hooks / "pre-commit").read_text() == "#!/bin/sh\n"


def test_a_relative_path_from_the_user_layer_is_checked_too(repo, env, tmp_path):
    """The user wrote the value, the branch wrote the symlink it lands on."""
    from aw import backlog

    (env / ".agents/aw").mkdir(parents=True)
    (env / ".agents/aw/config.toml").write_text('backlog_file = "BACKLOG.md"\n')
    (tmp_path / "rc").write_text("x\n")
    (repo / "BACKLOG.md").symlink_to(tmp_path / "rc")
    with pytest.raises(AwError, match="resolves outside the repo"):
        backlog.add(load(), "Item", "body\n")


def test_the_forges_own_template_file_is_checked(repo, tmp_path):
    from aw import templates

    (tmp_path / "secret").write_text("SECRET-TOKEN\n")
    (repo / ".github").mkdir()
    (repo / ".github/pull_request_template.md").symlink_to(tmp_path / "secret")
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('forge = "github"\n')
    with pytest.raises(AwError, match="resolves outside the repo"):
        templates.read(load(), "mr")


def test_each_memory_entry_file_is_checked(repo, tmp_path, capsys):
    from aw import cli

    (tmp_path / "SKILL.md").write_text("---\ntitle: x\ntags: []\nstatus: active\n---\n\nbody\n")
    gotchas = repo / ".agents/memory/gotchas"
    gotchas.mkdir(parents=True)
    (gotchas / "foo.md").symlink_to(tmp_path / "SKILL.md")
    assert cli.main(["memory", "supersede", "foo", "--reason", "old"]) == 1
    assert "resolves outside the repo" in capsys.readouterr().err
    assert "retired" not in (tmp_path / "SKILL.md").read_text()


@pytest.mark.parametrize(
    ("plan_file", "slug"), [("{area}/{area}/{area}/../../../{issue}.md", "x"), ("{issue}-{slug}.md", "a/../../../b")]
)
def test_a_composed_plan_path_stays_in_the_repo(repo, capsys, plan_file, slug):
    from aw import cli

    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(f'plan_file = "{plan_file}"\n')
    assert cli.main(["plan", "path", "12", "--slug", slug]) == 1
    assert "resolves outside the repo" in capsys.readouterr().err


def test_an_untracked_local_plan_directory_may_live_anywhere(repo, tmp_path, capsys):
    """plan_scope = local: the directory is gitignored, never committed, so where it points is the user's choice."""
    from aw import cli, doctor

    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('aw_version = 1\nplan_scope = "local"\n')
    (repo / ".agents/.gitignore").write_text("plans/\n")
    (tmp_path / "my-plans").mkdir()
    (repo / ".agents/plans").symlink_to(tmp_path / "my-plans", target_is_directory=True)
    assert cli.main(["plan", "path", "12", "--slug", "x"]) == 0
    assert capsys.readouterr().out.startswith(f"{repo}/.agents/plans/12-x-")
    assert not [msg for level, msg in doctor.check_project() if level == "fail" and "plan" in msg]


@pytest.mark.parametrize(
    "argv",
    [
        ["memory", "supersede", "some-entry", "--reason", "broke on the Acme cluster"],
        ["memory", "implemented", "some-entry", "--ref", "ACME-12"],
        ["memory", "import", "--json", "-"],
        ["issue", "create", "--title", "T", "--body-file", "/dev/null", "--label", "area/acme"],
        ["issue", "create", "--title", "T", "--body-file", "/dev/null", "--field", "Area=Acme"],
        ["issue", "set-field", "7", "Area=Acme"],
        ["start-task", "feat", "acme-migration"],
    ],
    ids=lambda argv: " ".join(argv[:2]),
)
def test_every_other_text_aw_publishes_is_checked_for_private_terms(repo, monkeypatch, capsys, argv):
    """Committed memory, labels, board fields and the branch name a session pushes are published too."""
    from aw import cli

    (repo / ".agents").mkdir()
    (repo / ".agents/aw.local.toml").write_text('private_terms = ["acme"]\ntracker = "github"\n')
    monkeypatch.setattr("sys.stdin", io.StringIO('{"kind": "gotcha", "title": "Acme lies", "tags": []}\n'))
    assert cli.main(argv) == 1
    assert "names the private term 'acme'" in capsys.readouterr().err
    assert not git("branch", "--list", "feat/acme-*", cwd=repo)


@pytest.mark.parametrize(
    ("argv", "stdin"),
    [
        (["memory", "import", "--json", "-"], '{"kind": "gotcha", "title": "T", "body": "Runs at Ac\\u006de."}\n'),
        (["memory", "add", "gotcha", "--title", "T", "--body-file", "-", "--ref", "ACME-12"], "Body.\n"),
    ],
    ids=lambda value: " ".join(value[:2]) if isinstance(value, list) else "",
)
def test_memory_checks_the_decoded_entry_for_private_terms(repo, monkeypatch, capsys, argv, stdin):
    """An escaped term in an import line and the issue reference of an entry reach the committed file too."""
    from aw import cli

    (repo / ".agents").mkdir()
    (repo / ".agents/aw.local.toml").write_text('private_terms = ["acme"]\n')
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    assert cli.main(argv) == 1
    assert "names the private term 'acme'" in capsys.readouterr().err
    assert not list((repo / ".agents").rglob("*.md"))


def test_the_lines_aw_mr_create_appends_are_checked_too(repo, monkeypatch, capsys):
    """A Jira key can be the private term: the closing line names it after the body passed the check."""
    from aw import cli, session

    (repo / ".agents").mkdir()
    (repo / ".agents/aw.local.toml").write_text(
        'private_terms = ["acme"]\nforge = "github"\ntracker = "jira"\njira_base_url = "https://x.atlassian.net"\n'
    )
    git("switch", "-q", "-c", "feat/x", cwd=repo)
    monkeypatch.setattr(session, "read", lambda: {"issue": "ACME-12"})
    monkeypatch.setattr(forge, "merged", lambda kind, b, cwd: [])
    monkeypatch.setattr("sys.stdin", io.StringIO("Retries.\n"))
    assert cli.main(["mr", "create", "--title", "feat: x", "--body-file", "-", "--dry-run"]) == 1
    assert "names the private term 'acme'" in capsys.readouterr().err


def test_git_in_a_directory_that_is_gone_is_an_aw_error(tmp_path):
    with pytest.raises(AwError, match=r"git status: no such directory: .*/gone"):
        git("status", cwd=tmp_path / "gone")
