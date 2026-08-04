# C-W1-01 — Database Security and Coherence Correction Evidence

Status: complete locally; awaiting independent re-audit.

## Audit findings corrected

1. All four `SECURITY DEFINER` RPCs now derive the target organisation from the release, execution, or approval record. The caller's `p_org_id` must match that derived organisation but cannot grant authority. The canonical `request.jwt.claim.org_id` must match the target and the caller must have platform membership or trusted service authority.
2. The new model prevents same-organisation lineage mixing. Instance, provisioning request, deployment, and execution triggers check the definition/release/instance/deployment relationship and deployed digests.
3. SQL and TypeScript validation now reject raw connection-string URLs, Bearer values, private keys, recognised opaque-token prefixes, and secret-shaped keys.
4. RLS no longer treats `request.jwt.claim.tenant_id` as an alternative authority source.
5. The disposable down path now drops privileged public RPCs and local trigger helpers, and the harness runs a post-rollback verification.

## Commands and results

```text
npm --prefix packages/automation-contracts test
  1 test file passed; 3 tests passed

npm --prefix packages/automation-contracts run typecheck
  passed

npm --prefix packages/automation-contracts run verify:db
  passed against disposable postgres:16-alpine
  - canonical-org service call certifies a matching release
  - tenant-only RLS access is denied
  - each of the four privileged RPCs rejects an org-A context operating org-B data
  - same-org lineage mismatches are rejected for instance, provisioning, deployment, and execution records
  - connection-string and Bearer configuration values are rejected
  - forward verification and disposable rollback verification both pass
```

## Boundary retained

No Supabase project, shared LiNKplatform schema, GSM secret, n8n instance, VPS, or live migration was changed. The service-authority claim is a production integration prerequisite for LiNKplatform; this packet proves the local database contract only.
