---
name: lint-and-validate
description: Run focused static checks, builds, type checks, tests, and artifact validation after changes.
version: 1.0.0
status: active
tags: [lint, validation, build, verification]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/lint-and-validate
---

# Lint And Validate

Use this skill after modifying code, configuration, documentation structure, or shared artifacts.

## Validation Order

1. Identify the changed surface.
2. Find the repo's existing validation commands.
3. Run the smallest relevant check first.
4. Expand to broader checks when risk or failures require it.
5. Record commands and outcomes in proof.

## Common Checks

- formatter check
- linter
- type checker
- unit tests
- integration tests
- build
- markdown or schema validation
- link/path checks for documentation systems

## Rules

- Prefer existing project scripts over invented commands.
- Do not run expensive full-suite checks when a focused check is sufficient unless risk justifies it.
- If a command fails, capture the failure and decide whether it is caused by the current work.
- Do not hide unrelated pre-existing failures; label them clearly.
- If validation cannot run, explain the missing dependency or environment.

## Output

- commands run
- pass/fail result
- failure cause, if any
- skipped checks and reason
- proof-ready verification summary

## Progressive Disclosure

Read package scripts, project config, and changed file context. Do not inspect unrelated tooling unless validation cannot be discovered.
