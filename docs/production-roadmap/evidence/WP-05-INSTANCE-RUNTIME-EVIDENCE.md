# WP-05 — Instance Runtime Evidence

## Implemented boundary

- `POST /v2/instances/:instanceId/operations/:operation/execute` is the supported invocation surface. It accepts only an idempotency key and input.
- The authenticated service and platform-org claim address an enabled, org-scoped durable binding. Workflow path, method, criticality, timeouts, retries, release state, deployment digest, and required secret references are resolved server-side.
- `/v1/ingress/:workflowId` remains the explicit signed internal compatibility route. It is not the v2 client model and must be retired through a separately approved consumer migration.
- Secret bindings are references only. Dispatch carries the native instance-credential/broker reference descriptor; raw credentials are not resolved into caller input, receipts, or logs.

## Provisioning controls

- The provisioner reads a source workflow, requires its expected digest, creates a uniquely named inactive copy, performs smoke before activation, and compensates by deactivating/deleting a failed copy.
- The provisioning service locks and records request state, is replay-safe for completed request references, and records failure before rethrowing.

## Validation

- `npm test -- --run gateway/tests/instance-runtime.test.ts gateway/tests/provisioning-service.test.ts` — pass (5 tests).
- `npm run typecheck` — pass.

No live n8n, GSM, Supabase migration, or external operation was invoked.
