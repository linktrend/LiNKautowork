# LiNKautowork — Technical PRD

**Status:** Technical reference for the LiNKautowork Program as actually built in this repository (verified against `gateway/src/**`, `deploy/**`, `supabase/migrations/**`, `automations/templates/**`, and ops scripts as of 2026-07-19).

**Ground rule:** Code is the source of truth. Where older docs (now under `docs/archive/`) disagree with code, this document follows the code and calls out the discrepancy in §12.

**Companion:** [`LINKAUTOWORK-INTENT.md`](./LINKAUTOWORK-INTENT.md) — why this Program exists.

---

## 1. System overview / architecture

LiNKautowork is **not** "n8n with some scripts." It is a small control plane around an execution engine:

| Layer | Implementation |
|---|---|
| **Execution** | Stock Docker image `n8nio/n8n:2.30.0` (Compose/evaluator exact-reference pin); workflows imported from `automations/templates/` |
| **Policy / security** | Express gateway (`gateway/`) — signed ingress, service/control tokens, tenant check, kill-switch, lifecycle, Slack actions |
| **Secrets** | Google Secret Manager via `SecretsProvider` + env `*_SECRET_NAME` contract |
| **Control ledger** | Supabase schema `lautowork` — `audit_runs`, `lifecycle_transitions`, `killswitch_events` + public RPCs |
| **n8n data isolation** | Schema `lautowork_n8n` + role `svc_lautowork_n8n` (n8n owns tables on first boot) |
| **Events** | persistent NATS JetStream (`nats:2.10.26-alpine` in Compose); `linkautowork.v1.*` subjects |
| **n8n source of truth** | Upstream `https://github.com/n8n-io/n8n` releases / official Docker images — no LiNKtrend fork in this Program |

### Process topology (one environment)

```
Caller / ritual / ops tool
  └─ HTTPS → gateway (:8080)
       ├─ /health, /metrics
       ├─ /v1/ingress/:workflowId     → validate → GSM secrets → n8n webhook → audit + NATS
       ├─ /v1/events/publish          → NATS (+ audit)
       ├─ /v1/lifecycle/transition    → validate approvals → persist → NATS
       ├─ /v1/control/killswitch/*    → activate/release → persist → (global: deactivate n8n workflows)
       └─ /v1/slack/actions           → Slack-signed lifecycle path
  n8n (:5678)  ← webhook / schedule / editor (Tailscale-bound in prod)
  NATS (:4222, prod also :8222 monitor)
  Supabase (linkplatform-stage | linkplatform-prod)
```

Stage stack: `deploy/dev/docker-compose.yml`. Prod stack: `deploy/prod/docker-compose.yml` (Traefik labels + `linktrend-network`, `restart: unless-stopped`).

---

## 2. Terminology glossary

| Term | Meaning |
|---|---|
| **MVO** | Minimum Viable Operations — current delivered bar (internal utility, not marketplace) |
| **Gateway** | The Express policy service in `gateway/` |
| **Mission envelope** | Required lineage object: `tenantId`, `missionId`, `runId`, `taskId`, `dprId`, `triggerSource` (+ optional capability/package ids) |
| **Canonical internal org** | UUID `00000000-0000-0000-0000-000000000001`, slug `linktrend_internal` (`gateway/src/constants/org.ts`) |
| **Tenant (wire)** | Mission/env still say `tenantId` / `ACTIVE_TENANT_*`; value is written to DB as `org_id` |
| **Template** | Versioned n8n workflow JSON under `automations/templates/` |
| **Lifecycle state** | One of `draft → dev_tested → qa_approved → ops_approved → prod_deployed → deprecated → archived` |
| **Protected action** | Lifecycle transition requiring Principal (`chairmanApproved`) |
| **Kill switch (scoped)** | Blocks ingress for one `tenantId:workflowId` pair |
| **Kill switch (global)** | Blocks all ingress + deactivates active n8n workflows via Public API |
| **Ritual windows** | Scheduled Taipei-time gates: 08:00 strategic, 10:45 operational, 14:45 quality |
| **Event subjects** | `linkautowork.v1.*` NATS subjects for explicitly wired cross-Program interoperability |

---

## 3. n8n runtime + gateway architecture

### 3.1 Compose runtime

Both environments share the same three services:

1. **nats** — `nats:2.10-alpine` with `-js` (JetStream).
2. **gateway** — built from `deploy/common/gateway.Dockerfile` (repo root context); healthcheck `GET /health` on `:8080`.
3. **n8n** — `n8nio/n8n:2.30.0`; `DB_POSTGRESDB_SCHEMA=lautowork_n8n`; `GENERIC_TIMEZONE` / `TZ=Asia/Taipei`; `N8N_PUBLIC_API_DISABLED=false` (required for template import + global kill-switch).

Security baseline on containers: `no-new-privileges`, `cap_drop: ALL`. Prod n8n joins external `linktrend-network` for Traefik (`Host(n8n.linktrend.internal)`).

### 3.2 Gateway routes (authoritative)

From `gateway/src/app.ts`:

| Method | Path | Auth | Behavior |
|---|---|---|---|
| GET | `/health` | none | Status, active tenant, kill-switch snapshot |
| GET | `/metrics` | none | Prometheus registry |
| POST | `/v1/ingress/:workflowId` | signed ingress + rate limit 120/min | Tenant check → kill-switch → JIT secrets → n8n webhook → audit + `workflow.execution` event |
| POST | `/v1/events/publish` | internal service token | Publish mapped NATS subjects + audit |
| POST | `/v1/lifecycle/transition` | control token | Validate transition/approvals → persist lifecycle → event + audit |
| POST | `/v1/control/killswitch/scoped` | control token | Activate/release scoped block + persist + event |
| POST | `/v1/control/killswitch/global` | control token | Activate (deactivate all n8n workflows) / release + persist + event |
| POST | `/v1/slack/actions` | Slack signing secret | Parse lifecycle payload; publish event (does **not** currently call `writeLifecycleTransition`) |

Boot (`bootstrapApp`): connect NATS → `killSwitchService.hydrate()` from DB → serve app.

### 3.3 Ingress security

- Headers: `x-link-service`, `x-link-service-token`, `x-link-signature` (HMAC-SHA256), `x-link-timestamp`, `x-link-nonce`.
- Raw body captured for signature verification (`middleware/raw-body.ts`).
- Replay window default 300s (`REPLAY_WINDOW_SECONDS`) via in-memory `NonceStore`.
- Canonical tenant: `assertCanonicalTenant(mission.tenantId, ACTIVE_TENANT_UUID)`.

### 3.4 Secrets

`SecretsProvider` resolves named secrets from GSM at ingress time (`requiredSecrets` on the request). Env loading (`loadEnv`) also resolves HMAC/service/control tokens, Supabase service role, n8n API key, and optional Slack signing secret from GSM when direct values are absent.

---

## 4. Supabase schemas

Prerequisite: LiNKplatform `platform` foundation (`platform.organizations`, `platform.has_org_access`, …) on the same project.

### 4.1 `lautowork` (control)

Migration `supabase/migrations/20260715_000001_lautowork_control_core.sql`:

| Table | Purpose |
|---|---|
| `lautowork.audit_runs` | Append-only execution/audit ledger (`org_id`, run/task/dpr, status, token_usage, command_log, details) |
| `lautowork.lifecycle_transitions` | Append-only promotion history (`workflow_id` free-text template id today) |
| `lautowork.killswitch_events` | Append-only kill-switch activate/release log |

Roles: `svc_lautowork_runtime` (DML), `svc_observer` (read). RLS OR's JWT `tenant_id` claim fast-path with `platform.has_org_access(org_id, 'client_viewer')`.

Public RPCs (wire param still named `tenant_id`, written into `org_id`):

| RPC | Role |
|---|---|
| `public.linkautowork_write_audit_run` | Ingress/event audit writes |
| `public.linkautowork_write_killswitch_event` | Persist kill-switch events (2026-07-18) |
| `public.linkautowork_write_lifecycle_transition` | Persist lifecycle (2026-07-18) |
| `public.linkautowork_active_killswitches` | Hydrate active global/scoped switches from event log |

Persistence RPCs: `supabase/migrations/20260718_000001_lautowork_control_persistence.sql`.

### 4.2 `lautowork_n8n` (runtime isolation)

Migration `supabase/migrations/20260715_000002_lautowork_n8n_isolation.sql`:

- Creates empty schema + `svc_lautowork_n8n` with full privileges on that schema only.
- **No tables created by LiNKautowork** — n8n migrates itself on first boot.
- Hard isolation: control roles are **not** granted access.

Env separation is at **Supabase project** level (`linkplatform-stage` vs `linkplatform-prod`), not `_dev`/`_prod` schema suffixes.

---

## 5. Upstream n8n (stock only — no LiNKtrend fork)

**Principal decision 2026-07-23:** LiNKautowork does **not** maintain or require a custom fork of n8n (`linktrend/link-n8n` is unused and not part of this Program). Customizations live outside n8n core: `gateway/`, `automations/templates/`, Supabase `lautowork*`, GSM, NATS, and platform contracts.

| Surface | Location |
|---|---|
| Gateway, templates, deploy, ops, control migrations | **This repo** (`LiNKautowork`) |
| n8n engine source of truth for upgrades | Upstream `https://github.com/n8n-io/n8n` releases |
| What Compose runs | Official image `n8nio/n8n:2.30.0` (exactly matches evaluator reference; never `:latest`) |
| Full upstream tree vendored in this repo | **No** — not needed for MVO; do not add an `n8n-io/n8n` submodule without a concrete build-from-source reason |

**Rules:**

1. Bump the Compose image pin when upgrading n8n (document why in the same change). Prefer official published tags.
2. Canonical workflow templates stay in `automations/templates/` — never inside an n8n source tree.
3. Patching n8n core itself is a **new Principal decision**, not the current architecture.
4. The remote GitHub repo `linktrend/link-n8n` (if still present) is orphan/unused for this Program and may be archived later by the Principal — LiNKautowork no longer references it.

---

## 6. Ritual windows and scheduling

Authoritative template: `automations/templates/ritual-gates-unified.json` (manifest: critical, `ops_approved`).

| Local time (Asia/Taipei) | Gate | Event type |
|---|---|---|
| 08:00 | Strategic | `ritual.strategic` → `linkautowork.v1.ritual.strategic` |
| 10:45 | Operational (COO pulse) | `ritual.operational` → `linkautowork.v1.ritual.operational` |
| 14:45 | Quality | `ritual.quality` → `linkautowork.v1.ritual.quality` |

Outputs are designed to publish to Slack + NATS (via gateway) + canonical audit. Degraded source data should still ship on schedule with an explicit confidence flag (template behavior; verify in live export evidence).

---

## 7. Kill-switch and lifecycle mechanisms

### 7.1 Lifecycle

States and allowed edges: `gateway/src/constants/lifecycle.ts`.

Approval rules (`gateway/src/services/lifecycle.ts`):

- `qa_approved` → auditor recommendation + Head of Quality.
- `ops_approved` → auditor + Head of Quality + COO.
- `protectedAction: true` → Principal (`chairmanApproved`) required.

Persisted via `writeLifecycleTransition` on `/v1/lifecycle/transition`. Slack path validates and publishes events but (as of this verify) does not write the lifecycle RPC — see §12.

### 7.2 Kill switch

`KillSwitchService` keeps in-memory global + scoped maps, **persists every activate/release**, and **hydrates from** `linkautowork_active_killswitches` on boot.

- Scoped: key `tenantId:workflowId`; ingress returns 503 when blocked.
- Global: calls `N8nClient.deactivateAllActiveWorkflows()` then blocks all ingress until release.

---

## 8. Event interoperability (`linkautowork.v1.*`)

`EventBridgeService` subject map (`gateway/src/services/event-bridge.ts`):

| `eventType` | Subject |
|---|---|
| `ritual.strategic` | `linkautowork.v1.ritual.strategic` |
| `ritual.operational` | `linkautowork.v1.ritual.operational` |
| `ritual.quality` | `linkautowork.v1.ritual.quality` |
| `workflow.execution` | `linkautowork.v1.workflow.execution` |
| `security.exception` | `linkautowork.v1.security.exception` |
| `killswitch` | `linkautowork.v1.killswitch` |
| `lifecycle.transition` | `linkautowork.v1.lifecycle.transition` |

Publish failures are logged as warnings (fail-soft on the event bus, not on ingress auth).

Payload always includes mission lineage fields + status + nested payload.

---

## 9. Integration with LiNKplatform and other Programs

### 9.1 Shared org model (ADR 0001)

Accepted decision (archived at `docs/archive/adr/0001-adopt-shared-platform-org-model.md`; still authoritative for *why*):

- Control tables carry `org_id uuid references platform.organizations(id)`.
- RLS uses `platform.has_org_access`.
- Wire/env keep `tenant_*` names for contract compatibility.
- Internal TypeScript uses `orgId` / `CANONICAL_INTERNAL_ORG_UUID`.

### 9.2 Other Programs

| Program | Relationship |
|---|---|
| **LiNKplatform** | Owns `platform.*` foundation; LiNKautowork is a Program schema on the shared stage/prod projects |
| **LiNKsites / LiNKdeveloper / …** | May publish to gateway ingress or consume `linkautowork.v1.*` when explicitly wired; no nested dependency on this repo's packages |
| **LiNKskills / LiNKbrain** | Original PRD described bridges; MVO delivers audit/events, not those products' core logic |
| **Historical program shells** | Not a supported dependency; retained only under the non-authoritative template archive |

---

## 10. Live template inventory and contracts

### 10.1 Live set (`automations/templates/manifest.json`, 2026-07-18)

| Template | Purpose | Criticality | State |
|---|---|---|---|
| `ritual-gates-unified.json` | Strategic / operational / quality ritual gates | critical | ops_approved |
| `urgent-event-ingestion.json` | Urgent event intake → gateway publish | critical | ops_approved |
| `promotion-review-governance.json` | Lifecycle promotion approvals | critical | ops_approved |
| `restore-authorization-governance.json` | Restore auth + scoped kill-switch | critical | ops_approved |

### 10.2 Ingress envelope (code)

Required mission fields + workflow object + `idempotencyKey` + optional `requiredSecrets` / `payload` — see `gateway/src/contracts/types.ts`.

### 10.3 Eval assets

Baseline under `automations/evals/` (dirty-data scenarios, known-failure replays) + `ops/run-evals.sh`. These support Gate-1-style refinement later; they are **not** a claim that autonomous JSON rewriting is live in production.

---

## 11. Package / directory map appendix

| Path | One-line description |
|---|---|
| `gateway/src/` | Policy gateway (Express app, auth, services, integrations) |
| `gateway/tests/` | Vitest unit tests (signing, tenant, lifecycle, kill-switch, events, audit, payload) |
| `automations/templates/` | Canonical live workflow JSON + `manifest.json` |
| `automations/templates/archive/` | Retired templates (incl. legacy Program shells) |
| `automations/evals/` | Synthetic / replay evaluation assets |
| `deploy/dev`, `deploy/prod` | Compose stacks + env examples |
| `deploy/common/gateway.Dockerfile` | Gateway image build |
| `supabase/migrations/` | `lautowork` + `lautowork_n8n` + persistence RPCs |
| `ops/*.sh` | Deploy, import/export, backup, GSM render, env contract, evals |
| `ops/security/` | Secret scan + Tailscale firewall installers |
| `ops/alerts/prometheus-rules.yml` | Baseline alert rules for SLO metrics |
| `scripts/validate-templates.mjs` | Template shape + canonical tenant validation |
| `docs/runbooks/` | Operator runbooks (keep live) |
| `docs/archive/` | Superseded documentation |
| `archive/legacy-dev-mirrors-2026-07-15/` | Pre-existing large archive — **out of scope / do not touch** |

---

## 12. Known doc drift (for reviewers)

Factual discrepancies between older (now archived) docs and current code:

| Claim in older docs | Actual code today |
|---|---|
| PRD "Autonomous Nervous System" with Scout/Architect bots editing JSON in production | MVO is gateway + templates + n8n; autonomous self-edit is deferred |
| PRD monetization / marketplace / Automation Packs | Deferred (Gate 2); internal utility only |
| Two control schemas `linkautowork_audit` / `linkautowork_control` | Single `lautowork` schema |
| `lautowork_n8n_dev` / `_prod` schema suffixes | Single `lautowork_n8n` per Supabase project |
| Kill-switch / lifecycle only in memory | Persisted + hydrate (2026-07-18 migration + gateway) |
| Compose builds/runs custom `link-n8n` image / keeps fork submodule | Stock `n8nio/n8n:2.30.0` only; fork submodule **removed** 2026-07-23 |
| `security-exception-response.json` as live evidence | File lives under **archived** templates, not the live manifest set |
| `IMPLEMENTATION_AGAINST_PRD` "gateway not deployed / tables have no writers" (early ADR finding) | Superseded: persistence writers exist; deploy readiness marks schemas applied — historical Finding text in archived ADR is a snapshot, not current ops state |
| Slack `/v1/slack/actions` fully equivalent to `/v1/lifecycle/transition` | Slack path validates + publishes event; does **not** call `writeLifecycleTransition` |
| Root README "Root Documents" pointing at PRD/implementation/plain-English | Superseded by Intent + Technical PRD + Ops Manual + OPEN-ISSUES |

---

## 13. Deferred items / honest gaps

Cross-checked against `docs/DEPLOY_READINESS.md` and archived PRD roadmap:

### Coding / product deferred (not claimed done)

1. **Gate 1 — Autonomous refinement** — bots editing production JSON via API for self-heal.
2. **Gate 2 — Marketplace / external SaaS provisioning.**
3. **Full commercial multi-tenant isolation** beyond the single internal org UUID.
4. **Per-template research dossiers** (PRD "Research Doc" anatomy) — not fully authored per template.
5. **RPC/env renames** — wire `tenant_id` / `ACTIVE_TENANT_*` → `org_*` (needs coordinated cross-service change).
6. **`lautowork.managed_automations` registry** — future parent table for workflow ids (ADR open question).
7. **Slack lifecycle path persistence** — align Slack handler with control-token route DB write.
8. ~~**Compose switch to fork-built image**~~ — **retired 2026-07-23**; Program uses stock upstream images only. Revisit only under a new Principal decision to patch n8n core.

### Ops inputs (not software holes — from Deploy Readiness)

- Choosing / provisioning the VPS.
- Filling real GSM secret values and Traefik hostnames.
- Slack channel wiring (optional for first smoke).
- First live bring-up executing `docs/runbooks/OPERATIONS.md` + release gate checklist content (see Operations Manual / runbooks).

### Reliability targets (live doc)

Kept in `docs/SLO.md` (critical ≥99%, non-critical ≥97%, ingest p95 ≤30s, briefing within 5 min of schedule, RTO ≤60 / RPO ≤15). Metrics: `linkautowork_ingress_dispatch_latency_ms`, `linkautowork_execution_outcome_total`, `linkautowork_killswitch_events_total`.

---

## 14. How to verify (structural)

```bash
npm ci
npm run ci          # validate:templates + test + typecheck
ops/validate-env-contract.sh
ops/security/scan-secrets.sh
bash -n ops/*.sh ops/security/*.sh
docker compose -f deploy/dev/docker-compose.yml config
docker compose -f deploy/prod/docker-compose.yml config
```

CI workflow: `.github/workflows/ci.yml` (also runs env contract + shell syntax + secret scan).

Branch policy: `.github/workflows/branch-source-policy.yml` — only `development`→`staging`→`main` for promotions; work branches `issue/*|dev/*|feature/*|fix/*|chore/*|…` into `development`.
