import os
import stat

import pytest

from aw import doctor, init, install
from aw.config import AwError


def fake_exe(tmp_path):
    exe = tmp_path / "venv/bin/aw"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


def test_install_links_and_is_idempotent(env, tmp_path):
    exe = fake_exe(tmp_path)
    install.run(["claude"], exe)
    skill = install.source_skills()[0]
    assert (env / ".agents/skills" / skill.name).resolve() == skill.resolve()
    assert (env / ".claude/skills" / skill.name).resolve() == skill.resolve()
    assert (env / ".agents/bin/aw").resolve() == exe.resolve()
    again = install.run(["claude"], exe)
    assert all(line.startswith("unchanged") for line in again)


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
    (repo / ".agents/aw.toml").write_text('instructions_file = "MISSING.md"\nbogus = 1\n')
    results = {msg: level for level, msg in doctor.run()}
    assert results[".agents/aw.toml: aw_version missing; run `aw init`"] == "fail"
    assert results["instructions_file MISSING.md not found"] == "fail"
    assert results["project: unknown key 'bogus'"] == "warn"
    assert any(level == "fail" and "run `aw install`" in msg for msg, level in results.items())


def test_skill_frontmatter_check(tmp_path):
    skill = tmp_path / "Bad-Name"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: other\ndescription: x\n---\n")
    levels = {level for level, _ in doctor.check_skill(skill)}
    assert levels == {"fail"}


def test_menu_lists_skills_before_commands(capsys):
    from aw import cli

    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert out.index("Skills") < out.index("/aw-start-task") < out.index("Commands") < out.index("aw start-task")
    assert "/aw-start-task" in out and "Start an implementation session (user only)" in out
    assert "\033[" not in out  # no colour when not a terminal
