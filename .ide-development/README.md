# Managed Core (v2.2 package source)

**Status:** v2.2 streamlined-delivery package surface
**Package version:** see `VERSION`
**Contract:** `docs/contracts/MANAGED-CORE-V2.md`
**ADR:** `docs/adr/0004-portable-managed-core-v2.md`

## Purpose

`core/managed-core/` is the **system-source package root** for the portable IDE Development v2 managed core, including the shared streamlined-delivery coordinator interfaces.

When installed into a consumer repository, the committed package root is `.ide-development/`.
This directory is the authoring source inside the IDE Development system repository. It is **not** a nested install of IDE Development into itself.

## Layout

```text
core/managed-core/
  README.md                 # this file
  INDEX.yaml                # discovery index
  VERSION                   # package semver (2.2.0 target)
  MANIFEST.json             # live install set (built by scripts/ide_development/build_manifest.py)
  schemas/                  # authoritative JSON Schemas
  examples/                 # minimal valid examples for focused validation
  content/                  # managed content payload (doctrine/skills/…)
  skills/                   # approved shared skills mirrored for packaging
  platforms/                # platform adapter sources (Cursor / Codex)
  migrations/               # reviewed supersession catalog (canonical)
  migration/                # discovery alias pointer only (no catalog duplicate)
```

### Consumer materialization (normative)

| Source (system) | Destination (consumer) |
|---|---|
| `core/managed-core/VERSION` | `.ide-development/VERSION` |
| package manifest (`files[]`) | `.ide-development/MANIFEST.json` |
| `core/managed-core/content/**` | `.ide-development/content/**` |
| `core/managed-core/platforms/**` | `.ide-development/platforms/**` plus declared discovery paths |
| declared Codex skills | `.agents/skills/<name>/SKILL.md` (physical) |
| declared Cursor entrypoints | `.cursor/rules|commands|skills/...` (physical) |
| managed AGENTS section | root `AGENTS.md` marker block |
| installed-state | `.ide-development/installed-state.json` (committed) |
| transactions / backups | `.git/ide-development/` (Git-local only) |

## Ownership boundaries (Wave 1 packets)

| Path | Owner |
|---|---|
| `core/managed-core/` layout, schemas, examples, architecture docs | WP1 |
| `core/managed-core/platforms/**` adapter bodies | WP3 |
| `core/managed-core/migrations/**` catalog entries | WP4 |
| installer engine reading these schemas | WP2 |
| external protection plan/apply/verify | WP5 |
| top-level operator docs / VERSION product file | WP6 |

## Hard rules

- Physical files by default; no absolute/external/checkout-to-checkout symlinks.
- No credentials, tokens, or absolute host checkout paths in package payloads.
- No Claude / `.claude` / root `CLAUDE.md` surfaces in this package.
- Unknown conflicts fail closed.
- Supersession removals require exact reviewed identity + hash match.

## Read next

1. `docs/contracts/MANAGED-CORE-V2.md`
2. `schemas/manifest.schema.json`
3. `schemas/installed-state.schema.json`
4. `schemas/transaction.schema.json`
5. `examples/`
