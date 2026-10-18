---
title: "An unquoted ' #' in SKILL.md frontmatter cuts the value as a YAML comment"
tags: ["skills", "yaml"]
status: "active"
date: "2026-10-18"
---

## Symptom

A skill's description ends early in Claude Code's skill list and in `npx skills add --list`: `aw-plan-story` stopped at `Use when the user says "plan story", "plan issue`.

## Cause

Frontmatter is YAML. In an unquoted (plain) value, a space followed by `#` starts a comment, so `"plan issue #N"` cut everything after it. `: ` in a plain value is a mapping error the same way. `aw doctor` read the line whole and saw nothing wrong.

## Fix

Quote a frontmatter value that contains ` #` or `: ` (single quotes; double any `'` inside). `aw doctor` now fails such unquoted values, and a test holds every bundled skill to it.
