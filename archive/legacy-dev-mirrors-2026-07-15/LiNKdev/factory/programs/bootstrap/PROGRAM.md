---
program_id: bootstrap
title: Build LiNKdev portable factory
status: complete
chairman_review_schedule:
  - after_wave: 4
---

# Program: bootstrap

Build `LiNKdev/` inside LiNKtrend-System through Wave 4. Bootstrap mode uses one-line launchers; runtime mode after wire.

## Module: factory — Phase: all waves

| Issue | Title | Runtime | Tier | Depends on | Parallel group |
|-------|-------|---------|------|------------|----------------|
| DS-001 | Scaffold LiNKdev tree | cursor | standard | [] | A |
| DS-003 | GitHub contracts and STATE schema | codex | standard | [] | A |
| DS-004 | Issue and report templates | codex | standard | [] | A |
| DS-002 | Skills allowlist and dedupe | cursor | standard | DS-001 | B |
| DS-005 | Install CHECKLIST and WIRE-PROMPT | cursor | standard | DS-001 | B |
| DS-011 | Complete SPEC.md | cursor | standard | DS-001 | C |
| DS-014 | Executor prompts cursor and codex | codex | standard | DS-011 | C |
| DS-015 | validate-dag.sh and proof | codex | standard | DS-004 | C |
| DS-016 | Bootstrap PROGRAM.md and index | cursor | standard | DS-011 | C |
| DS-012 | Planner prompt and program template | cursor | standard | DS-011 | D |
| DS-013 | Orchestrator Reviewer Integrator prompts | cursor | standard | DS-011 | D |
| DS-021 | Cursor automations docs | cursor | standard | DS-011 | E |
| DS-022 | Codex automations docs | codex | standard | DS-011 | E |
| DS-023 | GitHub LiNKdev-guard workflow | codex | standard | DS-003 | E |
| DS-024 | Planner automation checklist in install | cursor | standard | DS-005, DS-021 | G |
| DS-031 | verify.sh mechanical verify | codex | standard | DS-001 | F |
| DS-033 | Reviewer vacuous PASS rules | cursor | standard | DS-013 | F |
| DS-034 | proof-manifest.sh | codex | standard | DS-004 | F |
| DS-032 | merge-ready policy in prompts | cursor | standard | DS-013, DS-031 | G |
| DS-041 | Root AGENTS.md portable layer | codex | standard | DS-011 | H |
| DS-042 | Report trajectory section | codex | standard | DS-004 | H |
| DS-045 | Benchmark stub and sandbox doc | codex | standard | DS-021 | H |
| DS-043 | Dry-run E2E proof | cursor | standard | DS-021, DS-022, DS-031 | I |
| DS-044 | linktrend program stub and migration | cursor | standard | DS-016 | I |
| DS-046 | Integrator final bootstrap complete | cursor | standard | DS-043 | I |

## Parallel groups

- **A:** DS-001, DS-003, DS-004
- **B:** DS-002, DS-005
- **C:** DS-011, DS-014, DS-015, DS-016
- **D:** DS-012, DS-013
- **E:** DS-021, DS-022, DS-023
- **F:** DS-031, DS-033, DS-034
- **G:** DS-024, DS-032
- **H:** DS-041, DS-042, DS-045
- **I:** DS-043, DS-044, DS-046

## Codex automation checklist

| Issue | Trigger labels | Automation name |
|-------|----------------|-----------------|
| DS-003 | linkdev:ready, runtime:codex | LiNKdev-codex-executor |
| DS-004 | linkdev:ready, runtime:codex | LiNKdev-codex-executor |
| DS-014 | linkdev:ready, runtime:codex | LiNKdev-codex-executor |
| DS-015 | linkdev:ready, runtime:codex | LiNKdev-codex-executor |
| DS-022 | linkdev:ready, runtime:codex | LiNKdev-codex-executor |
| DS-023 | linkdev:ready, runtime:codex | LiNKdev-codex-executor |
| DS-031 | linkdev:ready, runtime:codex | LiNKdev-codex-executor |
| DS-034 | linkdev:ready, runtime:codex | LiNKdev-codex-executor |
| DS-041 | linkdev:ready, runtime:codex | LiNKdev-codex-executor |
| DS-042 | linkdev:ready, runtime:codex | LiNKdev-codex-executor |
| DS-045 | linkdev:ready, runtime:codex | LiNKdev-codex-executor |

## Cursor automation checklist

| Role | Trigger | Automation name |
|------|---------|-----------------|
| Orchestrator | merge to development | LiNKdev-orchestrator |
| Reviewer | linkdev:review-ready | LiNKdev-reviewer |
| Integrator | linkdev:merge-ready | LiNKdev-integrator |
| Executor | linkdev:ready + runtime:cursor | LiNKdev-executor-cursor |

## Issue index

All specs: `LiNKdev/factory/programs/bootstrap/issues/`  
All prompts: `LiNKdev/factory/programs/bootstrap/prompts/`  
One-line launchers: `LiNKdev/factory/programs/bootstrap/LAUNCHERS.md`
