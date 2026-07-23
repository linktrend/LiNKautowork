# LiNKautowork — Open Issues & Build Log

**Role:** Append-only engineering build / compliance log for this Program. Prefer this file over stale prose elsewhere when asking "what was actually built, deferred, or limited?"

**Current source of truth for product description:** [`LINKAUTOWORK-INTENT.md`](./LINKAUTOWORK-INTENT.md), [`LINKAUTOWORK-TECHNICAL-PRD.md`](./LINKAUTOWORK-TECHNICAL-PRD.md), [`LINKAUTOWORK-OPERATIONS-MANUAL.md`](./LINKAUTOWORK-OPERATIONS-MANUAL.md).

**History note:** This file was renamed from root `IMPLEMENTATION_AGAINST_PRD.md` on 2026-07-19 (documentation cleanup). Sections 1–12 below are the preserved MVO implementation trace against the original PRD; path references inside them were updated to `docs/archive/...` where those docs moved. New dated entries append after that baseline.

---

# Baseline — MVO Implementation Against PRD (preserved)

Document purpose (original):

- Provide a comprehensive, implementation-level trace from the PRD to what is now built in this repository.
- Show where each PRD requirement is implemented, how it is enforced, and what remains intentionally deferred.

Reference PRD (archived):

- `docs/archive/root-docs/260319 - PRD_ LiNKautowork Automation Engine.md`

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
- Contract docs: `docs/archive/CONTRACTS.md` (superseded; see Technical PRD), `docs/archive/AUTOMATION_LIFECYCLE.md` (superseded; see Technical PRD), `docs/SLO.md`

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

- Canonical internal-org constants: `gateway/src/constants/org.ts`
- Tenant/org enforcement: `gateway/src/lib/tenant.ts`, `gateway/src/app.ts`
- Audit RPC integration: `gateway/src/integrations/supabase-rpc.ts`
- Supabase schema + RLS + RPC function: `supabase/migrations/20260715_000001_lautowork_control_core.sql`
- JIT secret retrieval: `gateway/src/integrations/secrets-provider.ts`

Schema/org-model update (2026-07-15, `docs/archive/adr/0001-adopt-shared-platform-org-model.md`):

- The control/ledger surface is now a single `lautowork` schema (`audit_runs`, `lifecycle_transitions`, `killswitch_events`), replacing the retired two-schema `linkautowork_audit` / `linkautowork_control` split.
- Each control table is org-scoped via `org_id uuid references platform.organizations(id)` (replacing the old bare `tenant_id uuid`), with RLS that OR's the JWT tenant-claim fast-path against a real `platform.has_org_access()` membership check.
- The exposed RPC keeps its published name `public.linkautowork_write_audit_run` (preserving the `SUPABASE_AUDIT_RPC` gateway contract) and still accepts a wire parameter literally named `tenant_id`, which it writes into the `org_id` column. Gateway internals were renamed to `org` (`constants/org.ts`, `AuditRecord.orgId`); the external env-var names (`ACTIVE_TENANT_*`) and inbound mission field (`tenantId`) are deliberately unchanged.
- The prior `ops/sql/001_mvo_schema.sql` was archived to `ops/sql/archive/` (confirmed never applied to any live database).

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
- `docs/archive/AUTOMATION_LIFECYCLE.md` (superseded; see Technical PRD)

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
  - `supabase/migrations/20260715_000001_lautowork_control_core.sql` (`lautowork` control schema)
  - `supabase/migrations/20260715_000002_lautowork_n8n_isolation.sql` (isolated `lautowork_n8n` schema + `svc_lautowork_n8n` role)

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
- `docs/archive/CONTRACTS.md` (superseded; see Technical PRD)

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


---

## 13. Documentation cleanup — four new source-of-truth documents, legacy docs archived, this file renamed — 2026-07-19

Following the same Principal-requested process already completed on sibling repo LiNKdeveloper (2026-07-18, their OPEN-ISSUES item #43), performed the documentation source-of-truth cleanup for LiNKautowork.

**New source-of-truth documents created** (drafted against real code — compose pins, gateway routes, Supabase migrations, live `automations/templates/manifest.json` — not only the archived PRD/plain-English prose):

- `docs/LINKAUTOWORK-INTENT.md` — why this Program exists, scope, out-of-scope, success criteria.
- `docs/LINKAUTOWORK-TECHNICAL-PRD.md` — exhaustive technical reference (architecture, terminology, n8n+gateway, Supabase `lautowork` / `lautowork_n8n`, link-n8n fork subsection, rituals, kill-switch/lifecycle, dual NATS subjects, LiNKplatform org-model integration, directory map, deferred items, and a §12 table of factual discrepancies vs archived docs).
- `docs/LINKAUTOWORK-OPERATIONS-MANUAL.md` — plain-English handbook for the Principal (non-technical audience), adapted from the archived plain-English doc and verified against current code.
- This file — `docs/OPEN-ISSUES.md` — renamed via `git mv` from root `IMPLEMENTATION_AGAINST_PRD.md` so the running implementation/compliance log has an intuitive name matching LiNKdeveloper's convention (placed under `docs/` to match this repo's docs layout).

**Legacy documentation archived to `docs/archive/`** (moved, not deleted; `docs/archive/README.md` explains the supersession and links back to the 4 new documents):

- Root: `260319 - PRD_ LiNKautowork Automation Engine.md`, `HOW_THIS_PROJECT_WORKS_PLAIN_ENGLISH.md`, `GIT_STRATEGY.md` → `docs/archive/root-docs/`
- `docs/UPSTREAM.md`, `docs/AUTOMATION_LIFECYCLE.md`, `docs/CONTRACTS.md`, `docs/DOCUMENTATION_GOVERNANCE.md`, `docs/RELEASE_GATE_CHECKLIST.md`, `docs/BRANCHING_AND_DEPLOYMENT_POLICY.md`
- `docs/adr/0001-adopt-shared-platform-org-model.md` → `docs/archive/adr/` (code comments updated to the archived path; decisions remain implemented in migrations/gateway)

Every in-repo cross-reference to these old paths (README, AGENTS.md, Deploy Readiness, compose comments, gateway comments, ops/sql archive README) was updated — verified zero dangling references remain outside deliberately frozen artifacts. Explicitly excluded from path rewrites (untouched): `archive/legacy-dev-mirrors-2026-07-15/**`, `link-n8n/**`, and `supabase/migrations/**` (migration SQL comments still cite the ADR path as historical authority text; migrations are not edited in doc cleanups).

**Explicitly NOT archived:**

- `docs/runbooks/*`, `docs/SLO.md`, `docs/DEPLOY_READINESS.md` — still used for real operations / DONE definition.
- `archive/legacy-dev-mirrors-2026-07-15/**` — pre-existing bulk archive; left completely untouched.
- `link-n8n/**` — nested separate git repo / submodule; documented inside the Technical PRD only; no file changes.

**`README.md` rewritten** to point at the 4 new documents as source of truth and to correct stale "Root Documents" claims.

**Verification performed after structural changes:** `npm run ci`, `ops/security/scan-secrets.sh`, `ops/validate-env-contract.sh`, `bash -n` on ops scripts, `docker compose … config` for dev/prod — pure documentation/file-organization pass; no `gateway/src` behavior changes beyond comment path updates.

**What this deliberately does NOT do:** delete any archived document (moved only); touch `link-n8n/**` or `archive/legacy-dev-mirrors-2026-07-15/**`; invent a separate Intent/PRD/Ops-manual set for the n8n fork; edit archived document *content* beyond the archive index README.

---

## 14. Drop `linktrend/link-n8n` fork / submodule — stock upstream n8n only — 2026-07-23

**Principal decision:** LiNKautowork does not need a custom fork of n8n. Compose already ran stock `docker.n8n.io/n8nio/n8n:2.30.0`; customizations live in `gateway/`, templates, Supabase, GSM, NATS — not in n8n core.

**Removed:**

- Git submodule `link-n8n` (`.gitmodules` entry pointing at `https://github.com/linktrend/link-n8n.git`)
- Working-tree `link-n8n/` directory and `.git/modules/link-n8n`
- Live docs claiming a required LiNKtrend n8n fork / submodule

**Documented:**

- Technical PRD §5 rewritten to “stock upstream n8n only”
- Intent / Ops Manual / Deploy Readiness / README updated
- `docs/archive/UPSTREAM.md` marked retired; archived ADR 0001 carries a supersession note for the submodule conversion
- Remote GitHub `linktrend/link-n8n` **not** deleted — unused/orphan; Principal may archive later

**Unchanged:** gateway behavior, live templates, Compose image pin `2.30.0`, Supabase migrations, secrets.

**Verify:** `git submodule status` empty of `link-n8n`; `npm run ci` green; no live docs require the fork.
