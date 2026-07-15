# How LiNKautowork Works (Plain English)

This document explains the project in plain language for operators, non-engineers, and new contributors.

## 1) What this project is

LiNKautowork is the internal automation engine.

Think of it as a reliable operations machine that runs workflows on a self-hosted n8n instance.

The core idea is simple:

1. Define workflow templates once.
2. Keep those templates in this repo as the source of truth.
3. Deploy them to n8n.
4. Run them safely with strict contract checks, logging, and governance approvals.

## 2) The most important rule

`automations/templates` is the authority.

If there is ever a mismatch between this repo and any copied workflows in AIOS, this repo wins.

AIOS copies are mirrors for integration, not the master source.

## 3) What "internal-only" means right now

This MVO only serves one internal tenant.

The machine contract tenant ID is:

- `00000000-0000-0000-0000-000000000001`

The human-friendly label is:

- `linktrend_internal`

Any request with the wrong tenant UUID is rejected.

## 4) High-level architecture

There are 4 main parts:

1. Templates (`automations/templates`)
- JSON workflow definitions.
- Governance, ritual, and operational workflows live here.

2. Gateway service (`gateway/`)
- The policy/security front door.
- Verifies signatures and service tokens.
- Checks tenant and mission lineage.
- Pulls secrets just-in-time from Google Secret Manager.
- Sends valid requests to n8n.
- Writes execution records to Supabase.
- Publishes events to NATS.

3. n8n runtime (`deploy/dev` and `deploy/prod`)
- Executes workflow logic.
- Uses a Supabase/Postgres backend. n8n's own tables live in the isolated `lautowork_n8n` schema, which n8n creates and manages itself. Dev and prod are separated at the Supabase-project level (`linkplatform-stage` / `linkplatform-prod`), not by a schema-name suffix (the old `lautowork_n8n_dev` / `lautowork_n8n_prod` split is retired — see ADR 0001).

4. Data and event plane
- Supabase: audit and control-plane state.
- NATS: event distribution.
- Event compatibility: publishes to canonical `aios.*` subjects and optional `linkautowork.v1.*` mirror subjects.

## 5) How a request flows end-to-end

Example: urgent internal event

1. Internal system sends request to gateway `/v1/ingress/:workflowId`.
2. Gateway checks headers:
- `x-link-service`
- `x-link-service-token`
- `x-link-signature`
- `x-link-timestamp`
- `x-link-nonce`
3. Gateway validates HMAC signature and blocks replayed nonces.
4. Gateway verifies tenant UUID and required mission lineage IDs.
5. Gateway fetches required secrets from GSM.
6. Gateway dispatches to the corresponding n8n webhook.
7. Gateway logs canonical telemetry to Supabase `audit_runs` via RPC.
8. Gateway publishes event to NATS (`aios.*`, plus optional internal mirror).

If anything fails policy checks, the request is rejected before n8n runs it.

## 6) Daily ritual windows (Taipei time)

A unified scheduler workflow runs at:

- `08:00` strategic feed
- `10:45` operational pulse (COO report)
- `14:45` quality feed

This means LiNKautowork feeds all required decision windows.

When a data source is incomplete, the system still sends a partial report on time and marks confidence/degradation instead of silently dropping output.

## 7) Governance and approvals in simple terms

Workflow promotions move through fixed states:

`draft -> dev_tested -> qa_approved -> ops_approved -> prod_deployed -> deprecated -> archived`

Approval logic:

- `qa_approved`: Auditor + Head of Quality
- `ops_approved`: Auditor + Head of Quality + COO
- Protected decisions (for example restore/promotion actions with governance risk): Principal approval required

This is enforced by gateway lifecycle transition validation.

## 8) Kill switch behavior in plain words

There are 2 levels:

1. Scoped kill switch
- Stops one tenant/workflow path.
- Used for local quality/security failures.

2. Global kill switch
- Deactivates active webhook exposure platform-wide.
- Used for major incidents (security crisis, runaway cost, systemic rate-limit failure).

Restore requires governed approval flow and audit evidence.

## 9) Where to make changes

If you want to change workflow behavior:

- Edit templates in `automations/templates`.
- Validate with `npm run validate:templates`.
- Import into n8n with `ops/import-templates-to-n8n.sh`.
- Export runtime snapshot with `ops/export-live-from-n8n.sh dev`.

If you want to change policy/security rules:

- Edit gateway code in `gateway/src`.
- Run `npm run ci`.

If you want to change infrastructure/runtime settings:

- Edit `deploy/dev/docker-compose.yml` and `deploy/prod/docker-compose.yml`.
- Update `.env` files under each deploy directory.

## 10) Operational scripts you will actually use

- `ops/sync-templates-to-aios.sh`
- `ops/import-templates-to-n8n.sh`
- `ops/export-live-from-n8n.sh dev|prod`
- `ops/run-evals.sh`
- `ops/run-backup.sh`
- `ops/restore-drill.sh <db-backup.sql.gz> <templates-backup.tar.gz>`

## 11) How safety is enforced (without jargon)

- Every important request must prove who sent it.
- Every request must carry trace IDs so you can reconstruct what happened.
- Every run is logged to a canonical audit table.
- Events are broadcast in a standard way for the rest of the system.
- Dangerous situations can be stopped quickly by kill switch.
- Restarts and restores are controlled and traceable.

## 12) What this project is not yet (by design)

This MVO does not include:

- External client self-service onboarding
- Billing/commercial marketplace features
- Full autonomous Gate 1/Gate 2 commercialization logic
- HA topology

Those are intentionally deferred to later gates.

## 13) Quick mental model for new team members

If you remember only this:

- Templates here are the truth.
- Gateway is the enforcer.
- n8n is the executor.
- Supabase is the audit memory.
- NATS is the event bloodstream.
- Governance decides what is allowed into production.
