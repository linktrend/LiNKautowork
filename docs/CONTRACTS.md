# LiNKautowork Contracts (MVO)

## Canonical Tenant

- Contract `tenantId`: `00000000-0000-0000-0000-000000000001`
- Label/slug only: `linktrend_internal`

## Ingress Envelope

Required fields:

- `tenantId` (UUID)
- `missionId`
- `runId`
- `taskId`
- `dprId`
- `triggerSource`
- optional `capabilityId|packageId`

Security requirements:

- `x-link-service`
- `x-link-service-token`
- `x-link-signature` (HMAC-SHA256)
- `x-link-timestamp`
- `x-link-nonce`

## Audit RPC Payload

Canonical fields written to `audit_runs`:

- `tenant_id`
- `run_id`
- `task_id`
- `dpr_id`
- `status`
- `token_usage`
- `command_log`
- `details`
- `created_at`

`details` must include workflow id, trigger source, latency, retries, and failure reason when failed.

## Event Contract

LiNKautowork emits both:

- Primary interoperability subjects: `aios.*`
- Internal mirror subjects: `linkautowork.v1.*`

Payload lineage fields are identical across both subject families.

## Kill Switch Hierarchy

1. Scoped kill switch (`tenant/workflow`) for local failures.
2. Global webhook revocation for platform-wide incidents (security/runaway-cost/systemic rate-limit).
