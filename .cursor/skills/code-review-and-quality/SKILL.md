---
name: code-review-and-quality
description: Review changes for correctness, maintainability, scope compliance, security, tests, and proof sufficiency.
version: 1.0.0
status: active
tags: [review, quality, proof, maintainability]
source_adapted_from:
  - addyosmani/agent-skills/skills/code-review-and-quality
  - link-antigravity-kit/.codex/skills/code-review-checklist
---

# Code Review And Quality

Use this skill before integration or when asked to review a change.

## Review Axes

- scope compliance
- correctness
- tests and verification
- maintainability
- security and privacy
- performance risk
- compatibility
- documentation and handoff quality

## Review Workflow

1. Read the issue, acceptance criteria, and proof.
2. Inspect the diff or changed files.
3. Verify the proof actually supports the completion claim.
4. Check for regressions, missed edge cases, and unnecessary scope expansion.
5. Produce findings ordered by severity.
6. Give a verdict: `pass`, `fail`, or `blocked`.

## Rules

- Findings must be concrete and file-specific when code is involved.
- Do not fail a review for stylistic preference unless it affects maintainability or standards.
- Do not pass unsupported completion claims.
- Do not treat passing tests as sufficient if acceptance criteria are not covered.
- A blocked verdict must name the missing evidence or unavailable input.

## Severity Guide

- `P0`: breaks core behavior, data safety, security, or release viability
- `P1`: likely user-facing bug or serious maintainability risk
- `P2`: important quality issue that should be fixed before completion
- `P3`: minor improvement or follow-up

## Output

- verdict
- findings
- missing proof, if any
- required rework
- residual risk

## Progressive Disclosure

Read the issue, proof, changed files, and directly relevant dependencies. Do not review unrelated code unless the diff creates a visible dependency or regression risk.
