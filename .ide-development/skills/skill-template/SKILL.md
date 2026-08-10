---
name: skill-template
description: Golden template for IDE Development skills. Use when creating or refactoring shared core skills.
version: 1.0.0
status: template
tags: [template, skills, progressive-disclosure]
source_adapted_from:
  - LiNKskills/skills/skill-template
---

# Skill Template

Use this template when creating or refactoring skills for the IDE Development core.

The template keeps the useful structure from the LiNKskills golden template, but aligns it to this system's artifact model:

`INTENT -> PROGRAM -> MODULE -> PHASE -> ISSUE -> PROOF -> REVIEW -> INTEGRATION`

## Frontmatter

Required:

- `name`
- `description`
- `version`
- `status`
- `tags`

Optional:

- `source_adapted_from`
- `related_templates`
- `related_commands`
- `related_agents`
- `permissions`
- `dependencies`

## Use When

- state the exact trigger for this skill
- prefer concrete situations over broad categories
- include exclusions where the skill should not be used

## Inputs

- current user request
- relevant artifact path, if any
- required repository state
- required external context, if any

## Outputs

- specific artifact, decision, code change, report, proof, review, or integration output
- explicit blocker if the skill cannot complete safely

## Decision Path

1. Confirm the task matches this skill.
2. Load only the relevant index and artifacts.
3. Check whether the work is greenfield, planned, issue-ready, review-ready, or integration-ready.
4. Route to the smallest viable workflow.
5. Stop or escalate if the required inputs are missing.

## Rules

### Scope In

- list the work this skill is allowed to guide

### Scope Out

- list prohibited work, side effects, and assumptions

### Evidence Standard

- define what counts as proof
- distinguish verified facts from assumptions
- state which tests, checks, screenshots, logs, or artifacts are expected

### Blocker Standard

- stop only for a genuine blocker
- record attempted work and the exact missing decision, dependency, or failed gate

## Workflow

### Phase 1: Intake

- identify the active artifact level
- gather only required context
- confirm acceptance criteria or definition of done

### Phase 2: Execution

- perform the smallest coherent unit of work
- preserve issue atomicity
- avoid unrelated refactors

### Phase 3: Proof

- map each acceptance criterion to evidence
- record test commands and outcomes
- record any assumptions or gaps

### Phase 4: Review

- evaluate scope compliance, proof sufficiency, and regression risk
- produce a pass, fail, or blocked verdict

### Phase 5: Integration

- record accepted outputs and downstream readiness effects
- mark `done` only after proof, passing review, and integration

## Progressive Disclosure

Read only:

1. this skill
2. the relevant `.cursor` or `core` index
3. the active artifact
4. directly referenced proof, review, integration, or dependency artifacts

Do not scan unrelated modules, phases, issue trees, reports, or historical material unless the active artifact requires it.

## References

Use optional local subfolders only when useful:

- `examples/`
- `references/`
- `scripts/`

Supporting files must not override the core doctrine.
