---
name: aw-merge-request
license: MIT (see LICENSE)
description: Write and open the merge request (pull request) for the current branch - follow the project's contribution rules and merge request template, shape the content to show the change at a glance, and create or update it through aw. Used by aw-finalize and aw-checkpoint; use when the user says "open a PR", "merge request", "MR", "write the PR description".
allowed-tools: Bash(~/.agents/bin/aw config) Bash(~/.agents/bin/aw session) Bash(~/.agents/bin/aw template mr) Bash(~/.agents/bin/aw issue ref:*) Bash(~/.agents/bin/aw mr create:*) Bash(~/.agents/bin/aw mr update:*) Bash(~/.agents/bin/aw mr view:*)
metadata:
  package: agentic-workflows
  source: https://github.com/mattpocock/skills/tree/e484a8095543718ced436b9b49a8160ed4554000/skills/engineering/pr
  credits: the Sections style is adapted from mattpocock/skills `pr`, which credits Dex Horthy's show-me skill (humanlayer/skills)
---

# Merge request

Request: $ARGUMENTS

One merge request for the current branch: its title and description, created or updated through `aw mr`. GitHub calls it a pull request; the commands are the same.

## 1. Load settings and the change

```bash
~/.agents/bin/aw config
~/.agents/bin/aw session      # gives the issue; fails outside a session, then there is none
```

- `forge = none` → there is no merge request; say so and stop.
- The change: `git diff <main_branch>...HEAD --stat` and the diff itself, plus the commit messages. Called from `/aw-finalize`, reuse its summary of what changed and why.
- The branch is pushed and has no unpushed commits; `aw mr create` refuses otherwise.

## 2. Read the rules, then the template

What decides the content, strongest first:

1. **Rules**: `contributing_file` (default `CONTRIBUTING.md`), when it exists: title format, required sections, checklists, labels, reviewers, draft policy. Also what `instructions_file` says about merge requests. Rules win over everything below.
2. **Template**: the sections to fill.

   ```bash
   ~/.agents/bin/aw template mr      # stderr names the source
   ```

   It is `templates.mr` when set, else the forge's own template (`mr_template` names one in `.gitlab/merge_request_templates/` or `.github/PULL_REQUEST_TEMPLATE/`; unset, GitLab's `Default.md` or GitHub's `pull_request_template.md`), else the bundled Summary / Evidence / Merge danger. Keep every section and checklist of the template, in its order. Fill each one; a section that does not apply says why in a line instead of disappearing.
3. **Style**: the [Sections](#sections) guidance below, for the content inside the template's sections.

## 3. Title

- The rules' format; without one, a conventional-commit style summary of the outcome (`feat: …`, `fix: …`), as for the main commit.
- With an issue on a tracker that links by key (Jira), put `aw issue ref <issue>` in the title.

## 4. Body

Fill the template following [Sections](#sections). Do not add the issue's closing line, a part reference or the list of earlier parts yourself: `aw mr create` appends them (`pr_close_keyword`, e.g. `Fixes #12`).

## 5. Create or update

```bash
~/.agents/bin/aw mr create --title "<title>" --body-file - [--draft] [--part] --dry-run
~/.agents/bin/aw mr create --title "<title>" --body-file - [--draft] [--part]
```

- Standalone: show the title and body and wait for a go before the real create. From `/aw-finalize` or `/aw-checkpoint`: create directly; the merge gate comes later.
- One part of a multi-merge session (from `/aw-checkpoint`): `--part`. The request then references the issue as `Refs #12 (part N)` instead of closing it; the dry run prints N. Add ` (part N)` to the title unless the rules define titles. Without `--part`, after earlier parts, `aw mr create` lists them (`Earlier parts: #314, #315`) and closes the issue.
- `--draft` when the rules ask for it, or the work is not ready for review.
- `already open` → this branch has a merge request. Show the old and new description and update it on a go: `~/.agents/bin/aw mr update --title "<title>" --body-file -` (`--dry-run` first).
- Print the merge request link.

## Sections

Skip all preambles and keep prose brief. Use the project's domain language (`GLOSSARY.md`, when there is one). These shape the bundled template; with another template, apply them inside its sections (its "Description" or "What does this MR do" is the Summary, its "How to test" is the Evidence, its "Risks" is the Merge danger).

### Summary

Pick the smallest view that makes the key point clear.

- Logic or an algorithm as pseudocode:

  ```text
  on(save)
    if content is unchanged
      return cached result
    write new content
    return fresh result
  ```

- Runtime control flow as a call tree:

  ```text
  submitForm
    createSession
      persistPrompt
      launchAgent
    navigateToSession
  ```

- UI structure as a component tree, with the state and module boundaries that matter.
- File responsibility or a broad refactor as a shallow file tree:

  ```text
  src/
  ├── commands/       # parses user actions
  ├── sessions/       # owns session state
  └── transport/      # sends API requests
  ```

- Component interaction, control flow or data flow as Mermaid (`sequenceDiagram`, `flowchart`).
- A `diff` when the point is what changes and the surrounding shape already exists. Match the diff's shape to the topic: a component tree, a file layout, a call tree, a state change:

  ```diff
   on(save)
  -  write content
  +  if content is unchanged
  +    return cached result
  +  write new content
  +  invalidate cache
  ```

- The whole block when most of it is new, when omitted context would hide ownership or order, or when the reader needs a copyable target shape.

Place each visual next to the short text it supports. Keep only the calls, files, props, states and boundaries the reader needs. Use one view, sometimes several, rarely all; do not overwhelm.

### Evidence

Concrete proof that the change works, as a before and after.

- Screenshots are best, when the change is visual and the environment can take them.
- Execution next: test results, console output. Name the exact test that failed before and passes now, in pseudocode when the test itself is long.
- `aw verify` passing is the floor, not the evidence; say what it covers only when that is the point.

### Merge danger

- **Door**: one-way or two-way. A two-way door can be walked back: a change that is cheap to roll back is lower risk. Destructive actions, data migrations, published interfaces and other hard-to-reverse decisions are one-way doors.
- **Blast radius**: the potential impact, in one word, then what could break and for whom: consumers, deploys, data, layout, other teams. Consider all of it, write only what applies.
- A merge that deploys (GitOps, release on merge) says so here.

## Rules

- At most one open merge request per branch; a multi-merge session opens the next part only after the previous one merged.
- No secret values in titles, descriptions or comments.
- Never merge from this skill; merging is behind the gate of `/aw-finalize` (`aw finish`) or `/aw-checkpoint` (`aw merge`).
