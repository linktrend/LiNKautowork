# ADR 0004: Portable Managed Core v2

**Status:** Accepted for Wave 1 implementation (Issue #43)
**Date:** 2026-08-01
**Version target:** `2.0.0` (no Git tag or GitHub release in this wave)
**Related:** `docs/adr/0003-autonomous-ship-pull-promote.md`, `docs/contracts/MANAGED-CORE-V2.md`, `core/managed-core/`

## Context

IDE Development currently spreads shared behavior across a Mac-local checkout, sparse GitOps wiring (`scripts/wire-repo.sh`), physical copies of a few Cursor entrypoints, and optional absolute `.cursor` symlinks on workspace machines. That model:

- does not travel cleanly across machines or Windows hosts without symlink privileges;
- installs only a GitOps slice rather than the full shared development lifecycle;
- lacks a single committed package identity, transactional update path, and fail-closed conflict model inside each consumer.

Wave 1 must turn IDE Development into a versioned, portable software-development operating system that installs or updates **inside** a Git repository without external absolute symlinks, while preserving consumer-owned content and existing GitOps behavior.

Claude Code remains outside current v2 release scope. Historical Claude files may remain; no new Claude runtime surfaces are added.

## Decision

1. **Installed package root:** every consumer receives a committed physical tree at `.ide-development/` (never an absolute, external, or checkout-to-checkout symlink).
2. **System source root:** package content and schemas are authored under `core/managed-core/` in the IDE Development system repository.
3. **Physical discovery adapters (default):**
   - Codex: root `AGENTS.md` managed marker block + physical `.agents/skills/<name>/SKILL.md`
   - Cursor: physical `.cursor/rules`, `.cursor/commands`, and `.cursor/skills` entries
4. **Manifest authority:** a versioned package manifest declares every managed path with ownership class, source hash, destination, mode, platform, merge strategy, and optional supersession identity.
5. **Installed-state authority:** after successful mutation, the installer records hashes and package version in committed `.ide-development/installed-state.json`. Transaction backups and recovery journals live in Git-local metadata under `.git/ide-development/` (not packaged credentials).
6. **Transactional mutation:** every install/update/rollback plans first, writes machine-readable plans, performs atomic file replacement with exact pre-change backups, and can recover interrupted transactions.
7. **Precedence:** IDE Development governs shared lifecycle doctrine and managed lifecycle rules. Repository-specific technical guidance remains unless it conflicts with an **explicitly identified** managed lifecycle rule.
8. **Fail closed:** unknown or modified conflicts never overwrite or delete; superseded generic files may be removed only when a reviewed migration-catalog identity and hash match exactly.
9. **External-state boundary:** GitHub App credentials, secrets, variables, Bugbot product settings, and live ruleset/branch-protection mutations are never packaged as secret values. External settings use separate plan/apply/verify tooling with dry-run default. Protection of `development`, `staging`, and `main` is required managed-system behavior for every installed repository; repository-specific required checks are preserved and unioned deterministically.
10. **Self-verification vs consumer rollout:** IDE Development is the system source and internal self-verification target. It is **not** a consumer rollout entry and must not receive a nested installed copy of itself during Wave 1. Consumer rollout order and Principal approval gates are documented separately and remain read-only until approved.
11. **Out of scope for this ADR:** installer engine implementation (WP2), platform adapter file bodies (WP3), migration catalog entries (WP4), live protection apply (WP5), and top-level documentation rewrites (WP6).

## Alternatives considered

- Keep Mac-local `.cursor` symlink inheritance — rejected; breaks portability and Windows hosts.
- Nested submodule or git subtree of the full IDE Development repo — rejected; couples consumers to system history and invites nested self-install.
- Symlink managed files into consumers from a shared absolute path — rejected; Wave 1 forbids absolute/external/checkout-to-checkout symlinks.
- Soft-merge unknown conflicts — rejected; fail-closed is required for managed drift.
- Include Claude Code adapters in v2 — rejected; explicitly outside current release scope.

## Consequences

- New contracts and schemas live under `docs/contracts/MANAGED-CORE-V2.md` and `core/managed-core/schemas/`.
- Existing sparse GitOps wire/sync scripts remain until the v2 installer supersedes them; Wave 1 must preserve their observed behavior for current consumers.
- Active docs (WP6) must stop describing consumer-to-system `.cursor` symlinks as the current install model.
- Protection planning (WP5) becomes standard system behavior but does not mutate live GitHub settings in this wave.

## Validation / rollback

- Validation: schema examples validate; disposable-repo installer tests (WP2/WP4) prove physical install, idempotence, fail-closed conflict, byte-exact rollback, and no outbound path resolution; existing GitOps suites remain green.
- Rollback: leave consumers on current wire/sync model; do not tag `v2.0.0`; remove unreleased `.ide-development` package docs/schemas from the issue branch if abandoned before merge.
