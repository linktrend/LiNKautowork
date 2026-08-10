---
name: repository-manager
description: Manage repository hygiene, handoffs, artifact placement, and safe workspace organization.
version: 1.0.0
status: active
tags: [repository, hygiene, handoff, workspace]
source_adapted_from:
  - LiNKskills/skills/repository-manager
---

# Repository Manager

Use this skill when a task changes repository structure, shared artifacts, branches, handoffs, or installation state.

## Use When

- adding or moving core artifacts
- updating indexes or catalogs
- preparing session handoff material
- checking workspace adoption state
- deciding where a new file belongs
- cleaning compatibility or legacy surfaces

## Rules

1. Keep canonical knowledge in `core/`.
2. Preserve `.cursor/` compatibility paths.
3. Prefer updating existing indexes over creating parallel navigation.
4. Keep historical design and audit reports under `docs/archive/core-reports/`.
5. Keep session handoffs under `docs/handoff/`.
6. Do not duplicate shared runtime content into consumer repositories when symlinks are intended.
7. Record protective cleanup decisions in a report when they affect future operators.

## Hygiene Checklist

- Is the file in the right layer?
- Is the layer indexed if it needs discovery?
- Does the change preserve progressive disclosure?
- Does it introduce duplicate source of truth?
- Does it break `.cursor/...` references?
- Does it need a report or changelog note?

## Output

- placement decision
- files changed
- index/catalog updates
- compatibility notes
- unresolved cleanup questions

## Progressive Disclosure

Read the nearest README or INDEX for the affected layer, then the files being changed. Avoid scanning the whole repository unless placement is genuinely unclear.
