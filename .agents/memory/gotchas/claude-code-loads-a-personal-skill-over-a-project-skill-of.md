---
title: "Claude Code loads a personal skill over a project skill of the same name"
tags: ["claude-code", "skills"]
status: "active"
date: "2026-10-18"
---

## Symptom

A skill copied into a project's `.claude/skills/<name>` does nothing on a machine where `aw install` ran: `/name` still runs the copy linked into `~/.claude/skills/<name>`.

## Cause

Claude Code resolves same-named skills enterprise over personal over project (code.claude.com/docs/en/skills, "Resolve skills that share a name", checked 2026-10-18). `aw install` links every skill into `~/.claude/skills`, and the skills call `~/.agents/bin/aw`, which only `aw install` creates: any machine that can run a vendored copy also shadows it.

## Fix

Do not vendor skills by copy while the global install exists; ship CLI and skills together in the package. A project-specific change to a skill needs another mechanism (backlog: "Project additions to skills"), not a same-named copy.
