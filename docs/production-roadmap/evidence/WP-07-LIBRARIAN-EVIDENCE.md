# WP-07 — Automation-mode Librarian evidence

## Delivered local adapter

- `gateway/src/contracts/librarian-automation.ts` accepts only `domain: "automation"`, canonical organisation IDs, immutable `evidence://` references, SHA-256 hashes, bounded candidate patches, and audit metadata. Strict parsing rejects unknown fields, so raw client payloads and credentials cannot enter this adapter.
- `gateway/src/services/librarian/automation-librarian.ts` resolves every evidence reference, recomputes its hash, counts distinct verified evidence, authenticates aggregate approval issuers, and implements deterministic deduplication, trigger thresholds, global disable, per-automation pause, candidate lifecycle transitions, and independent-review separation.
- The candidate contains source automation/version, evidence, scope, patch artifact/digest, benefit/risk/eval suites, provenance-style audit metadata, redaction outcome, and status. It has no mutation, publication, promotion, or deployment capability.
- The gateway accepts ingress only after service authentication, signed Platform org claims, and a separately signed institutional JWT agree on the organisation. Production accepts only RS256 tokens with `kid`, verifies issuer/audience/signature/expiry/not-before/subject/org/role against configured JWKS, bounds the cache to 20 keys and 300 seconds, and throttles unknown-key refreshes to 30 seconds. Unknown/unavailable keys fail closed. HS256 is test-only and cannot run in production.
- Migration `20260804_000003_lautowork_librarian_state.sql` adds durable org-scoped candidate, evidence-registry, dedupe, audit, and kill/pause state with narrow runtime RPC grants. `SupabaseLibrarianStore` is the production adapter; `DurableMemoryLibrarianStore` is the restart-test double.
- `Wp02PackageValidator` invokes WP-02's exported `validatePackageDirectory`. `Wp06ReceiptEvaluator` consumes WP-06's native authenticated envelope, binds automation/version/package/verdict, and verifies its HMAC through a governed key ID plus `gsm://` reference. Verifier secrets are GSM-resolved into memory and never stored in evidence, the database, or logs.
- Every privileged `000003` RPC calls `lautowork.assert_command_authorized`; candidate/evidence functions derive the addressed record org and treat request org only as a consistency guard. The gateway uses `SUPABASE_RUNTIME_JWT`, while the service-role key remains only the API key header.

## Lifecycle example

`automations/fixtures/librarian/repeated-failure-candidate.json` contains two redacted eval references for the same organisation. With the injected WP-02 validator and WP-06 evaluator adapters passing, tests record:

`proposed → ready_for_eval → awaiting_review → approved`

The proposer cannot make the review decision. `approved` is terminal candidate review only; no deployment field, n8n client, secret resolver, publisher, promoter, or deployment call exists in the Librarian service.

## Validation performed

- `npm run test:automation-librarian` — 16 passing tests.
- `npm test` — 16 root test files / 81 tests passed after the production JWKS correction.
- `npm run verify:automation-librarian-db` — passed against disposable PostgreSQL; proved migration up/down, durable evidence resolution, pause state, candidate dedupe lookup, and cross-org lookup denial.
- `npm run typecheck` — passed.
- `npm run ci` — passed after C-W2-08/C-W2-10 with 16 root test files / 74 tests plus all package, evaluator, restore, disposable-database, and typecheck gates.

WP-07 tests, disposable database verification, and typecheck are official `npm run ci` gates and explicit GitHub Actions steps. The typecheck is intentionally gateway-wide because the Librarian adapter is gateway-owned.

The tests cover successful flow, evidence attacks, org isolation, restart persistence, kill/pause, distinct proposer/reviewer principals, test-only HS256, production RS256/JWKS, forged signatures, wrong kid/alg/issuer/audience/org/role, expiry, rotation/unavailable providers, self-review denial, scoped RPC credentials, real WP-02 validation, and forged/unbound WP-06 envelopes. All JWKS tests use injected local keys/providers; CI performs no live issuer call.

## Deliberate boundary and rollback

This correction does not claim that the external institutional host is live. The adapter contract is configurable and fails closed when issuer/service configuration is absent. The disposable/test path proves durability and enforcement locally; applying the new migration and configuring a real approved issuer remain separately authorised deployment actions.

Rollback is code-only: remove the Librarian routes/service registration, or use the control route with an org ID and `{ "action": "disable" }` to halt new candidate creation. Migration rollback may drop only the `_librarian_` tables/functions after exporting their audit history. None of these paths modifies a workflow, published package, deployment, credential, execution route, or historical execution telemetry.
