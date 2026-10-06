import json

import pytest

from aw import cli, doctor, memory, session, start_task
from aw.config import AwError, git, load


def body(tmp_path, text):
    path = tmp_path / "body.md"
    path.write_text(text)
    return str(path)


@pytest.fixture
def vocab(repo):
    (repo / ".agents/memory").mkdir(parents=True)
    (repo / ".agents/memory/tags.toml").write_text(
        'flux = "Flux CD: kustomizations, HelmReleases"\ntalos = "Talos Linux and talosctl"\nsops = "SOPS and age"\n')
    return repo


def add(tmp_path, kind, title, text, tags=""):
    args = ["memory", "add", kind, "--title", title, "--body-file", body(tmp_path, text)]
    return cli.main(args + (["--tags", tags] if tags else []))


def test_add_writes_one_file_per_entry_with_frontmatter(vocab, tmp_path, capsys):
    assert add(tmp_path, "gotcha", "Flux reconcile hangs on a missing CRD", "## Fix\n\nSplit the kustomization.\n",
               "flux") == 0
    assert capsys.readouterr().out == "wrote .agents/memory/gotchas/flux-reconcile-hangs-on-a-missing-crd.md\n"
    text = (vocab / ".agents/memory/gotchas/flux-reconcile-hangs-on-a-missing-crd.md").read_text()
    assert text.startswith('---\ntitle: "Flux reconcile hangs on a missing CRD"\ntags: ["flux"]\nstatus: "active"\n')
    assert text.endswith("---\n\n## Fix\n\nSplit the kustomization.\n")
    assert add(tmp_path, "decision", "Plans live in git", "Tracker holds tickets only.\n") == 0  # tags optional


def test_add_rejects_unknown_or_missing_tags_and_duplicate_slugs(vocab, tmp_path, capsys):
    assert add(tmp_path, "gotcha", "Untagged", "x\n") == 1
    assert "needs at least one tag" in capsys.readouterr().err
    assert add(tmp_path, "gotcha", "Kyverno blocks", "x\n", "kyverno") == 1
    assert "unknown tag(s): kyverno; add them to .agents/memory/tags.toml first" in capsys.readouterr().err
    assert add(tmp_path, "gotcha", "Same title", "x\n", "flux") == 0
    assert add(tmp_path, "gotcha", "Same title!", "y\n", "flux") == 1
    assert "same-title.md exists: same subject?" in capsys.readouterr().err


def test_find_show_tags_and_supersede(vocab, tmp_path, capsys):
    add(tmp_path, "gotcha", "Flux needs CRDs first", "dependsOn on the operator\n", "flux")
    add(tmp_path, "gotcha", "talosctl needs the endpoint", "pass -e\n", "talos")
    add(tmp_path, "gotcha", "SOPS rule order matters", "first match wins in flux decryption\n", "sops,flux")
    capsys.readouterr()

    assert cli.main(["memory", "find", "--tags", "flux", "--compact"]) == 0
    assert capsys.readouterr().out == ("- flux-needs-crds-first · Flux needs CRDs first\n"
                                       "- sops-rule-order-matters · SOPS rule order matters\n")
    assert cli.main(["memory", "find", "--text", "FIRST", "match", "--compact"]) == 0
    assert capsys.readouterr().out == "- sops-rule-order-matters · SOPS rule order matters\n"

    assert cli.main(["memory", "tags"]) == 0
    assert capsys.readouterr().out == "flux 2 · sops 1 · talos 1\n"  # most first, ties alphabetical

    assert cli.main(["memory", "supersede", "talosctl-needs-the-endpoint", "--reason", "talosconfig sets it",
                     "--by", "flux-needs-crds-first"]) == 0
    capsys.readouterr()
    assert cli.main(["memory", "find", "--tags", "talos", "--compact"]) == 0
    assert capsys.readouterr().out == "no entries\n"
    assert cli.main(["memory", "find", "--tags", "talos", "--compact", "--retired"]) == 0
    assert "(retired → flux-needs-crds-first)" in capsys.readouterr().out
    assert cli.main(["memory", "show", "talosctl-needs-the-endpoint"]) == 0
    assert "_Retired " in capsys.readouterr().out


def test_import_validates_everything_before_writing(vocab, capsys):
    lines = [
        {"kind": "gotcha", "title": "Bootstrap fails with host parse error", "tags": ["talos"], "aliases": ["1"],
         "date": "2026-01-02", "sections": {"Symptom": "fails", "Cause": "inventory", "Fix": "add pve01"}},
        {"kind": "decision", "title": "GitOps engine: Flux CD, not ArgoCD", "tags": ["flux"], "aliases": ["D15"],
         "body": "See phase 02."},
        {"kind": "gotcha", "title": "Second with the same alias", "tags": ["flux"], "aliases": ["1"]},
        {"kind": "gotcha", "title": "Bad tag", "tags": ["nope"]},
    ]
    path = vocab / "import.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    assert cli.main(["memory", "import", "--json", str(path)]) == 1
    err = capsys.readouterr().err
    assert "nothing written" in err and "line 4: unknown tag(s): nope" in err
    assert "alias '1' claimed by bootstrap-fails-with-host-parse-error, second-with-the-same-alias" in err
    assert not (vocab / ".agents/memory/gotchas").exists()

    path.write_text("\n".join(json.dumps(line) for line in lines[:2]) + "\n")
    assert cli.main(["memory", "import", "--json", str(path)]) == 0
    assert capsys.readouterr().out == "imported 1 gotcha, 1 decision\n"
    assert cli.main(["memory", "show", "#1"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("gotcha: bootstrap-fails-with-host-parse-error\n")
    assert "## Symptom\n\nfails\n\n## Cause\n\ninventory" in out and 'aliases: ["1"]' in out
    assert cli.main(["memory", "show", "d15"]) == 0
    assert "GitOps engine" in capsys.readouterr().out


def test_session_start_load_per_mode_and_the_experiment_log(vocab, tmp_path, monkeypatch, capsys):
    add(tmp_path, "gotcha", "Flux needs CRDs first", "dependsOn\n", "flux")
    add(tmp_path, "decision", "Plans live in git", "x\n")
    cfg = load()
    full = memory.start_text(cfg, has_plan=False)
    assert "# Gotchas\n\n## Flux needs CRDs first\n\ndependsOn" in full
    assert "- plans-live-in-git · Plans live in git" in full
    assert "Plans live in git" not in memory.start_text(cfg, has_plan=True)

    (vocab / ".agents/aw.toml").write_text(f'gotchas_load = "tags"\nworktree_root = "{tmp_path}/wt"\n')
    git("add", ".", cwd=vocab)
    git("commit", "-qm", "memory", cwd=vocab)
    git("push", "-q", "origin", "main", cwd=vocab)
    wt = start_task.run(load(), "feat", "probe", None)["worktree"]
    monkeypatch.chdir(wt)
    capsys.readouterr()
    assert cli.main(["memory", "load", "--plan"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Known gotchas by tool.") and out.rstrip().endswith("flux 1")
    assert session.read()["memory_start_tokens"] == memory.tokens(out.rstrip("\n"))

    assert cli.main(["memory", "log", "--relevant", "flux-needs-crds-first", "--missed", "none", "--note", "ok"]) == 0
    record = json.loads((vocab / ".agents/gotchas-experiment.log").read_text())
    assert record["mode"] == "tags" and record["relevant"] == ["flux-needs-crds-first"]
    assert record["start_tokens"] == memory.tokens(out.rstrip("\n")) and record["missed"] == []


def test_plan_pulls_are_counted_from_known_gotchas(tmp_path):
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("# Plan\n\n## Known gotchas\n\n- a-b · A\n- c · C\n\n## Decisions in force\n\n- d · D\n")
    assert memory.pulled(plan_file) == ["a-b", "c"]


def test_doctor_checks_tags_successors_and_aliases(vocab, tmp_path):
    (vocab / ".agents/aw.toml").write_text("aw_version = 1\n")
    gotchas = vocab / ".agents/memory/gotchas"
    gotchas.mkdir(parents=True)
    (gotchas / "a.md").write_text('---\ntitle: "A"\ntags: ["ghost"]\nstatus: "retired"\nsuperseded_by: "zz"\n'
                                  'aliases: ["7"]\n---\n\nx\n')
    (gotchas / "b.md").write_text('---\ntitle: "B"\ntags: ["flux"]\nstatus: "active"\naliases: ["7"]\n---\n\ny\n')
    results = doctor.check_memory(load())
    assert ("fail", "memory: unknown tags on a (ghost)") in results
    assert ("fail", "memory: superseded_by points nowhere in a") in results
    assert ("fail", "memory: aliases claimed twice: 7 (a, b)") in results
    with pytest.raises(AwError, match="claimed by a, b"):
        memory.resolve(load(), "7")
