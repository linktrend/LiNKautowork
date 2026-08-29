# Managed repository protection (external-state contract)

**Status:** Binding for Wave 1 portable IDE Development v2
**Date:** 2026-08-01
**Audience:** Operators applying GitHub branch protections; managed installer consumers; Verifier
**SOT:** `docs/AUTONOMOUS-GIT-OPERATIONS.md` · `core/github/CI-GATE-CONTRACTS.md` · ADR `docs/adr/0003-autonomous-ship-pull-promote.md`
**Tooling:** `scripts/manage-repository-protections.sh` · `scripts/gitops/repository_protection.py`
**Compatibility wrapper:** `scripts/apply-development-merge-ruleset.sh` (development-only apply; CLI preserved)

---

## External-state boundary

GitHub rulesets, classic branch protection, repository settings (`allow_auto_merge`), Apps, secrets, variables, and Bugbot dashboard settings are **external state**.

| Rule | Requirement |
|------|-------------|
| Packaging | Never package credentials, tokens, App private keys, or secret values into the managed core |
| Default mode | **Plan / dry-run** — produce a before/after plan and rollback snapshot; mutate nothing |
| Apply | Explicit `--apply` only; never implied by install/update |
| Wave 1 | Do **not** apply protections to IDE Development or any consumer during Wave 1 |
| Reads | Live reads may list public protection metadata when an operator opts into live mode; tests use fixtures only |
| Secrets | Tools must not create credentials and must not read secret values |

---

## Governed branches (required)

Every repository that installs the managed system must protect these three branches:

| Branch | Ruleset name (when rulesets available) | Managed purpose |
|--------|----------------------------------------|-----------------|
| `development` | `development-autonomous-merge` | Strict required checks, work-branch source policy, delivery-controller auto-merge compatibility |
| `staging` | `staging-autonomous-promote` | Promotion-only PR sources (`promote/staging/*`) + staging-gate checks |
| `main` | `main-autonomous-release` | Promotion-only PR sources (`promote/main/*`) + release-gate checks + Main Approve compatibility |

Promotion-only source policy is enforced by the managed workflow check **`Linktrend Branch Source Policy`** (see `.github/workflows/branch-source-policy.yml`). Protections require that check on all three branches so GitHub cannot merge disallowed heads even if a human clicks merge. The obsolete step title `Enforce allowed PR source branches` must not remain a required context (WP-U05).

---

## Managed required-check baselines

Defaults match IDE Development. Consumers override via repository variables / CLI extras; baselines always union with the active source-policy check.

### `development` (delivery controller)

Managed baseline (order stable):

1. Fast-gate checks — default `Verify IDE Development`, or `LINKTREND_INTEGRATOR_REQUIRED_CHECKS` when provided
2. `Linktrend Branch Source Policy` (always present)

`Cursor Bugbot`, `Linktrend Review Gate`, and `Linktrend Review Ready` are obsolete
advisory/provider contexts. The v2.5.1 migration removes them from required
status checks rather than waiting for credentials or synthetic success states.

Also set repository setting `allow_auto_merge=true` so the delivery controller may auto-merge when gates are green.

### `staging` (staging-gate)

Managed baseline:

1. Staging-gate checks — default `Verify IDE Development`, or `LINKTREND_STAGING_GATE_CHECKS`
2. `Linktrend Branch Source Policy`

Do **not** require `Linktrend Review Gate` on staging promotion PRs.

### `main` (release-gate + Main Approve)

Managed baseline:

1. Release-gate checks — default `Verify IDE Development`, or `LINKTREND_RELEASE_GATE_CHECKS`
2. `Linktrend Branch Source Policy`

Do **not** require `Linktrend Review Gate` on main promotion PRs.
Do **not** invent extra human-review rules that conflict with Lisa Main Approve (`docs/contracts/LISA-MAIN-APPROVE-DISPATCH.md`). Preserve existing `bypass_actors` on update. Main Approve remains Principal Approve of the sealed package + release-gate success on the promote head.

---

## Union of repository-specific checks

When planning an update of an existing ruleset or classic protection:

1. Start from the managed baseline for that branch.
2. **Preserve** every legitimate existing required-check context that is not already in the baseline (stable sort: managed order first, then preserved names sorted lexicographically).
3. Never drop a previously required context solely because it is consumer-specific.
4. Explicit `--checks` / `--extra-checks` append into the preserved set (still unioned; duplicates removed).

### Non-check ruleset rules and classic review fields

On ruleset update, the tool replaces only `required_status_checks` rules. Every other legitimate rule type already on the ruleset (`pull_request`, `non_fast_forward`, `deletion`, etc.) is **preserved** in the planned/applied body. Missing or unclassified rules fail closed — never silently wipe unrelated rules while managing checks.

On classic branch-protection update, existing `required_pull_request_reviews`, `restrictions`, and similar review/restriction fields are **preserved** from before-state unless managed policy explicitly changes them. The tool must not force those fields to `null` merely because it is rewriting required status checks.

When required check contexts already match the desired union, plan/verify still compare a **semantic** normalized view of classic reviews/restrictions (and related preserved fields) against the desired body. Realistic GitHub GET payloads (nested user/team/app objects, `url`/`html_url` noise, `{enabled: bool}` wrappers) normalize for PUT equality checks and for actual writes — **without inventing** review policy (for example, never defaulting `required_approving_review_count` when a GET shell only exposes `url`/`enabled`). Shape-only differences that normalize to the same values are **not** drift (live re-GET stays nested; perpetual update/verify failure is forbidden). If the semantic comparison detects that desired would change or wipe preserved review/restriction fields, action is `update` with reason `review/restriction drift` — not `noop`. Sparse review shells with no preservable fields fail closed. Create still emits `null` reviews/restrictions. Unexpected field types fail closed.

Fail closed only when the desired set cannot be represented on the available GitHub mechanism (see capability handling), or when preservation cannot be proven safe.

---

## Plan / apply / verify / rollback

| Mode | Mutates? | Exit 0 when |
|------|----------|-------------|
| `plan` (default) | No | Plan emitted (even if drift exists) |
| `verify` | No | Current external state matches desired plan |
| `apply` | Yes (explicit) | Desired state written atomically across governed branches; post-apply verify passes. Mid-apply failure restores archived before-state and reports incomplete (no false success). |
| `rollback` | Yes (explicit, from snapshot) | Restored to recorded before-state |

Every plan and apply response includes:

- `before` / `after` per governed branch
- `actions[]` (`create` / `update` / `noop` / `unavailable`)
- `rollback.snapshot` sufficient to restore prior ruleset bodies / classic protection payloads / `allow_auto_merge`
- Human-readable `rollback.instructions`

---

## Capability: rulesets vs classic branch protection

| Capability probe | Behavior |
|------------------|----------|
| Rulesets list succeeds | Prefer repository rulesets (`mechanism=rulesets`) |
| Rulesets unavailable (404 / plan limitation / feature disabled) but classic branch protection readable | Plan classic protection payloads (`mechanism=branch_protection`) |
| Neither available / insufficient permissions | `mechanism=unavailable`; plan reports blocked actions; apply refuses; no partial silent mutation |

Never invent a third mechanism. Document the gap for the Principal; do not force-apply.

---

## Delivery controller / Main Approve compatibility notes

- Development: required checks must include the active fast-gate and branch-source policy; `allow_auto_merge=true`.
- Staging / main: merge only via temporary `promote/*` PRs after named gates; never direct-push.
- Preserve `bypass_actors` on ruleset update so existing App / operator bypasses are not wiped.
- Preserve non-check ruleset rules and classic `required_pull_request_reviews` / `restrictions` (and similar) on update.
- Tools never create GitHub Apps, install tokens, or repository secrets.

---

## CLI entrypoints

```bash
# Default: plan only (no mutation)
./scripts/manage-repository-protections.sh --repo linktrend/Example plan

# Verify drift without writing
./scripts/manage-repository-protections.sh --repo linktrend/Example verify

# Explicit apply (operator only; forbidden in Wave 1 automation)
./scripts/manage-repository-protections.sh --repo linktrend/Example apply --apply

# Development-only legacy wrapper (still applies when invoked — operator tool)
./scripts/apply-development-merge-ruleset.sh --repo linktrend/Example
```

Fixture / offline mode for tests: pass `--fixture-dir <path>` so no live GitHub calls occur.

---

## Change control

Changing managed baselines, ruleset names, or union rules is a **contract change**: update this file, `scripts/gitops/repository_protection.py`, compatibility wrapper expectations, and `scripts/tests/test-repository-protection.sh` in the same change.
