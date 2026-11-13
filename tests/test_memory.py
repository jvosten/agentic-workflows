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
        'flux = "Flux CD: kustomizations, HelmReleases"\ntalos = "Talos Linux and talosctl"\nsops = "SOPS and age"\n'
    )
    return repo


def add(tmp_path, kind, title, text, tags=""):
    args = ["memory", "add", kind, "--title", title, "--body-file", body(tmp_path, text)]
    return cli.main(args + (["--tags", tags] if tags else []))


def test_add_writes_one_file_per_entry_with_frontmatter(vocab, tmp_path, capsys):
    assert (
        add(tmp_path, "gotcha", "Flux reconcile hangs on a missing CRD", "## Fix\n\nSplit the kustomization.\n", "flux")
        == 0
    )
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
    assert capsys.readouterr().out == (
        "- flux-needs-crds-first · Flux needs CRDs first\n- sops-rule-order-matters · SOPS rule order matters\n"
    )
    assert cli.main(["memory", "find", "--text", "FIRST", "match", "--compact"]) == 0
    assert capsys.readouterr().out == "- sops-rule-order-matters · SOPS rule order matters\n"

    assert cli.main(["memory", "tags"]) == 0
    assert capsys.readouterr().out == "flux 2 · sops 1 · talos 1\n"  # most first, ties alphabetical

    assert (
        cli.main(
            [
                "memory",
                "supersede",
                "talosctl-needs-the-endpoint",
                "--reason",
                "talosconfig sets it",
                "--by",
                "flux-needs-crds-first",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert cli.main(["memory", "find", "--tags", "talos", "--compact"]) == 0
    assert capsys.readouterr().out == "no entries\n"
    assert cli.main(["memory", "find", "--tags", "talos", "--compact", "--retired"]) == 0
    assert "(retired → flux-needs-crds-first)" in capsys.readouterr().out
    assert cli.main(["memory", "show", "talosctl-needs-the-endpoint"]) == 0
    assert "_Retired " in capsys.readouterr().out


def test_an_intent_decision_is_marked_until_it_is_implemented(vocab, tmp_path, capsys):
    args = ["memory", "add", "decision", "--title", "Plans live in git", "--body-file", body(tmp_path, "Why.\n")]
    assert cli.main([*args, "--intent", "--ref", "12"]) == 0
    text = (vocab / ".agents/memory/decisions/plans-live-in-git.md").read_text()
    assert 'status: "intent"' in text
    capsys.readouterr()

    assert cli.main(["memory", "find", "--kind", "decision", "--compact"]) == 0
    assert capsys.readouterr().out == "- plans-live-in-git · Plans live in git (intent: accepted, not built yet)\n"
    assert cli.main(["memory", "load"]) == 0
    assert "- plans-live-in-git · Plans live in git (intent: accepted, not built yet)" in capsys.readouterr().out

    assert cli.main(["memory", "implemented", "plans-live-in-git", "--ref", "14"]) == 0
    assert capsys.readouterr().out == "implemented .agents/memory/decisions/plans-live-in-git.md\n"
    text = (vocab / ".agents/memory/decisions/plans-live-in-git.md").read_text()
    assert 'status: "active"' in text and "_Implemented " in text and "(14)_" in text
    assert cli.main(["memory", "find", "--kind", "decision", "--compact"]) == 0
    assert capsys.readouterr().out == "- plans-live-in-git · Plans live in git\n"

    assert cli.main(["memory", "implemented", "plans-live-in-git"]) == 1
    assert "plans-live-in-git is active, not intent" in capsys.readouterr().err


def test_only_a_decision_can_be_intent(vocab, tmp_path, capsys):
    args = ["memory", "add", "gotcha", "--title", "Flux hangs", "--tags", "flux", "--body-file", body(tmp_path, "x\n")]
    assert cli.main([*args, "--intent"]) == 1
    assert "only a decision can be intent" in capsys.readouterr().err
    line = json.dumps({"kind": "gotcha", "title": "Flux hangs", "tags": ["flux"], "status": "intent"})
    assert cli.main(["memory", "import", "--json", body(tmp_path, line + "\n")]) == 1
    assert "only a decision can be intent" in capsys.readouterr().err


def test_import_validates_everything_before_writing(vocab, capsys):
    lines = [
        {
            "kind": "gotcha",
            "title": "Bootstrap fails with host parse error",
            "tags": ["talos"],
            "aliases": ["1"],
            "date": "2026-01-02",
            "sections": {"Symptom": "fails", "Cause": "inventory", "Fix": "add the host"},
        },
        {
            "kind": "decision",
            "title": "GitOps engine: Flux CD, not ArgoCD",
            "tags": ["flux"],
            "aliases": ["D15"],
            "body": "See phase 02.",
        },
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
    (gotchas / "a.md").write_text(
        '---\ntitle: "A"\ntags: ["ghost"]\nstatus: "retired"\nsuperseded_by: "zz"\naliases: ["7"]\n---\n\nx\n'
    )
    (gotchas / "b.md").write_text('---\ntitle: "B"\ntags: ["flux"]\nstatus: "active"\naliases: ["7"]\n---\n\ny\n')
    results = doctor.check_memory(load())
    assert ("fail", "memory: unknown tags on a (ghost)") in results
    assert ("fail", "memory: superseded_by points nowhere in a") in results
    assert ("fail", "memory: aliases claimed twice: 7 (a, b)") in results
    with pytest.raises(AwError, match="claimed by a, b"):
        memory.resolve(load(), "7")


def test_import_refuses_unsafe_slugs_and_never_overwrites(vocab, tmp_path, capsys):
    escaped = tmp_path / "escaped"
    assert memory.add(load(), "decision", "Plans live in git", "Original.\n", [], None)
    original = (vocab / ".agents/memory/decisions/plans-live-in-git.md").read_text()
    lines = [
        {"kind": "decision", "title": "Absolute", "slug": str(escaped)},
        {"kind": "decision", "title": "Relative", "slug": "../../outside"},
        {"kind": "decision", "title": "Plans live in git", "body": "Overwritten."},
        {"kind": "gotcha", "title": "Sections as a list", "tags": ["flux"], "sections": ["Symptom"]},
    ]
    path = vocab / "import.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    assert cli.main(["memory", "import", "--json", str(path)]) == 1
    err = capsys.readouterr().err
    assert "nothing written" in err
    assert "line 1: slug" in err and "line 2: slug" in err
    assert "plans-live-in-git exists" in err
    assert "line 4:" in err  # a malformed field is a refusal, not a traceback
    assert not escaped.with_suffix(".md").exists()
    assert not (vocab.parent / "outside.md").exists()
    assert (vocab / ".agents/memory/decisions/plans-live-in-git.md").read_text() == original


def test_slugs_are_unique_across_decisions_and_gotchas(vocab, tmp_path, capsys):
    assert add(tmp_path, "decision", "Flux owns deploys", "x\n") == 0
    assert add(tmp_path, "gotcha", "Flux owns deploys", "y\n", "flux") == 1
    assert "flux-owns-deploys exists as a decision" in capsys.readouterr().err

    path = vocab / "import.jsonl"
    path.write_text(json.dumps({"kind": "gotcha", "title": "Flux owns deploys", "tags": ["flux"]}) + "\n")
    assert cli.main(["memory", "import", "--json", str(path)]) == 1
    assert "flux-owns-deploys exists" in capsys.readouterr().err

    gotchas = vocab / ".agents/memory/gotchas"
    gotchas.mkdir(parents=True, exist_ok=True)
    (gotchas / "flux-owns-deploys.md").write_text('---\ntitle: "Hand-made clash"\ntags: ["flux"]\n---\n\nz\n')
    with pytest.raises(AwError, match="flux-owns-deploys is both a decision and a gotcha"):
        memory.resolve(load(), "flux-owns-deploys")
    (vocab / ".agents/aw.toml").write_text("aw_version = 1\n")
    assert ("fail", "memory: slugs used by a decision and a gotcha: flux-owns-deploys") in doctor.check_memory(load())


# --- malformed records name the file and the field ------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("tags: [flux, sops]", 'tags must be a JSON list of strings, like ["git", "gh"]'),
        ('tags: "flux"', 'tags must be a JSON list of strings, like ["git", "gh"]'),
        ('status: "gone"', "status must be one of active, intent, retired"),
        ("title: 12", "title must be a string"),
        ('aliases: [{"n": 1}]', "aliases must be a JSON list of strings"),
        ('superseded_by: ["other"]', "superseded_by must be a string"),
    ],
)
def test_a_malformed_entry_names_its_file_and_field(vocab, capsys, line, message):
    gotchas = vocab / ".agents/memory/gotchas"
    gotchas.mkdir()
    head = {"title": 'title: "Odd entry"', "tags": 'tags: ["flux"]', "status": 'status: "active"'}
    head[line.split(":")[0]] = line
    (gotchas / "odd-entry.md").write_text("---\n" + "\n".join(head.values()) + "\n---\n\nBody.\n")
    (gotchas / "sound-entry.md").write_text('---\ntitle: "Sound entry"\ntags: ["flux"]\n---\n\nBody.\n')
    assert cli.main(["memory", "find", "--tags", "flux", "--compact"]) == 0
    out, err = capsys.readouterr()
    assert "sound-entry" in out and "odd-entry" not in out
    assert f"warning: skipped {gotchas / 'odd-entry.md'}" in err and message in err
    assert cli.main(["memory", "load"]) == 0
    assert "Sound entry" in capsys.readouterr().out
    assert cli.main(["memory", "show", "sound-entry"]) == 0
    capsys.readouterr()
    assert cli.main(["memory", "show", "odd-entry"]) == 1
    err = capsys.readouterr().err
    assert str(gotchas / "odd-entry.md") in err and message in err
    assert doctor.check_memory(load())[0][0] == "fail"


def test_an_imported_line_meets_the_same_rules_as_a_file(vocab, capsys):
    path = vocab / "import.jsonl"
    path.write_text(json.dumps({"kind": "gotcha", "title": "Split tags", "tags": "flux"}) + "\n")
    assert cli.main(["memory", "import", "--json", str(path)]) == 1
    assert 'line 1: tags must be a JSON list of strings, like ["git", "gh"]' in capsys.readouterr().err
    assert not (vocab / ".agents/memory/gotchas").exists()
