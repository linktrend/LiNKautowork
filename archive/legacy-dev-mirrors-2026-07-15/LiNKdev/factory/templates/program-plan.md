---
program_id: example-program
title: Example Program
status: draft
chairman_review_schedule:
  - after_wave: 1
---

# Program plan: Example Program

## Finished product (plain English)

Written after Principal Go Q&A. Describe what the product **does**, how it **behaves**, and what users **see** when **all issues in this program** are complete. Not a file tree.

## Program Definition of Done (DS-B14)

- [ ] All issues `done` in STATE
- [ ] Release phase critical issues passed verify + proof manifest
- [ ] `LiNKdev/product/grounding/SHIP_CRITERIA.md` satisfied
- [ ] Demo evidence path recorded in `LiNKdev/product/reports/<program-id>/STATUS.md`
- [ ] Principal Release OK recorded (staging/main remain Principal-only)

## Modules

### example-module — Module title

**README:** `modules/example-module/README.md` (5–15 lines: goal, out of scope)

#### Phase 1 — Phase title

| Issue | Title | Runtime | Tier | Depends on | Parallel group |
|-------|-------|---------|------|------------|----------------|
| PR-001 | … | cursor | standard | [] | A |

### release — Ship

#### Phase ship — Release

| Issue | Title | Runtime | Tier | Depends on | Parallel group |
|-------|-------|---------|------|------------|----------------|
| PR-900 | Program release verify | cursor | critical | [all module issues] | — |

## Parallel groups

- **A:** PR-001, PR-003
- **B:** PR-002 (after PR-001)

## Active wave cap

Orchestrator sets at most **3** concurrent `linkdev:ready` issues (adjust per Principal).

## Codex automation checklist

| Issue | Trigger labels | Paths filter | Automation name |
|-------|----------------|--------------|-----------------|
| PR-003 | `linkdev:ready`, `runtime:codex` | `LiNKdev/factory/contracts/**` | LiNKdev-codex-example |

## Cursor automation checklist

| Role | Trigger | Automation name |
|------|---------|-----------------|
| Orchestrator | Merge to `development` | LiNKdev-orchestrator |
| Reviewer | `linkdev:review-ready` | LiNKdev-reviewer |
| Integrator | `linkdev:merge-ready` | LiNKdev-integrator |
| Executor (cursor) | `linkdev:ready`, `runtime:cursor` | LiNKdev-executor-cursor |

## DAG notes

`LiNKdev/factory/scripts/validate-dag.sh LiNKdev/product/programs/<program-id>/PROGRAM.md`
