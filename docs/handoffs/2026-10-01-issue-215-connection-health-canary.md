# Issue #215 — Provider connection health canary

**Date:** 2026-10-01 (Asia/Taipei)
**Branch:** `issue/215-add-read-only-provider-connection-health-canary`
**Base:** `93954faa4f268cf149390f7b5831504c86850727` (`origin/development`)

## Scope and result

Adds the fixed, read-only `linkautowork-connection-health@1.0.0` provider package and its synchronous authenticated n8n webhook path. A request is dispatched only after the durable `accepted -> running` compare-and-set succeeds. Replays never dispatch. A failed claim is reread and terminalized as `unavailable` only while the same accepted version remains authoritative; otherwise the route returns explicit `recovery_required` and operators must reconcile status manually. Malformed, mismatched, timeout, or persistence outcomes do not trigger automatic redispatch.

The provider receipt binds the n8n execution reference to the request ID and fingerprint. The package has no embedded credentials and permits only the exact status/precheck, no-side-effect policy.

## Files

- `automations/catalog/index.json`
- `automations/catalog/linkautowork-connection-health/1.0.0/automation.json`
- `automations/catalog/linkautowork-connection-health/1.0.0/config.schema.json`
- `automations/catalog/linkautowork-connection-health/1.0.0/input.schema.json`
- `automations/catalog/linkautowork-connection-health/1.0.0/output.schema.json`
- `automations/catalog/linkautowork-connection-health/1.0.0/workflow.json`
- `automations/catalog/linkautowork-connection-health/1.0.0/operations/runbook.md`
- `gateway/src/app.ts`
- `gateway/src/config/env.ts`
- `gateway/src/integrations/n8n-client.ts`
- `gateway/src/services/provider-route-service.ts`
- `gateway/tests/provider-connection-health.test.ts`
- This handoff.

## Validation performed

- `npm test -- gateway/tests/provider-connection-health.test.ts gateway/tests/provider-routes.test.ts` — 20 passed.
- `npm run typecheck` — passed.
- `npm run test:catalog` — 182 passed, 1 skipped; the suite logged its expected mocked audit-RPC 403 warning.
- `npm run catalog:check` — passed.
- `git diff --check` — passed.
- No hosted CI, live workflow import/publish, webhook execution, database apply, or production acceptance was performed.

## Live boundary and recovery

From the existing gateway container network, `http://n8n:5678/healthz` returned HTTP 200 with status `ok`; the installed container reports n8n `2.30.0`. Read-only installed-source inspection confirmed Public API workflow listing supports an exact `name` filter and the workflow controller exposes `POST /api/v1/workflows/:id/activate`. Using the existing GSM API key in-process (never printed or persisted), the exact canary workflow query returned HTTP 200 with no match; credential metadata also returned HTTP 200 with no exact Header Auth credential. No workflow or credential was created, activated, or executed.

The host-only `n8n.linktrend.internal` URL timed out from this machine; that did not block the in-container read-only checks. Live import and canary execution remain unverified. The gateway candidate is not deployed, and no dedicated canary webhook token is configured in production yet.

If a dispatched request remains `running`, or the route returns `recovery_required`, do not resubmit. Read the durable request/receipt status and reconcile manually using the fixed runbook. A timeout or malformed success response is ambiguous and must not be retried automatically.

## Handoff state

At handoff, candidate source is uncommitted on the issue branch. Independent exact-head review, checkpoint push/admission, and any n8n live proof remain pending. No pre-existing worktree changes were observed.
