# Migration catalog (Wave 1 / WP4)

Reviewed supersession catalog for IDE Development managed-core v2.

## Authority

- Contract: `docs/contracts/MANAGED-CORE-V2.md` (exact identity + hash removals; fail closed on mismatch)
- Installer loader (WP2): expects `schemaVersion: 1` and `entries[]` with `identity`, `path`, `contentHash`, `action: "remove"`
- This directory (`core/managed-core/migrations/`) is the Wave 1 packet-owned catalog root

## Layout

```text
migrations/
  README.md
  schema.json
  catalog.json
  scenarios.json
  known-bytes/          # reviewed exact bytes for supersession hashes
```

## Hard rules

1. Removals require **exact** `identity` and `contentHash` match.
2. Hash mismatch or unknown/modified content → **fail closed** (do not delete).
3. No absolute host paths, credentials, tokens, or secret values in catalog or known-bytes.
4. Catalog paths are repo-relative POSIX paths only (no `..`, no drive letters).
5. Symlink / sparse-GitOps / dirty-tree / rollback / idempotence behaviors are proven by black-box fixtures under `tests/managed-core-migration-bb/`; this catalog supplies exact-removal identities those fixtures exercise.
6. `scenarios.json` ids / `fixture` fields must match `tests/managed-core-migration-bb/fixtures/<id>/` directory names one-to-one (titles stay aligned with each fixture’s `scenario.json`).

## Related

- Black-box fixtures/tests: `tests/managed-core-migration-bb/`
- WP1 layout note: `core/managed-core/migration/` (singular) is a discovery alias pointer only — no duplicate catalog file
