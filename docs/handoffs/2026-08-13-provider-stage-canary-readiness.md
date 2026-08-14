# CR-04 provider stage-canary readiness

Date: 2026-08-13 (Asia/Taipei)

## Readiness decision

Stage canary readiness is HOLD. The source candidate is
`ide-repository-status@1.0.0` at immutable source checkpoint
`3ccfca0b1b9564e25cd6f4eea012caf9b3ac7ee1` (tree
`b85579ff28ac6b34960501bfed7e65942f39b2cf`), with source-derived definition
digest `sha256:12acc384669f0edd01e37897093466340816fbe4f13774d188235f8ac0f1d336`
and configuration digest
`sha256:5cd4573569f22891a5e13201afa91bfaecc7d9c3f1fc540a2d08caae648391d9`.

**IDE Development** is the first and only source-proposed consumer for this
candidate. That proposal is not evidence that the consumer is connected,
authorized, staged, executed, or successful.

## Required named prerequisites

- Platform claims
- Platform JWKS issuer
- Platform credentials
- Supabase migration application
- NATS
- n8n
- Express gateway
- Approved test tenant
- Owner/operator authorization

These names identify prerequisites only; this handoff supplies no credentials,
activation instructions, stage-mutating command, or external dispatch command.

## Source evidence and boundaries

The source evidence is defined by:

- `packages/automation-contracts/src/provider-contract.ts`
- `packages/automation-contracts/tests/provider-contract.test.ts`
- `gateway/tests/provider-routes.test.ts`
- `gateway/tests/provider-store.test.ts`
- `gateway/tests/supabase-provider-store.test.ts`
- `automations/catalog/ide-repository-status/1.0.0/`
- `docs/contracts/provider-contract-v1.md`, `docs/contracts/provider-http-v1.md`, `docs/contracts/provider-persistence-v1.md`, `docs/contracts/provider-lifecycle-v1.md`, `docs/contracts/provider-events-v1.md`, `docs/contracts/provider-dispatch-v1.md`, `docs/contracts/provider-status-v1.md`, `docs/contracts/provider-notifications-v1.md`, `docs/contracts/provider-aggregation-v1.md`

Supported source-local behavior is limited to authenticated capability and
catalogue metadata, exact-version detail, bounded request acceptance/replay,
status and receipt reads, callback admission, cursor-bounded event reads, and
provider-store guards. The source checks organization authority, exact release
and digest binding, idempotency conflict, callback authenticity/replay/order,
tenant/cursor isolation, evidence limits, and kill-switch new-start denial.
External assistance is explicitly HOLD/unavailable with no dispatch proof.

Provider records are not consumer records. They cannot establish an IDE
Development Issue, Ledger, gate, approval, branch, PR, deployment, consumer
result, external side effect, E2E result, or production outcome. MCP is not
applicable, and OKF is not applicable to operational records.

## Source command results

- Focused provider route/store/Supabase tests: PASS, 3 files and 13 tests.
- Automation contract suite: PASS, 2 files and 9 tests.
- Automation package validator: PASS, 1 catalogue release.
- Catalogue check: PASS, index current.
- Root typecheck: PASS.
- Root local test suite: PASS, 26 files and 108 tests. The run emitted an expected test-double audit-RPC warning (`403 permission denied`).

## Explicit hold boundary

Stage activation, stage migration application, credentials, provider services,
consumer execution, callback delivery, E2E, external assistance, deployment,
and production remain HOLD. Production is prohibited by this handoff. No
command in this document mutates stage or production.
