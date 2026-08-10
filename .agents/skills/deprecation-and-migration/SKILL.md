---
name: deprecation-and-migration
description: Migrate, archive, or retire old systems safely while preserving compatibility and rollback paths.
version: 1.0.0
status: active
tags: [migration, deprecation, compatibility, cleanup]
source_adapted_from:
  - addyosmani/agent-skills/skills/deprecation-and-migration
---

# Deprecation And Migration

Use this skill when replacing, archiving, renaming, or retiring existing commands, artifacts, APIs, workflows, or compatibility surfaces.

## Migration Checklist

- current users or references are identified
- replacement path is clear
- compatibility requirements are explicit
- old path is archived or marked legacy before removal
- rollback path exists when risk justifies it
- docs and indexes are updated
- verification confirms old references still behave as intended or fail clearly

## Rules

- Prefer archive-in-place before physical moves when compatibility risk is unknown.
- Do not delete legacy surfaces until references are audited.
- Mark deprecated paths clearly.
- Avoid creating duplicate active sources of truth.
- Record migration decisions in a report when future operators need context.

## Output

- migration plan
- affected references
- compatibility decision
- files changed
- verification steps
- remaining cleanup

## Progressive Disclosure

Read index files, direct references, and affected artifacts. Do not scan unrelated history unless reference ownership is unclear.
