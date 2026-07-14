---
id: PR-000
title: Example issue title
runtime: cursor
tier: standard
module: example-module
phase: example-phase
depends_on: []
allowed_files:
  - path/to/allowed/**
prohibited_files:
  - .env
  - "**/secrets/**"
  - LiNKdev/archive/**
read_first:
  - LiNKdev/factory/SPEC.md
  - LiNKdev/product/programs/<program-id>/modules/<module-id>/phases/<phase-id>/issues/PR-000.md
proof_required:
  - "git status --short is clean except documented exclusions"
  - "Report updated with proof block (DS-B5)"
acceptance_criteria:
  - Criterion is testable and observable
  - All allowed paths respected
read_forbidden:
  - LiNKdev/product/reports/**
  - LiNKdev/product/grounding/**
  - LiNKdev/archive/**
  - LiNKdev/skills/**
report_path: LiNKdev/product/reports/<program-id>/<module-id>/<phase-id>/PR-000.md
prompt_path: LiNKdev/product/programs/<program-id>/modules/<module-id>/phases/<phase-id>/prompts/PR-000.prompt.md
---

# PR-000 — Example issue title

## Objective

One paragraph: what this issue must achieve.

## Steps

1. Step one
2. Step two

## Acceptance criteria

- [ ] Criterion is testable and observable
- [ ] All allowed paths respected

## Proof required

| Command | Expected |
|---------|----------|
| `LiNKdev/factory/scripts/verify.sh` | Exit 0 |
| `git status --short` | Clean except documented exclusions |

## Handoff

- Commit on issue branch; push
- Update report at path in `report_path` frontmatter only
- Do not set `linkdev:merge-ready` until verify exits 0
- Commit message includes issue id: `feat(scope): summary (PR-000)`
