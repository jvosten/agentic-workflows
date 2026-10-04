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


def test_doctor_summary_lists_problems_and_verbose_lists_everything(env, repo, tmp_path, monkeypatch, capsys):
    from aw import cli

    install.run(["claude"], fake_exe(tmp_path))
    init.run(True, [])
    monkeypatch.setenv("PATH", f"{env}/.agents/bin:/usr/bin:/bin")
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
