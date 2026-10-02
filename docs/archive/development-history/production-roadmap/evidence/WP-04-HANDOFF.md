# WP-04 Handoff — Automation Control Data Model

Status: corrected after independent Wave 1 audit; correction evidence is in `C-W1-01-DATABASE-SECURITY-CORRECTION.md`.

## Delivered

- Additive `lautowork` migration for the required catalogue, release, instance, operations, and evidence records.
- Org-scoped composite foreign keys, same-automation lineage triggers, and canonical-org RLS for all new private operational tables.
- Immutable-release trigger plus controlled certification/deprecation/retirement RPCs.
- Independent-evaluation requirement for certification.
- Reference-only secret-binding record and SQL/TypeScript/Zod secret-shaped-content guards, including connection-string and Bearer-value patterns.
- Append-only evidence triggers and narrow execution/approval append RPCs.
- Disposable Postgres Docker harness and verification matrix.
- Migration manifest, prerequisites, hashes, security decisions, forward-fix/rollback instructions, and a tested disposable rollback path.

## Commands and results

```text
npm --prefix packages/automation-contracts test
  1 test file passed; 3 tests passed

npm --prefix packages/automation-contracts run typecheck
  passed

npm --prefix packages/automation-contracts run verify:db
  passed against disposable postgres:16-alpine, including adversarial authorization/lineage/redaction cases and a verified rollback cleanup

bash -n packages/automation-contracts/disposable-db/run.sh
  passed

git diff --check
  passed at the final local verification point
```

## Explicit exclusions

- No Supabase project, GSM secret, VPS, n8n instance, gateway route, platform schema, or live migration was touched.
- WP-05 owns instance provisioning and gateway execution authorization.
- WP-06 owns execution projection/callback handling and live evaluator integration.
- WP-07 owns Automation Librarian candidate workflow.
- WP-08 owns health derivation, alerting, incident operation, maintenance, canary, and rollback service behavior.
- Product/API/dashboard consumers must use future authenticated API contracts, not direct database mutation.

## Auditor focus

1. Confirm the LiNKplatform canonical `request.jwt.claim.org_id`, membership-helper, and service-role claim contract in shared environments.
2. Confirm the exact production migration sequencing and whether existing service runtime roles use `svc_lautowork_runtime` as intended.
3. Confirm the client-product semantics for provider-owned offerings before WP-11 adds public product behaviour.
4. Review the same-automation lineage trigger matrix before WP-05 relies on it for runtime authorization.

## Risks and forward path

The disposable harness proves PostgreSQL behaviour, not Supabase hosting, RLS role claims, live migrations, or n8n execution. A production migration remains blocked until LiNKplatform review/application ownership, backed-up stage migration proof, new GSM mapping, and VPS/network decisions are complete.
