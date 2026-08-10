---
name: python-patterns
description: Apply practical Python project, typing, async, testing, and packaging patterns.
version: 1.0.0
status: active
tags: [python, backend, scripts, testing]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/python-patterns
---

# Python Patterns

Use this skill when writing or reviewing Python code, scripts, tests, or service components.

## Rules

- Follow the existing project structure and style.
- Prefer clear functions and typed boundaries where useful.
- Keep scripts deterministic and CLI-friendly.
- Handle errors explicitly.
- Avoid broad dependency additions for small scripts.
- Use virtual environment or project tooling conventions already present.

## Checklist

- inputs are validated
- filesystem paths are explicit
- output is structured when agents consume it
- tests cover meaningful behavior
- exceptions are actionable
- no secrets are logged

## Proof

Useful evidence includes:

- unit test result
- script sample run
- type check
- lint result
- error-path check

## Progressive Disclosure

Read nearby Python code, project config, and existing tests. Do not impose a new framework or package manager without architectural justification.
