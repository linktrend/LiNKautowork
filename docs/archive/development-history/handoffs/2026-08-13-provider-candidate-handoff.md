# CR-04 provider candidate handoff

Date: 2026-08-13 (Asia/Taipei)

## Scope and candidate

This handoff records source-local final proof for immutable source checkpoint
`3ccfca0b1b9564e25cd6f4eea012caf9b3ac7ee1` (tree
`b85579ff28ac6b34960501bfed7e65942f39b2cf`) on
`issue/85-correct-provider-routes-persistence-adapter-and`. It was pushed to
the branch. No deployment, migration application, external activation,
credential use, or stage operation was performed.

The only candidate is the checked-in `ide-repository-status@1.0.0` package. Its
manifest lifecycle is `draft`; its workflow is inactive and has no credentials.
The source-derived candidate digests observed during this proof are:

- Definition: `sha256:12acc384669f0edd01e37897093466340816fbe4f13774d188235f8ac0f1d336`
- Configuration: `sha256:5cd4573569f22891a5e13201afa91bfaecc7d9c3f1fc540a2d08caae648391d9`

## Contract, schema, and package paths

- Contract/schema source: `packages/automation-contracts/src/provider-contract.ts`
- Contract tests: `packages/automation-contracts/tests/provider-contract.test.ts`
- Gateway route proof: `gateway/tests/provider-routes.test.ts`
- In-memory store proof: `gateway/tests/provider-store.test.ts`
- Supabase adapter proof: `gateway/tests/supabase-provider-store.test.ts`
- Candidate package: `automations/catalog/ide-repository-status/1.0.0/`
- Candidate manifest/workflow: `automations/catalog/ide-repository-status/1.0.0/automation.json`, `automations/catalog/ide-repository-status/1.0.0/workflow.json`
- Candidate schemas: `automations/catalog/ide-repository-status/1.0.0/contracts/configuration.schema.json`, `automations/catalog/ide-repository-status/1.0.0/contracts/input.schema.json`, `automations/catalog/ide-repository-status/1.0.0/contracts/output.schema.json`
- Provider contracts: `docs/contracts/provider-contract-v1.md`, `provider-http-v1.md`, `provider-persistence-v1.md`, `provider-lifecycle-v1.md`, `provider-events-v1.md`, `provider-dispatch-v1.md`, `provider-status-v1.md`, `provider-notifications-v1.md`, `provider-aggregation-v1.md`

## Supported source-local operations

The source gateway supports authenticated, bounded metadata operations for
capabilities, compact catalogue discovery, exact automation/version detail,
request acceptance and idempotent replay, request status, receipt retrieval,
callback admission, and organization-scoped cursor-bounded event reads.
The provider store supports tenant-scoped acceptance, CAS lifecycle transitions,
immutable receipt binding, callback ordering checks, event deduplication, and
kill-switch guards. These are source-local contract/store behaviors only.

## Authority and fail-closed boundaries

Platform-derived organization identity is authoritative over the request body.
Internal service authentication and Platform invocation authentication are both
required. Exact automation version, definition digest, configuration digest,
expiry, capability, audience, binding, revocation, idempotency fingerprint,
callback binding/timestamp, cursor, tenant, evidence-reference, and kill-switch
checks fail closed. Raw/private payloads and oversized evidence are rejected.
External assistance is HOLD/unavailable and has no dispatch path in this proof.

Provider receipts and events contain bounded metadata and opaque references;
they do not prove or mutate a consumer Issue, Ledger, Gate, approval, branch,
PR, deployment, publication, external side effect, consumer result, E2E result,
or production readiness. MCP is not applicable to this operational surface.
OKF is not applicable to operational records.

## Source proof commands and results

- `npx vitest run gateway/tests/provider-routes.test.ts gateway/tests/provider-store.test.ts gateway/tests/supabase-provider-store.test.ts` — PASS, 3 files and 13 tests.
- `npm run test:automation-contracts` — PASS, 2 files and 9 tests.
- `npm run validate:automations` — PASS, 1 catalogue release.
- `npm run catalog:check` — PASS, catalogue index current.
- `npm run typecheck` — PASS.
- `npm test` — PASS, 26 files and 108 tests. The run emitted an expected test-double audit-RPC warning (`403 permission denied`).

The focused provider/store/contract proof and repository-wide local suite are
Source PASS.

## External prerequisites (names only)

- Platform claims
- Platform JWKS issuer
- Platform credentials
- Supabase migration application
- NATS
- n8n
- Express gateway
- Approved test tenant
- Owner/operator authorization

## Decision

Source PASS for this candidate's local provider route/store/contract evidence.
Stage, E2E, external activation, consumer-result, deployment, and production
evidence are HOLD. No production operation is authorized or described here.
