---
name: code-simplification
description: Simplify code or documentation while preserving behavior, proof, and compatibility.
version: 1.0.0
status: active
tags: [refactor, simplification, maintainability, clarity]
source_adapted_from:
  - addyosmani/agent-skills/skills/code-simplification
  - link-antigravity-kit/.codex/skills/clean-code
---

# Code Simplification

Use this skill when existing code or artifacts work but are harder to understand, maintain, or verify than needed.

## Use When

- removing unnecessary complexity
- reducing duplication
- clarifying names or structure
- simplifying docs or workflows
- refactoring without behavior change

## Rules

- Preserve behavior unless the issue explicitly changes it.
- Make one coherent simplification at a time.
- Do not combine simplification with unrelated feature work.
- Keep compatibility surfaces stable unless migration is explicit.
- Verify before and after behavior when code changes.

## Simplification Checks

- Can this be expressed with fewer moving parts?
- Is the abstraction earning its cost?
- Is duplication meaningful or accidental?
- Does the change make proof/review easier?
- Does it reduce future agent confusion?

## Output

- behavior-preservation statement
- simplification made
- verification performed
- residual compatibility risk

## Progressive Disclosure

Read the target code or artifact and nearby callers/references. Do not refactor across layers unless the issue requires it.
