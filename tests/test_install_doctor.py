import os
import stat
import tomllib
from pathlib import Path

import pytest

from aw import doctor, init, install
from aw.config import AwError, git


def fake_exe(tmp_path):
    exe = tmp_path / "venv/bin/aw"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


def test_cli_matches_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    from aw import cli

    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out == f"aw {project['project']['version']}\n"


def test_install_links_and_is_idempotent(env, tmp_path):
    exe = fake_exe(tmp_path)
    install.run(["claude"], exe)
    skill = install.source_skills()[0]
    assert (env / ".agents/skills" / skill.name).resolve() == skill.resolve()
    assert (env / ".claude/skills" / skill.name).resolve() == skill.resolve()
    assert (env / ".agents/bin/aw").resolve() == exe.resolve()
    again = install.run(["claude"], exe)
    assert {c.action for c in again.changes} == {"unchanged"}


def test_install_summary_and_verbose(env, tmp_path, monkeypatch, capsys):
    from aw import cli

    exe = fake_exe(tmp_path)
    monkeypatch.setattr("sys.argv", [str(exe)])
    monkeypatch.setenv("PATH", "/usr/bin")
    count = len(install.source_skills())
    assert cli.main(["install"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "aw install"
    assert out[1].split() == ["~/.agents/skills", str(count), "skills", str(count), "new"]
    assert out[2].split() == ["~/.claude/skills", str(count), "skills", str(count), "new"]
    assert out[3].split() == ["~/.agents/bin/aw", "CLI", "1", "new"]
    assert out[4].startswith("! `aw` is not on your PATH") and "uv tool update-shell" in out[5]
    assert len(out) == 6

    (env / ".claude/skills" / install.source_skills()[0].name).unlink()
    gone = env / ".agents/skills/aw-retired"
    gone.symlink_to(install.skills_source() / "aw-retired")
    assert cli.main(["install"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[1].endswith("1 removed") and out[2].endswith("1 new")
    assert out[4:6] == [f"  new:     {install.source_skills()[0].name}", "  removed: aw-retired"]

    assert cli.main(["install"]) == 0
    assert all(line.endswith("up to date") for line in capsys.readouterr().out.splitlines()[1:4])
    assert cli.main(["install", "--verbose"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len([line for line in lines if line.startswith("  unchanged ")]) == 2 * count + 1


def test_install_prunes_dangling_links(env, tmp_path):
    install.run(["claude"], fake_exe(tmp_path))
    gone = env / ".agents/skills/aw-removed"
    gone.symlink_to(install.skills_source() / "aw-removed")
    claude_gone = env / ".claude/skills/aw-removed"
    claude_gone.symlink_to(gone)
    install.run(["claude"], None)
    assert not os.path.lexists(gone) and not os.path.lexists(claude_gone)


def test_install_refuses_real_dir(env, tmp_path):
    skill = install.source_skills()[0]
    (env / ".claude/skills" / skill.name).mkdir(parents=True)
    with pytest.raises(AwError, match="not a symlink"):
        install.run(["claude"], fake_exe(tmp_path))


def test_doctor_healthy(env, repo, tmp_path):
    install.run(["claude"], fake_exe(tmp_path))
    init.run(True, [])
    results = doctor.run()
    assert [r for r in results if r[0] == "fail"] == []


def test_doctor_reports_problems(env, repo):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('instructions_file = "MISSING.md"\nbogus = 1\nsandboxed = true\n')
    results = {msg: level for level, msg in doctor.run()}
    assert results[".agents/aw.toml: aw_version missing; run `aw init`"] == "fail"
    assert results["instructions_file MISSING.md not found"] == "fail"
    assert results["project: unknown key 'bogus'"] == "warn"
    assert results["project: sandboxed is set by the environment only (AW_SANDBOXED); ignored"] == "warn"
    assert any(level == "fail" and "run `aw install`" in msg for msg, level in results.items())


def test_skill_frontmatter_check(tmp_path):
    skill = tmp_path / "Bad-Name"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: other\ndescription: x\n---\n")
    levels = {level for level, _ in doctor.check_skill(skill)}
    assert levels == {"fail"}


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        ('Plan it. Use when the user says "plan issue #N"', "' #' starts a YAML comment"),
        ("Plan it: one story", "': ' is a YAML mapping"),
    ],
)
def test_an_unquoted_description_that_yaml_cuts_or_rejects_fails(tmp_path, value, problem):
    skill = tmp_path / "aw-x"
    skill.mkdir()
    (skill / "SKILL.md").write_text(f"---\nname: aw-x\ndescription: {value}\n---\n")
    assert doctor.check_skill(skill) == [
        ("fail", f"skill aw-x: description: {problem} in an unquoted value; quote the value")
    ]
    (skill / "SKILL.md").write_text(f"---\nname: aw-x\ndescription: '{value}'\n---\n")
    assert doctor.check_skill(skill) == [("ok", "skill aw-x: frontmatter valid")]


def test_every_bundled_skill_has_valid_frontmatter():
    assert [r for skill in install.source_skills() for r in doctor.check_skill(skill) if r[0] != "ok"] == []


GATED = ("aw merge", "aw finish", "aw abandon", "aw issue rollup", "aw issue set-status")
READ_ONLY = "/aw issue rollup --json:*"


def test_no_skill_pre_approves_a_command_that_merges_or_closes():
    """allowed-tools skip the permission prompt; a merge or a close must keep it, whatever the model was told."""
    pre_approved = [
        f"{skill.name}: {tool}"
        for skill in install.source_skills()
        for line in (skill / "SKILL.md").read_text().splitlines()
        if line.startswith("allowed-tools:")
        for tool in line.removeprefix("allowed-tools:").split(") ")
        if any(f"/{command}" in tool for command in GATED) and not tool.rstrip(")").endswith(READ_ONLY)
    ]
    assert pre_approved == []


def test_menu_lists_skills_before_commands(capsys):
    from aw import cli

    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert out.index("Skills") < out.index("/aw-start-task") < out.index("Commands") < out.index("aw start-task")
    assert "/aw-start-task" in out and "Start an implementation session (user only)" in out
    assert "\033[" not in out  # no colour when not a terminal


def test_doctor_summary_lists_problems_and_verbose_lists_everything(env, repo, tmp_path, monkeypatch, capsys):
    from aw import cli

    install.run(["claude"], fake_exe(tmp_path))
    init.run(True, [])
    monkeypatch.setenv("PATH", f"{env}/.agents/bin:/usr/bin:/bin")
    assert any("not committed: session worktrees start from main" in m for _, m in doctor.check_project())
    git("add", ".agents", cwd=repo)
    git("commit", "-qm", "aw config", cwd=repo)
    count = len(install.source_skills())
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "aw doctor"
    assert out[1].split() == ["✓", "CLI", "~/.agents/bin/aw"]
    assert out[2].split() == ["✓", "Skills", f"({count})", str(3 * count), "checks", "ok"]
    assert out[-1] == "all good"
    assert not [line for line in out if line.startswith("      ")]

    (env / ".agents/bin/aw").unlink()
    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[1].split()[:4] == ["✗", "CLI", "1", "failure"]
    assert out[2].strip().startswith("✗ ~/.agents/bin/aw missing")
    assert out[-1].startswith("1 failure")

    assert cli.main(["doctor", "--verbose"]) == 1
    detail = [line for line in capsys.readouterr().out.splitlines() if line.startswith("      ✓")]
    assert len(detail) >= 3 * count


def test_doctor_lists_hooks(repo):
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('on_merge = "flux reconcile source git flux-system"\n')
    assert ("ok", "hook on_merge: flux reconcile source git flux-system") in doctor.check_project()


def test_doctor_names_a_template_outside_the_checkout(env, repo, tmp_path):
    shared = tmp_path / "shared/mr.md"
    shared.parent.mkdir()
    shared.write_text("## Summary\n")
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text('forge = "github"\n')
    (repo / ".agents/aw.local.toml").write_text(f'templates = {{ mr = "{shared}" }}\n')  # outside: never committed
    results = {msg: level for level, msg in doctor.run()}
    assert results[f"merge request template: {shared}"] == "ok"


def test_doctor_in_a_worktree_names_the_keys_it_ignores_from_the_branch(repo, tmp_path, monkeypatch):
    from aw import start_task
    from aw.config import load

    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text(f'worktree_root = "{tmp_path}/wt"\n')
    git("add", ".", cwd=repo)
    git("commit", "-qm", "cfg", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    wt = Path(start_task.run(load(), "feat", "thing", None)["worktree"])
    config = wt / ".agents/aw.toml"
    config.write_text(config.read_text() + 'merge_method = "squash"\n')
    monkeypatch.chdir(wt)
    infos = [msg for level, msg in doctor.check_project() if level == "info"]
    assert any(msg.startswith("ignored from the branch: merge_method;") for msg in infos)


def test_doctor_fails_a_path_key_that_links_out_of_the_repo(env, repo, tmp_path):
    """Skills read instructions_file and contributing_file themselves; a committed link out of the repo would hand
    them any file."""
    (tmp_path / "secret.md").write_text("x\n")
    (repo / "AGENTS.md").unlink()
    (repo / "AGENTS.md").symlink_to(tmp_path / "secret.md")
    (repo / ".agents").mkdir()
    (repo / ".agents/aw.toml").write_text("aw_version = 1\n")
    results = {msg: level for level, msg in doctor.run()}
    assert results[f"instructions_file: {repo}/AGENTS.md resolves outside the repo; aw follows no link out of it"] == (
        "fail"
    )
