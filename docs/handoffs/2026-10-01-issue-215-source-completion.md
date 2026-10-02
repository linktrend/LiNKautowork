# Issue #215 source completion handoff

- Date: 2026-10-01 (Asia/Taipei)
- Issue/branch: #215, `issue/215-add-read-only-provider-connection-health-canary`
- Source candidate at takeover: `60b161a71e3ad672eb1a122b099e2bbf7c09e742`, based on `development` `93954faa4f268cf149390f7b5831504c86850727`
- Authorization: Carlos's direct instruction, relayed by `/root`, authorized completion of existing bounded source work. No source push, PR, merge, deployment, credential access, database apply, live workflow write, or canary was authorized/performed in this session.

## Source result

The existing source commit implements `linkautowork-connection-health@1.0.0` as a fixed read-only provider-to-n8n webhook canary. It accepts only the exact package/configuration/input and read-only policy references; persists the request before dispatch; dispatches only after the accepted-version compare-and-set to `running`; and sends only the request ID and canonical fingerprint to the authenticated fixed webhook. It validates the correlated response and execution ID before admitting a durable succeeded receipt. Replays do not dispatch. A failed claim is terminalized only after rereading the same accepted version; uncertain transport, receipt, or persistence cases remain explicit recovery/manual-reconciliation states and are not retried automatically.

The n8n package is inactive and uses only Webhook, Set, and Respond to Webhook nodes. The webhook uses fixed POST path `linkautowork-connection-health-v1`, Header Auth, and response-node mode; the package has no embedded credential. It does not invoke provider APIs or consumer work. This matches the n8n documentation for Header Auth and Respond to Webhook, and n8n documents `$execution.id` as the unique current execution ID: [Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/), [Webhook credentials](https://docs.n8n.io/integrations/builtin/credentials/webhook/), [Respond to Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.respondtowebhook/), [execution](https://docs.n8n.io/build/code-in-n8n/cookbook/built-in-methods-and-variables-examples/execution/).

The candidate source commit contains:

- `automations/catalog/index.json` and the `automations/catalog/linkautowork-connection-health/1.0.0/` package: manifest, schemas, workflow, evaluations, operations/runbooks, provenance, changelog, and README.
- `gateway/src/app.ts`, `gateway/src/config/env.ts`, `gateway/src/integrations/n8n-client.ts`, and `gateway/src/services/provider-route-service.ts`.
- `gateway/tests/provider-connection-health.test.ts`.
- The earlier `docs/handoffs/2026-10-01-issue-215-connection-health-canary.md`.

No new queue, migration, policy engine, or duplicate-dispatch path was added. The existing `ProviderStore` and its expected-version transition are used (`gateway/src/services/provider-store.ts`, `gateway/src/services/supabase-provider-store.ts`).

## Platform boundary and live prerequisites

- Compared the integration with Platform main commit `d65a57340104e25f4bf915be8388ce72b0d09257`, which includes Platform #390. Its current source defines the OpenClaw Autowork service audience as `linkautowork-gateway` and permits `execute`/`read`; the Autowork gateway consumes POST as `execute` and GET as `read`. Platform source holds still leave actor, runtime-binding, credential, key, and secret outputs owner-supplied. This session read Platform source only and changed no Platform file.
- The existing provider PostgREST client independently requires a JWT with exact role `svc_lautowork_runtime` and the requested `org_id`, selects the `lautowork` schema, and does not fall back to `service_role` (`gateway/src/services/supabase-provider-store.ts`). The parent reports the expected provider runtime secret is absent. The existing gateway runtime JWT role `svc_lautowork_gateway` is not a substitute.
- The route is disabled unless its dedicated `LINKAUTOWORK_CONNECTION_HEALTH_WEBHOOK_TOKEN` and provider persistence runtime are configured. A live run also depends on a manually provisioned n8n Header Auth credential bound to the imported workflow and matching runtime token, an active workflow, and the approved read-only Platform identity/policy. No values were read or changed.
- Existing handoff evidence from 2026-10-01 reports that the n8n health endpoint responded `200`, but the exact workflow and Header Auth credential were absent at that time. This is not workflow execution or canary proof. No live workflow import, activation, webhook execution, database operation, or deployment was performed here.
- The existing healthy Autowork release reference for a separately authorized rollout rollback is `0d8d241a56e0ebaf59d2daf25bc9ecd9b9312f81`; any such rollback must remove only the new provider configuration. This session did not perform or authorize rollout.

## Validation performed in this session

- `npm test -- gateway/tests/provider-connection-health.test.ts gateway/tests/provider-routes.test.ts` — passed, 2 files / 20 tests.
- `npm run typecheck` — passed.
- `npm run test:catalog` — passed, 36 files / 182 tests; 1 test skipped. The suite emitted its existing mocked audit-RPC `403 permission denied` warning.
- `npm run catalog:check` — passed; catalogue index is current.
- `git diff --check` — passed.
- `git status --short --branch` confirmed the issue worktree started clean except for this session's new records. No live or hosted integration test was run.

## Session files and repository state

- Added this completion handoff and a session record, then moved that record to `docs/agent-sessions/completed/` per repository lifecycle.
- The #215 source changes were already committed as `60b161a` before this session. This session added no application code and changed no pre-existing files outside its own handoff/session records.
- The shared checkout was clean on `development`; the #215 issue worktree was isolated. The expected `/Users/linktrend/.codex/worktrees/1f4a/LiNKautowork` path did not exist, so work continued only in the existing issue worktree.
- The repository has no `docs/agent-briefing.md`, `docs/agent-coordination.md`, `docs/current-status.md`, or session/handoff template. No shared current-status dashboard was created or edited.

## Exact next action

Keep source delivery separate from runtime readiness. The service owner must provide/approve the Platform #390 identity-registration outputs and read-only policy, the org-bound `svc_lautowork_runtime` provider JWT through its approved secret path, and the producer-only n8n Header Auth binding/token through the approved deployment path. Then an authorized operator can provision/import the inactive fixed workflow, verify its digest/configuration binding, activate it, and run one controlled canary with durable request/receipt readback. Until those dependencies and live authorization are present, deployment, workflow write, canary, and production acceptance remain HOLD.

Confidence: 98% for source behavior and source-level validation; live behavior remains unproven by design.
