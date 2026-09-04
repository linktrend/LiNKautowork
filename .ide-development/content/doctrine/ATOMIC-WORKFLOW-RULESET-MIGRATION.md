# Atomic workflow and ruleset migration (Update 5 / WP-U05)

**Status:** Active for `v2.4.0` WP-U05 (tooling + simulation). Live consumer
verification (`AC-U05-17`) is deferred to WP-CONSUMERS.
**Authority:** frozen `issue/307` Update 5 / `AC-U05-01`–`AC-U05-16`.
**Implementation:** `scripts/gitops/atomic_workflow_ruleset_migration.py` with
`scripts/gitops/repository_protection.py` for plan/apply/verify/rollback.

## Required outcome

Managed workflow files, coordination labels, readiness evaluator check-name
contracts, and live `development` / `staging` / `main` rulesets are one
versioned migration. Installation is incomplete while any protected branch
requires an obsolete managed check, a check active workflows cannot produce, or
a managed workflow depends on a missing coordination label.

## Active managed check contract

| Context | Active name |
|---|---|
| Review gate | Removed from required checks; retained provider/review signals are advisory only |
| Source policy | `Linktrend Branch Source Policy` |
| Fast | `Linktrend Fast Checks` |
| Full | `Linktrend Full Suite` |
| Receipt | `Linktrend Receipt Gate` |

Obsolete managed names (must be replaced, never preserved as repo-owned):

- `Enforce allowed PR source branches` → `Linktrend Branch Source Policy`
- `Cursor Bugbot`, `Linktrend Review Gate`, and `Linktrend Review Ready` → removed from required checks

## Capability preflight

Before mutation, probe native branch-protection / ruleset APIs and administrator
authority. Publish `native_protection_unverified` and stop on:

- `protected: false` for a governed branch
- HTTP 403
- missing administrator permission
- organization rules not visible through the branch endpoint

Successful application checks are never proof of native enforcement.
Reduced-assurance delivery requires recorded founder approval and is reported as
`reduced_assurance`, never silently relabeled as protected.

## Atomic three-branch apply

Rename or replace managed checks on all three governed branches together.
Preserve arbitrary repository-owned required contexts and strict-check settings.
Failure after one branch update rolls back applied branches or reports
`migration_incomplete` with no false success.

## Labels

Derive exact managed labels (name/description/color) from the release contract.
Create `linktrend-full-suite` before Full dispatch. Wrong-name, conflicting
metadata, or application to a stale/ineligible PR fails closed and does not
claim success.

## Evaluator / variable migration

Integrator, Packager, Promoter, observer, planner defaults and
`LINKTREND_*_CHECKS` repository variables must use the exact active contract.
Retained obsolete raw names fail closed.

## Trusted verifier separation

Gate logic that exists only on an untrusted product candidate cannot declare
the candidate verified. Install and validate the trusted verifier through a
separate protected migration; keep the sealed candidate head/tree unchanged.
Failed trusted-verifier migration reports `trusted_gate_version_unavailable`
and preserves the prior trusted gate.

## Rollback

Restore archived before-state for rulesets/labels. Leave issue branches
unmerged. Never weaken native protection or copy a verifier repair onto a
sealed product candidate.

## Related

- `docs/contracts/REPOSITORY-PROTECTION.md`
- `core/github/CI-GATE-CONTRACTS.md`
- `scripts/manage-repository-protections.sh`
