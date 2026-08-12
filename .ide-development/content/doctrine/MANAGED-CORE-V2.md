# Managed Core v2 Contract

**Status:** Active (Wave 1 — Issue #43; WP1–WP03 complete for stated scopes; WP04 consumer rollout prepared / not executed — Issue #72 status surface)
**Date:** 2026-08-02
**Package version target:** `2.1.3` (identity only; no tag/release claimed by packaging alone — RC archive proof + authorized publication)
**ADR:** `docs/adr/0004-portable-managed-core-v2.md`
**Schemas:** `core/managed-core/schemas/`
**Layout:** `core/managed-core/README.md`
**Operator docs:** `SETUP.md` · `docs/runbooks/release-candidate.md` · `docs/runbooks/rollback.md` · `docs/acceptance/acceptance-matrix.md`

## Purpose

Define the portable managed-core architecture contracts that all Wave 1 implementers (installer, adapters, migration, protections, docs) must obey:

1. directory layout
2. manifest / installed-state / transaction schemas
3. precedence rules
4. conflict matrix and fail-closed behavior
5. external-state boundary
6. self-verification versus consumer rollout distinction

This contract does **not** implement the installer, adapters, migration catalog entries, or live GitHub mutations.

## Authority map

| Concern | Authority |
|---|---|
| Shared lifecycle doctrine and managed lifecycle rules | IDE Development managed core |
| Repository-specific technical guidance | Consumer repository (preserved) |
| File ownership and hashes | Package `MANIFEST.json` + installed-state |
| Mutation safety | Transaction plan + backups under `.git/ide-development/` |
| External GitHub settings | Separate plan/verify tooling (default **read-only / dry-run**; live apply is **Principal-gated** — WP2 closed IDE Development live readiness for its stated scope; consumer/external apply remains WP04 / approval-gated) |
| Secrets / credentials | Never packaged; GSM / approved stores only |
| Release candidate archives | `release-candidate create|verify` CLI; no GitHub tag/Release claimed unless separately approved |

## Installed layout (consumer repository)

```text
<repo>/
  .ide-development/                 # committed physical managed package (required)
    VERSION                         # package semver string, e.g. 2.1.3
    MANIFEST.json                   # installed package manifest (copy)
    installed-state.json            # committed installed hashes (portable verify)
    content/                        # managed doctrine/skills/templates/...
    platforms/                      # managed platform adapter sources
  AGENTS.md                         # consumer text + managed marker block
  .agents/skills/<name>/SKILL.md    # physical Codex discovery (when declared)
  .cursor/rules/                    # physical Cursor discovery (when declared)
  .cursor/commands/
  .cursor/skills/
  .git/ide-development/             # Git-local only (transactions / backups / lock)
    current-transaction/
    last-transaction/
    lock
```

Hard rules:

- Every managed file is a regular file by default (physical bytes).
- No absolute, external, or checkout-to-checkout symlinks.
- No installed path may resolve outside the consumer repository root.
- IDE Development (system repo) must not receive a nested `.ide-development/` install of itself (timeless; system source ≠ consumer).

## System source layout (`core/managed-core/`)

```text
core/managed-core/
  README.md
  INDEX.yaml
  VERSION
  schemas/
    manifest.schema.json
    installed-state.schema.json
    transaction.schema.json
  examples/
  content/                  # payload mirrored into consumer .ide-development/content
  platforms/                # Codex/Cursor adapter sources (Wave-1 ADR-0004 slice WP3 fills bodies)
  migrations/               # reviewed supersession catalog (Wave-1 ADR-0004 slice WP4)
  migration/                # discovery alias pointer only
```

## Manifest schema (summary)

Authoritative JSON Schema: `core/managed-core/schemas/manifest.schema.json`.

Top-level required fields:

| Field | Meaning |
|---|---|
| `schemaVersion` | Manifest schema major version (`1`) |
| `packageName` | Stable package id (`ide-development-managed-core`) |
| `packageVersion` | Semver package version (`2.1.3`) |
| `files` | Non-empty list of managed path entries |

Each `files[]` item requires:

| Field | Meaning |
|---|---|
| `id` | Stable entry id (used by installed-state and supersession links) |
| `ownershipClass` | Ownership class (see below) |
| `source` | Package-relative source path (POSIX `/` separators) |
| `sourceHash` | Hex SHA-256 of source bytes (`sha256:<hex>`) |
| `destination` | Repo-relative destination path |
| `mode` | POSIX file mode string (`0644`, `0755`) |
| `platform` | Discovery/runtime adapter scope |
| `mergeStrategy` | How collisions are handled |
| `os` | Optional OS filter (`all` default) |
| `supersessionIdentity` | Optional catalog identity for exact-hash removal |

### Ownership classes

| Class | Meaning |
|---|---|
| `managed` | Generic managed file; hash-tracked |
| `managed-core` | File inside committed `.ide-development/` package tree |
| `managed-entrypoint` | Native discovery surface (`.cursor/*`, `.agents/*`) |
| `managed-marker` | Region inside a consumer file delimited by fixed markers |
| `optional` | Managed when present in package; absence is not conflict |
| `consumer-preserve` | Never written by installer; documented only for conflict clarity |
| `external-state` | Outside Git working-tree mutation (GitHub settings); never stores secret values |

### Platforms (discovery scope)

`all` · `cursor` · `codex` · `github` · `none`

Claude / `.claude` / root `CLAUDE.md` are **not** valid platforms or destinations in v2.

### OS filter (optional)

`all` · `posix` · `windows` · `darwin` · `linux`

Use `os` for host applicability. Do not overload `platform` with OS names.

### Merge strategies

| Strategy | Behavior |
|---|---|
| `replace` | Replace destination bytes when ownership and conflict rules allow |
| `create-only` | Write only if destination absent; otherwise conflict if bytes differ from expected |
| `remove-if-matches` | Delete only when supersession identity + exact hash match |
| `marker-upsert` | Upsert only the delimited managed block; preserve text outside markers |
| `external-plan-only` | Produce/verify external plans; no Git working-tree secret writes |

### Managed markers (Codex / AGENTS.md)

```text
<!-- BEGIN LINKTREND-IDE-MANAGED -->
... managed block ...
<!-- END LINKTREND-IDE-MANAGED -->
```

Consumer text outside markers is preserved. Marker-pair corruption (begin without end, nested markers, multiple unmanaged collisions) is a fail-closed conflict.

## Installed-state schema (summary)

Authoritative JSON Schema: `core/managed-core/schemas/installed-state.schema.json`.

Committed path: `.ide-development/installed-state.json`.

Records:

- `packageVersion`
- `installedAt`
- `files` map: destination path → `{ id, sourceHash, contentHash, mode, ... }`

Committed installed-state lets clones verify without relying solely on Git-local metadata. Transaction backups remain under `.git/ide-development/`.

## Transaction schema (summary)

Authoritative JSON Schema: `core/managed-core/schemas/transaction.schema.json`.

Every mutating operation (`install`, `update`, `rollback`) must:

1. build a deterministic plan (`plan` / `--dry-run` writes no repo or Git metadata);
2. create a transaction record with ordered operations and pre-change backup map;
3. apply atomically per file (temp write + replace) with exact mode restoration;
4. update installed-state only after all operations succeed;
5. mark interrupted transactions recoverable; never leave silent partial success.

## Precedence rules

1. **Managed lifecycle wins when explicitly identified.** If a managed lifecycle rule is declared in the managed marker block, managed Cursor/Codex lifecycle entrypoints, or managed doctrine paths listed in the manifest, that rule governs shared lifecycle behavior (branching, ship/pull, completion, review packager, promotion roles).
2. **Consumer technical guidance remains.** Repository-owned architecture, product APIs, coding standards, and domain instructions outside managed ownership remain authoritative for that repository.
3. **Conflict requires an explicit managed lifecycle identity.** A consumer file is not overridden merely because it “looks similar.” Override/replace requires a manifest entry (or marker ownership) that names the destination.
4. **More specific consumer guidance may refine managed lifecycle** only when it does not contradict an explicit managed lifecycle rule (for example, additional test commands). Contradiction → fail closed or require human/Principal resolution; installer must not silently prefer consumer or managed bytes.
5. **External state does not override Git contracts.** Branch protection / ruleset tooling may union required checks, but must not delete legitimate repository-specific checks or package secrets.

## Conflict matrix (fail closed)

| Situation | Classification | Installer action |
|---|---|---|
| Destination absent | `missing` | Create from package (mutating ops) |
| Destination hash == expected installed/package hash | `match` | No-op / idempotent success |
| Destination hash == previous installed-state hash, differs from new package | `managed_upgrade` | Plan replace (mutating ops) |
| Destination exists, no installed-state, path not in prior managed set, bytes ≠ package | `consumer_owned` | Preserve; do not overwrite |
| Destination hash ≠ package and ≠ previous installed-state hash | `unknown_conflict` | **Fail closed** |
| Consumer `.cursor` is an absolute, external, or directory symlink | `unsafe_link` | **Migrate/replace**: unlink the symlink itself (never follow outside), create a physical empty `.cursor`, then continue normal managed creates. Transaction journal records the original `readlink` target; `rollback` restores that symlink byte-for-byte and removes only the in-repo physical tree the installer created under `.cursor`. Outside target bytes/children must remain untouched. |
| Other destination is symlink or resolves outside repo root | `unsafe_link` | **Fail closed** |
| Managed marker begin/end missing or corrupted | `marker_conflict` | **Fail closed** |
| File listed for supersession removal; identity+hash exact match | `supersede_exact` | Allow removal in plan |
| File listed for supersession; identity or hash mismatch | `supersede_mismatch` | **Fail closed** (do not delete) |
| Dirty unrelated paths outside plan | `unrelated_dirty` | Preserve; do not revert |
| Interrupted transaction with backups present | `recoverable` | Resume/rollback via transaction record |
| Package/manifest invalid | `invalid_package` | **Fail closed** (non-zero exit) |

Unknown classifications default to **fail closed**.

## External-state boundary

Inside the managed package / Git working tree:

- doctrine, skills, templates, managed workflows **templates**, adapter sources, manifests, hashes

Outside the package (never embedded as secret values):

- GitHub App private keys / tokens
- repository secrets and Actions variables values
- Bugbot product configuration toggles applied in GitHub UI/API
- live rulesets and classic branch protection objects
- absolute local checkout paths of IDE Development on any machine

External tooling must:

- default to dry-run / read-only plan and verify;
- emit before/after machine-readable plans and rollback instructions;
- union repository-specific required checks with managed required checks;
- cover `development`, `staging`, and `main`;
- perform **no live mutation** without Principal / approval-gated authorization (WP1 historically proved fixture-backed + optional live GET read-only paths; WP2 closed IDE Development live readiness for its stated scope; consumer/external apply remains gated);
- never print, store, package, or hash secret values.

Apply of App installs, secrets, variables, Bugbot dashboard toggles, or rulesets is **Principal-gated** (not authorized by WP1–WP03 alone; consumer/external apply follows WP04 / separate approval).

## Self-verification versus consumer rollout

| Role | Repository | Current behavior |
|---|---|---|
| System source | IDE Development | Authors `core/managed-core/`; runs internal verification suites; **not** a consumer rollout entry |
| Internal self-verification | IDE Development | May execute installer tests against disposable temp repos only; may build RC archives for proof |
| Consumer rollout | Other LiNKtrend repos | **Deferred** until WP04 Principal approval. Inventory + gate in `docs/GITOPS-CONSUMER-ROLLOUT.md`. WP1–WP03 complete on system source; WP04 packet prepared / not executed. |

Locked consumer rollout order (documentation/ops; not executed — Work Packet 04 / Principal gate):

1. `openclaw_prime`
2. `LiNKplatform`
3. `LiNKskills`
4. `LiNKbrain`
5. `LiNKsites`
6. `LiNKdeveloper`
7. `LiNKlibraries`
8. `LiNKautowork`
9. `LiNKtrading-codebase`

Hard stops:

- no real consumer mutation without Principal-gated WP04 approval
- no nested self-install into IDE Development (timeless)
- no live GitHub settings/credential/tag/release changes without Principal / approval gate
- no Claude runtime additions
- no claim of production readiness when required OS/platform gates are skipped or untested

## Exit code expectations (installer contract surface)

| Code | Class | Meaning |
|---|---|---|
| `0` | clean | Match / completed mutation / verify ok |
| `10` | drift | Drift detected (non-conflict differences) |
| `11` | conflict | Conflict / fail closed |
| `12` | invalid_package | Invalid package or manifest |
| `13` | rollback_failure | Rollback failure |
| `1` | unexpected_failure | Other unexpected failure |

## Related

- `docs/adr/0004-portable-managed-core-v2.md`
- `docs/adr/0003-autonomous-ship-pull-promote.md`
- `docs/contracts/AGENT-COMPLETION.md`
- `docs/contracts/GITHUB-APP-GITOPS-CREDENTIALS.md`
- `core/managed-core/migrations/` (Wave-1 ADR-0004 slice WP4 migration catalog — not Work Packet 04)
- `core/github/managed-runtime/MANIFEST.json` (v1 sparse GitOps runtime; preserved until superseded)
