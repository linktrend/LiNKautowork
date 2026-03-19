# LiNKautowork MVO Implementation Against PRD

Document purpose:

- Provide a comprehensive, implementation-level trace from the PRD to what is now built in this repository.
- Show where each PRD requirement is implemented, how it is enforced, and what remains intentionally deferred.

Reference PRD in this repo root:

- `260319 - PRD_ LiNKautowork Automation Engine.md`

Implementation baseline date:

- March 19, 2026 (Asia/Taipei)

## 1) Executive Summary Mapping

PRD intent:

- LiNKautowork as autonomous nervous system, productized via n8n workflows, deterministic operations, and integration bridge between LiNKskills, LiNKsites/apps, and LiNKbrain.

Delivered in MVO:

- Self-hosted n8n Community runtime with separate `dev` and `prod` stacks.
- Canonical template authority in `automations/templates`.
- Dedicated policy gateway enforcing signed ingress, canonical tenant contract, and mission lineage.
- Canonical audit write path to Supabase RPC.
- Event bridge to primary `aios.*` subjects plus internal mirror `linkautowork.v1.*`.
- Governance and kill-switch controls aligned with operational requirements.

Primary implementation artifacts:

- Gateway: `gateway/src/*`
- Templates: `automations/templates/*`
- Deploy: `deploy/dev/*`, `deploy/prod/*`, `deploy/common/*`
- Ops and SQL: `ops/*`
- Contract docs: `docs/CONTRACTS.md`, `docs/AUTOMATION_LIFECYCLE.md`, `docs/SLO.md`

## 2) Business Logic and Monetization Layer (PRD Section 2)

### 2.1 Automated Utility Thesis

Implemented:

- Workflow templates are versioned assets in source control.
- Operational workflow management scripts support deterministic import/export and evidence capture.

Evidence:

- `automations/templates/manifest.json`
- `ops/import-templates-to-n8n.sh`
- `ops/export-live-from-n8n.sh`

### 2.2 Revenue and Delivery Models

MVO stance:

- Internal utility model is implemented.
- External commercialization paths (marketplace, external self-service, billing) are intentionally deferred.

Evidence:

- Internal-only tenant enforcement in gateway (`ACTIVE_TENANT_UUID` policy).
- No marketplace/public billing endpoints implemented.

### 2.3 Client Data Isolation Requirements

Implemented now (MVO-safe contracts):

- Canonical internal tenant UUID required in machine contracts:
  - `00000000-0000-0000-0000-000000000001`
- Tenant mismatch hard reject in gateway and templates.
- Canonical audit table with RLS enabled.
- RPC-only write path for audit insertion.
- JIT secrets retrieval in pre-run gateway layer via Google Secret Manager client.

Evidence:

- Tenant constants: `gateway/src/constants/tenant.ts`
- Tenant enforcement: `gateway/src/lib/tenant.ts`, `gateway/src/app.ts`
- Audit RPC integration: `gateway/src/integrations/supabase-rpc.ts`
- Supabase schema + RLS + RPC function: `ops/sql/001_mvo_schema.sql`
- JIT secret retrieval: `gateway/src/integrations/secrets-provider.ts`

Important clarification:

- Full commercial multi-tenant operational isolation is not declared complete in MVO. Contracts are enforced now to make Gate 1+ transition deterministic.

## 3) Automation Anatomy (PRD Section 3)

PRD Unit components and implementation mapping:

1. Workflow (JSON)
- Implemented and versioned in `automations/templates/`.
- Canonical source authority explicitly documented and enforced operationally.

2. Telemetry Hook
- Implemented through gateway event and audit paths.
- Templates call gateway event publish route; gateway writes canonical audit runs.

3. Research Doc (Genesis)
- Partially implemented at system level through repository docs and PRD traceability.
- Template-specific market research dossiers are not fully authored per-template in this pass.

4. Evals Suite
- Implemented baseline with versioned synthetic and replay assets.
- Dirty-data suite includes 120 scenarios.
- Known-failure replay set included.

Evidence:

- Templates: `automations/templates/*.json`
- Eval assets: `automations/evals/scenarios/urgent-event-ingestion-dirty-data.json`, `automations/evals/replays/known-failures.json`
- Eval helper script: `ops/run-evals.sh`

## 4) Operational Framework and Promotion Path (PRD Section 4)

### 4.1 Autoworker Squad Roles

Implemented as system controls and workflow/policy constraints rather than persona code.

Evidence:

- Lifecycle approval requirements enforced in code path:
  - `gateway/src/services/lifecycle.ts`
  - `gateway/src/app.ts` (`/v1/lifecycle/transition`)

### 4.2 Karpathy Self-Research Loop

Implemented baseline enforcement mechanisms:

- Synthetic dirty-data eval assets.
- Known-failure replay assets.
- Lifecycle gate controls for promotion.

Evidence:

- `automations/evals/*`
- `automations/templates/manifest.json`
- `docs/AUTOMATION_LIFECYCLE.md`

### 4.3 LiNKskills Promotion Path

Implemented in MVO-compatible governance primitives:

- Lifecycle transitions and protected-action approvals.
- Event/audit recording for deterministic traceability.

Deferred:

- Autonomous cross-venture detection and fully automated skill promotion orchestration (Gate 1+).

## 5) Review Rituals and Governance (PRD Section 5)

### Operational Gate #2 at 10:45 Asia/Taipei

Implemented explicitly as required MVO output.

Evidence:

- Unified ritual scheduler template:
  - `automations/templates/ritual-gates-unified.json`
- Scheduler runs at:
  - `08:00` strategic
  - `10:45` operational
  - `14:45` quality
- Operational output includes confidence/degraded signaling and publishes to:
  - Slack
  - NATS via gateway
  - canonical audit path via gateway

Cross-system ritual alignment implemented:

- 08:00 and 14:45 windows included to feed strategic and quality decision windows.

## 6) Technical Architecture (PRD Section 6)

### 6.1 Hosting and Environment

Implemented:

- Self-hosted n8n Community runtime via Docker Compose.
- One instance per environment (`dev`, `prod`).
- Supabase used for audit/logging and control-plane baseline schema.
- Gateway service introduced as integration layer for policy/security/telemetry.
- NATS event bus provided in stacks.

Evidence:

- Deploy files:
  - `deploy/dev/docker-compose.yml`
  - `deploy/prod/docker-compose.yml`
  - `deploy/common/gateway.Dockerfile`
- Supabase baseline:
  - `ops/sql/001_mvo_schema.sql`

### 6.2 Security and Risk Management

Implemented:

- Signed ingress with HMAC-SHA256 + timestamp + nonce replay window.
- Service token validation.
- Canonical tenant enforcement.
- Kill-switch hierarchy:
  - Scoped halt for local failures.
  - Global webhook revocation via n8n API deactivation.

Evidence:

- Signing and auth:
  - `gateway/src/lib/signing.ts`
  - `gateway/src/middleware/auth.ts`
- Kill switch:
  - `gateway/src/services/killswitch.ts`
  - control routes in `gateway/src/app.ts`
- Security exception workflow:
  - `automations/templates/security-exception-response.json`

## 7) Development Roadmap Gates (PRD Section 7)

### Phase 1 MVO (in scope)

Implemented:

- Stable runtime baseline (n8n + gateway + NATS, dev/prod topology).
- Canonical template and lifecycle governance model.
- Auditability and event interoperability.
- Ritual workflows and operations scripts.

### Gate 1 and Gate 2 (out of scope by decision)

Deferred intentionally:

- Autonomous bot-driven JSON self-editing loops as production autonomy feature.
- Public marketplace/API commercialization and external client self-service provisioning.

## 8) Contracts Implemented

Canonical tenant and identity:

- Machine contract tenant UUID: `00000000-0000-0000-0000-000000000001`
- Slug label only: `linktrend_internal`

Ingress contract enforcement:

- Required lineage fields in mission envelope (`missionId`, `runId`, `taskId`, `dprId`, `triggerSource`).
- Signed ingress headers required and validated.

Audit contract:

- Canonical fields in `audit_runs` implemented via RPC.
- Required details fields captured in gateway write path.

Event contract:

- Primary interoperability subjects:
  - `aios.ritual.strategic`
  - `aios.ritual.operational`
  - `aios.ritual.quality`
  - `aios.workflow.execution`
  - `aios.security.exception`
  - `aios.killswitch`
  - `aios.lifecycle.transition`
- Internal mirror subjects:
  - `linkautowork.v1.*` equivalents

Evidence:

- `gateway/src/services/event-bridge.ts`
- `docs/CONTRACTS.md`

## 9) Test and Quality Coverage Implemented

Automated checks:

- Template shape and canonical tenant validation script.
- Gateway unit tests for:
  - signature verification
  - event subject mapping
  - lifecycle transition controls
  - kill-switch behavior
  - tenant enforcement

CI pipeline:

- Validates templates.
- Runs tests.
- Runs typecheck.
- Shell syntax check for ops scripts.

Evidence:

- `scripts/validate-templates.mjs`
- `gateway/tests/*.test.ts`
- `.github/workflows/ci.yml`

## 10) Reliability and Operations Coverage

Implemented:

- Backup script (DB dump + template/eval archive).
- Restore drill validation script.
- Baseline SLO document and alert rules.

Evidence:

- `ops/run-backup.sh`
- `ops/restore-drill.sh`
- `docs/SLO.md`
- `ops/alerts/prometheus-rules.yml`

## 11) PRD Compliance Snapshot

Implemented in MVO:

- Self-hosted n8n runtime (dev/prod, single-instance per env).
- Canonical templates and lifecycle governance.
- 10:45 Operational Gate as explicit workflow/output.
- 08:00 and 14:45 alignment feeds.
- Canonical tenant UUID enforcement in cross-system contracts.
- Signed ingress + JIT secret retrieval in gateway.
- Dual event publishing with `aios.*` primary.
- Scoped and global kill-switch hierarchy.
- Canonical audit runs via RPC + baseline RLS policy.
- Eval assets and CI verification.

Partially implemented / structured for next phase:

- Full per-template research dossier depth.
- Full commercial multi-tenant runtime separation enforcement beyond MVO internal-tenant operation.
- Gate 1 autonomous refinement and Gate 2 commercialization features.

## 12) Commands Used for Verification During Build

Validated during implementation:

- `npm run ci`
- `npm run build`
- `bash -n ops/*.sh`
- `docker compose -f deploy/dev/docker-compose.yml config`
- `docker compose -f deploy/prod/docker-compose.yml config`

Result:

- All checks above passed with current repository state.
