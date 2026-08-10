---
name: database-design
description: Design and review schemas, migrations, indexes, data access, and database safety.
version: 1.0.0
status: active
tags: [database, schema, migrations, indexes, data]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/database-design
---

# Database Design

Use this skill when changing database schemas, migrations, queries, indexes, or persistence contracts.

## Use When

- adding or changing tables
- writing migrations
- modifying indexes
- changing query patterns
- introducing new data relationships
- reviewing data integrity or performance risk

## Design Checklist

- entity ownership is clear
- constraints protect expected invariants
- migration is reversible or rollback-safe where practical
- indexes match query patterns
- access control and tenant boundaries are preserved
- seed/test data is intentional
- data compatibility is considered for existing records

## Rules

- Prefer existing migration conventions.
- Do not silently drop or rewrite data.
- Do not add indexes without a query reason.
- Avoid mixing unrelated schema changes.
- Include tests or validation for data behavior when possible.
- Surface destructive or irreversible changes as gates.

## Proof

Evidence may include:

- migration applied locally
- schema diff
- query test
- integration test
- explain plan or performance note
- rollback note

## Progressive Disclosure

Read relevant schema, migrations, models, and data access code. Do not inspect unrelated database areas unless dependencies require it.
