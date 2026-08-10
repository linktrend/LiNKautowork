---
name: parallel-agents
description: Coordinate safe parallel work only when issue dependencies, scope boundaries, and review capacity allow it.
version: 1.0.0
status: active
tags: [parallelism, agents, dependencies, orchestration]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/parallel-agents
---

# Parallel Agents

Use this skill when considering concurrent agent work.

## Eligibility

Parallel work is allowed only when:

- issues are independently ready
- no selected issue depends on another selected issue's not-yet-integrated output
- file and artifact overlap is low or manageable
- review and integration can keep up
- rollback or conflict handling is clear

## Rules

- Dependencies determine concurrency, not agent availability.
- Do not parallelize work that touches the same fragile surface without a coordination plan.
- Each parallel unit must produce its own proof.
- Review and integration remain distinct gates.
- Recompute downstream readiness after integration.

## Coordination Checklist

- ready issue set
- file/artifact ownership
- expected outputs per unit
- proof requirements per unit
- merge/integration order
- conflict handling

## Output

- approved parallel units or denial reason
- assignment recommendation
- shared-risk notes
- integration order

## Progressive Disclosure

Read the module, phase, and issue dependency graph. Do not inspect unrelated issues outside the candidate ready set.
