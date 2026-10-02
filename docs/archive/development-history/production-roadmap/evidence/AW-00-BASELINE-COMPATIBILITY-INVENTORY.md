# AW-00 baseline and compatibility inventory

**Status:** source-proof inventory only; all live behaviour and external state are `HOLD`.
**Executor session:** `019ff961-9b95-7780-b311-68c793c14ae9`
**Recorded:** 2026-08-13, Asia/Taipei
**Repository:** LiNKautowork
**Worktree:** `/Users/linktrend/Projects/LiNKautowork/.git/linktrend-worktrees/issue-80-implement-governed-deterministic-automation-prov`
**Branch:** `issue/80-implement-governed-deterministic-automation-prov`

## 1. Input identity and scope

The exact source input inspected before this artifact was committed:

- Commit SHA: `3f5f85703ae9dbb7537384bd667a6b6803d1a015`
- Input tree SHA: `d873eaaadac3329612e77aff63a43a700c4507ee`
- Base subject: `Merge pull request #77 from linktrend/issue/76-install-exact-ide-development-v2-1-10-corrected`
- Worktree state at intake: clean; no pre-existing changes were found.

This packet inspected repository source, local contracts, migrations, runbooks, templates, and evidence conventions only. No live gateway, n8n, Supabase, NATS, GSM, Slack, VPS, GitHub, Lisa, or OpenClaw target was queried. Therefore this document does not prove deployment, activation, schedules, credentials, migration application, health, or production parity.

Authoritative local boundaries are the approved production roadmap and packet index (`docs/production-roadmap/LINKAUTOWORK-PRODUCTION-ROADMAP.md:1-18`, `docs/production-roadmap/WORK-PACK-INDEX.md:1-34`), the frozen GAP v0.1 contract (`docs/specs/GOLDEN-AUTOMATION-PACKAGE-v0.1.md:1-9`), and ADR 0002 (`docs/adr/0002-golden-automation-package-source-authority.md:1-18`).

## 2. Active gateway routes and clients

### Routes observed in `gateway/src/app.ts`

| Surface | Routes | Source-level admission |
|---|---|---|
| Probe/telemetry | `GET /health`, `GET /metrics` | Unauthenticated in the route declaration; `/health` returns `status`, active tenant identifiers, and kill-switch snapshot, while `/metrics` returns the Prometheus registry (`gateway/src/app.ts:156-168`). |
| Compatibility ingress | `POST /v1/ingress/:workflowId` | Rate-limited, signed ingress; validates mission/tenant, kill switch, JIT secrets, then calls an n8n webhook, writes audit, and publishes an event (`gateway/src/app.ts:170-248`). The prior handoff explicitly classifies this as legacy compatibility while v2 is supported (`docs/handoffs/2026-08-04-wp05-instance-runtime.md:5-8`). |
| Event/callback | `POST /v1/events/publish`, `POST /v1/executions/callback` | Internal service token for publish; signed ingress plus callback capability for execution records (`gateway/src/app.ts:250-297`). |
| Provider-plane runtime | `POST /v2/instances/:instanceId/operations/:operation/execute`, `POST /v2/provisioning/run` | Internal service token plus platform invocation claim; binding, release, digest, input schema, pause, and kill-switch checks are source-enforced (`gateway/src/app.ts:299-314`, `gateway/src/services/instances/runtime.ts:34-75`). |
| Operations | `POST /v1/operations/monitor/run`, `GET /v1/operations/health`, `POST /v1/operations/maintenance/run`, `POST /v1/operations/incidents/transition`, `POST /v1/operations/actions`, `POST /v1/operations/retries/deliver`, `POST /v1/operations/deployments`, `POST /v1/operations/pauses` | Internal service token plus platform invocation claim (`gateway/src/app.ts:316-346`). |
| Automation Librarian | `POST /v1/librarian/automation/candidates`, `POST /v1/librarian/automation/candidates/:candidateId/review` | Internal service token, platform invocation claim, and institutional proposer/reviewer claim (`gateway/src/app.ts:348-367`). |
| Control | `POST /v1/control/librarian/automation`, `POST /v1/lifecycle/transition`, `POST /v1/control/killswitch/scoped`, `POST /v1/control/killswitch/global` | Control token; lifecycle and kill-switch routes persist/emit governed control records (`gateway/src/app.ts:369-518`). |
| Slack adapter | `POST /v1/slack/actions` | Slack HMAC timestamp/signature and rate limit; validates a lifecycle transition and publishes an approved event (`gateway/src/app.ts:530-581`). Source proof does not show a durable lifecycle write on this path, so the approval-to-transition persistence boundary is a later compatibility HOLD. |

### Wired clients and boundary credentials

The dependency graph constructs `N8nClient`, `NatsPublisher`, `SecretsProvider`, `SupabaseAuditClient`, runtime/provisioning/Librarian services, and the n8n operations executor (`gateway/src/app.ts:84-105`). The environment contract names Supabase PostgREST/RPC, n8n webhook/API, NATS, GSM, platform/Librarian claims, and optional Slack signing-secret inputs (`gateway/src/config/env.ts:5-60`, `gateway/src/config/env.ts:91-167`).

- n8n: webhook dispatch plus workflow list/get/create/delete/smoke/activation API (`gateway/src/integrations/n8n-client.ts:16-115`).
- Supabase: RPC-only governed writes and organisation-scoped runtime reads; service-role and scoped runtime JWT are distinct (`gateway/src/integrations/supabase-rpc.ts:53-99`).
- NATS: versioned event publisher; connection failure leaves a degraded publisher and publish failure is logged rather than retried (`gateway/src/integrations/nats-client.ts:5-29`, `gateway/src/services/event-bridge.ts:23-59`).
- GSM: JIT access to named secret versions; values are not intended for source/evidence (`gateway/src/integrations/secrets-provider.ts:4-29`).
- Slack: inbound signature verification is wired; template-side outbound Slack webhooks are source references only (`gateway/src/app.ts:530-577`, `automations/templates/ritual-gates-unified.json:45-72`).
- Payload: `gateway/src/lib/payload-client.ts` exists and has unit tests, but no production dependency construction/caller was found; treat it as an unconnected compatibility utility, not an active provider-plane client.

## 3. Automation inventory and side-effect classes

The checked-in source manifest contains **four** entries, all `ops_approved`, and explicitly identifies `automations/templates` as its source of truth (`automations/templates/manifest.json:1-46`). This is not live activation evidence.

| Template | Trigger and source-level actions | Side-effect classification |
|---|---|---|
| `ritual-gates-unified.json` | Daily cron at 08:00, 10:45, and 14:45; builds a confidence report, posts Slack, and publishes a gateway event (`automations/templates/ritual-gates-unified.json:1-76`). | `send_message` to Slack; `publish_event` through the gateway; no direct database write in the template. Missing report sections produce a degraded/partial result, not a claim of full confidence. |
| `urgent-event-ingestion.json` | Manual dispatch validates canonical tenant/lineage, POSTs to `$env.PAPERCLIP_EVENT_URL`, then publishes `workflow.execution` through the gateway (`automations/templates/urgent-event-ingestion.json:1-57`). | External write/event dispatch to Paperclip plus gateway event publication; no retry/idempotency declaration in the legacy template. |
| `promotion-review-governance.json` | Manual dispatch requires lineage and Auditor, Head of Quality, COO, and Principal approvals; POSTs protected lifecycle transition, then Slack (`automations/templates/promotion-review-governance.json:1-50`). | Protected state transition/write, plus external Slack message. The template calls the legacy control-token route. |
| `restore-authorization-governance.json` | Manual dispatch requires the same protected approvals; records `archived -> deprecated`, releases a scoped kill switch, then Slack (`automations/templates/restore-authorization-governance.json:1-69`). | Protected lifecycle write, kill-switch release, and external Slack message. This is governance authorization, not proof of a restore execution. |

The package catalogue index currently has `release_count: 0` (`automations/catalog/index.json:1-7`). The GAP starter is explicitly non-deployable (`automations/packages/_golden-template/automation.json:1-70`, `docs/specs/GOLDEN-AUTOMATION-PACKAGE-v0.1.md:25-51`). New provider-plane work must not infer certified releases from the four legacy template states.

## 4. Migration, RLS, and RPC baseline

The local migration chain contains 13 files, from the MVO control core and n8n isolation through automation control, runtime corrections, Librarian state, operations, product lifecycle/API, operator operations, webhooks, and durable audit outbox. The WP-04 manifest says the migration is implemented locally but not applied to stage or production (`docs/contracts/WP-04-AUTOMATION-CONTROL-MIGRATION-MANIFEST.md:1-9`, `docs/contracts/WP-04-AUTOMATION-CONTROL-MIGRATION-MANIFEST.md:46-65`).

- MVO baseline: `lautowork.audit_runs`, `lifecycle_transitions`, and `killswitch_events`, with the published audit RPC retaining the wire parameter `tenant_id` while writing `org_id` (`supabase/migrations/20260715_000001_lautowork_control_core.sql:47-147`). Its old RLS policy also accepts `request.jwt.claim.tenant_id`/nullable rows/membership (`supabase/migrations/20260715_000001_lautowork_control_core.sql:176-204`); this is a compatibility boundary, not the later canonical authority.
- Runtime/provider model: definitions, immutable releases, sources, products, org-scoped instances/bindings, secret references, provisioning, deployments, executions/events, evaluation, health, alerts/incidents, maintenance, improvement candidates, approvals, and audit events (`supabase/migrations/20260804_000001_lautowork_automation_control_model.sql:85-460`).
- Canonical RLS: the provider model enables and forces RLS for all organisation-scoped tables and reads only when `org_id` matches `request.jwt.claim.org_id` plus service/member authority; broad runtime table mutation is revoked (`supabase/migrations/20260804_000001_lautowork_automation_control_model.sql:757-801`).
- Runtime RPCs: bound-instance resolution, atomic execution acceptance, capability-bound callback recording, provisioning begin/create/mark, and explicit `PUBLIC` revocation with named runtime/service grants (`supabase/migrations/20260804_000002_lautowork_wave2_runtime_corrections.sql:18-192`).
- Append-only evidence: sources, execution events, evaluation results, health snapshots, incident/maintenance events, approval decisions, and domain audit events reject update/delete (`supabase/migrations/20260804_000001_lautowork_automation_control_model.sql:627-639`).
- Operational controls: monitoring, incidents, action records, deployment transitions, pause controls, alert delivery attempts, and `operation_retry_outbox` are introduced in the operations migration (`supabase/migrations/20260804_000004_lautowork_operations_runtime.sql:14-74`).
- Product API audit: `product_api_audit_outbox` reserves a unique organisation/correlation/action/resource row before a handler and finalizes it after the outcome; a missing reservation fails closed (`supabase/migrations/20260804_000012_lautowork_durable_audit_outbox.sql:1-27`, `supabase/migrations/20260804_000012_lautowork_durable_audit_outbox.sql:217-280`).

No migration receipt, target schema inspection, role inspection, RLS inspection, backup/restore result, or live RPC probe was performed. All database runtime claims remain `HOLD`.

## 5. Event, retry, and outbox semantics

- Current event subjects are exactly the `linkautowork.v1.*` mapping for ritual, workflow execution, security exception, kill-switch, and lifecycle events (`gateway/src/services/event-bridge.ts:8-20`). The source evidence says historical compatibility subjects are retired. NATS connection failure is degraded mode; per-event publish errors are logged and swallowed (`gateway/src/integrations/nats-client.ts:11-29`, `gateway/src/services/event-bridge.ts:50-59`). This is not durable outbox delivery.
- v2 execution acceptance is organisation/instance/idempotency-key unique. Reusing a key with a different input digest fails; a matching key returns a duplicate receipt (`supabase/migrations/20260804_000002_lautowork_wave2_runtime_corrections.sql:50-73`).
- Callback events are capability-bound, ordered by positive sequence, duplicate-safe when identical, recorded as `out_of_order` when a sequence gap occurs, and reject conflicting or terminal mutations (`supabase/migrations/20260804_000002_lautowork_wave2_runtime_corrections.sql:75-112`).
- Gateway dispatch retries use the bound retry count for explicit non-2xx responses, but timeout/transport failure is treated as ambiguous and deliberately not retried to avoid duplicate work (`gateway/src/services/instances/runtime.ts:56-75`).
- Approved operational retry creates/merges an `operation_retry_outbox` row. Claiming uses `FOR UPDATE SKIP LOCKED`, marks delivery, and increments attempts; failed delivery returns to `failed` with a five-minute delay (`supabase/migrations/20260804_000004_lautowork_operations_runtime.sql:138-140`). The scheduler delivers one leased item and records success/failure (`gateway/src/services/monitoring/operations-service.ts:72-75`).
- Product API audit is a separate reserve/finalize outbox, not an automation execution outbox. It is intended to preserve audit evidence across retries/restarts (`supabase/migrations/20260804_000012_lautowork_durable_audit_outbox.sql:1-7`).

## 6. Legacy LiNKaios classification

LiNKaios/AIOS runtime shells, sync/scaffold material, and old cross-system workflow handles are archive-only historical evidence. The current roadmap prohibits restoring those paths (`docs/production-roadmap/LINKAUTOWORK-PRODUCTION-ROADMAP.md:19-40`), and the legacy retirement evidence records the former `aios.*` event namespace as removed in favour of `linkautowork.v1.*` (`docs/production-roadmap/evidence/WP-12-LEGACY-RETIREMENT-INVENTORY.md:1-16`).

The retained archive includes `automations/templates/archive/legacy-program-shells-2026-07-18/` and other archive material. It is not a current workflow inventory, source authority, provider contract, or migration input. Do not regenerate, call, or bind it. A later retirement packet may remove stale archive-adjacent references only after its own repository-wide dependency inventory (`docs/specs/GAP-v0.1-MIGRATION-INVENTORY.md:15-21`).

## 7. Capability and health status semantics

- Gateway readiness is shallow: `/health` reports HTTP success, active tenant identifiers, and kill-switch snapshot; it does not prove n8n, Supabase, NATS, GSM, or external-service health (`gateway/src/app.ts:156-168`). Product API/operator/web services separately expose `/healthz` with `{ "status": "ok" }` (`apps/product-api/src/server.ts:20-23`, `apps/operator-console/src/server.ts:18-25`).
- Executability requires a bound enabled operation, `ready`/`active` instance, certified release, matching release/deployed workflow and configuration digests, valid input schema, no kill switch, and no pause (`gateway/src/services/instances/runtime.ts:38-55`). Provisioning similarly requires a certified release and only activates after smoke evidence (`supabase/migrations/20260804_000002_lautowork_wave2_runtime_corrections.sql:114-173`).
- Health states are `healthy`, `warning`, `critical`, and `unknown`. Disabled targets are `unknown`; a missed schedule or at least two consecutive failures is `critical`; stale callbacks or any failure is `warning`; otherwise `healthy` (`gateway/src/services/monitoring/operations-service.ts:3-5`, `:40-52`).
- Execution statuses are `accepted`, `started`, `succeeded`, `failed`, `timed_out`, and `cancelled`; callback evidence is redacted to digests/references (`gateway/src/services/monitoring/operations-service.ts:3-5`, `gateway/src/services/executions/execution-service.ts:20-29`).
- These are source semantics only. No live health or capability result is asserted.

## 8. MCP and OKF v0.2 applicability

### MCP

No supported-root MCP server, adapter, route, package, schema, or contract was found. The only filename/content matches are under archived LiNKdev/gstack material. MCP is therefore **absent from the current provider-plane baseline**. Do not add an MCP surface to a later packet unless a separately owned contract and security boundary are approved.

### OKF v0.2

No local `OKF`, `OKF v0.2`, or authoritative OKF schema/spec was found. Decision: **not applicable to this baseline artifact; adoption is HOLD/deferred**.

- Catalogue: use the frozen GAP v0.1 package layout and the operator metadata index (`docs/specs/GOLDEN-AUTOMATION-PACKAGE-v0.1.md:25-65`, `automations/catalog/index.json:1-7`). Do not invent an OKF catalogue adapter.
- Runbook: use repository Markdown under `docs/runbooks/` and GAP `operations/runbook.md` (`docs/runbooks/AUTOMATION-INTAKE.md:1-18`, `docs/specs/GOLDEN-AUTOMATION-PACKAGE-v0.1.md:37-48`).
- Evidence: use `docs/production-roadmap/evidence/` with exact source identity, commands, results, HOLDs, and rollback; this artifact is not an OKF v0.2 document.

Revisit only after an authoritative OKF v0.2 specification, owner, version binding, validation rule, and mapping decision are supplied.

## 9. Lisa and current-workflow boundary

No current n8n automation template, gateway route, Compose service, or scheduler in this repository is a Lisa workflow. `scripts/gitops/main_approve_package_discover.py` and related GitOps helpers produce Lisa-compatible approval/repair dispatch metadata for GitHub-controlled workflows; they are not LiNKautowork automation definitions. The referenced `docs/contracts/LISA-MAIN-APPROVE-DISPATCH.md` path is absent from this checkout, so that script contract is itself a documentation compatibility HOLD.

Accordingly, this repository provides no source proof of a current Lisa/OpenClaw workflow, live Lisa schedule, deployed Lisa process, or Lisa-to-provider-plane execution path. Any such claim requires a separately verified OpenClaw/Lisa repository, installed checkout, running process, and schedules; none were inspected here.

## 10. Compatibility constraints and proposed downstream ownership

These are constraints for later packets, not implementation authorization:

1. Preserve the legacy `tenant_id` RPC wire names only at explicitly documented compatibility boundaries; new provider-plane contracts and RLS use canonical `org_id` and `request.jwt.claim.org_id`.
2. Treat `automations/templates/manifest.json` as a shrinking compatibility inventory. Do not add new provider automations there. Convert one workflow at a time to exactly one authoritative GAP package after validation, executable evaluation, independent approval, importer cutover, and legacy mapping (`docs/adr/0002-golden-automation-package-source-authority.md:20-39`).
3. Reconcile the manifest/documentation count before any conversion: source has four entries, while GAP migration text and ADR prose still refer to five and name deprecated `daily-chairman-briefing` (`automations/templates/manifest.json:21-46`, `docs/specs/GAP-v0.1-MIGRATION-INVENTORY.md:7-17`, `docs/adr/0002-golden-automation-package-source-authority.md:18`).
4. Preserve exact package/workflow/Git SHA/n8n version identity; catalogue entries are read models and consumer systems invoke explicit bindings, never runtime catalogue search (`docs/specs/GOLDEN-AUTOMATION-PACKAGE-v0.1.md:9-23`, `:73-107`).
5. Do not call the Slack approval path a durable lifecycle transition until a later packet proves or repairs its persistence/audit semantics (`gateway/src/app.ts:554-577`).
6. Keep ambiguous n8n dispatch failures non-retrying unless a later contract supplies an idempotent provider execution guarantee; do not collapse execution retries, operational retry outbox, and audit outbox into one semantic.
7. Do not treat local migration files, disposable SQL, template validation, `/health`, or unit tests as live stage/production proof. Live apply remains owned and externally authorized (`docs/contracts/WP-04-AUTOMATION-CONTROL-MIGRATION-MANIFEST.md:20-31`, `:67-77`).

Proposed owned paths for later work:

| Concern | Proposed owned path | Constraint |
|---|---|---|
| GAP catalogue/release conversion | `automations/catalog/<automation-id>/<version>/`, `automations/catalog/index.json`, `packages/automation-catalog/` | WP-02/GAP authority; no parallel OKF or legacy-template source. |
| Intake/authoring | `automations/intake/`, `automations/packages/`, `packages/automation-architect/` | Candidate-only until independent evaluation/certification. |
| Runtime/provider contracts | `gateway/src/contracts/`, `gateway/src/services/instances/`, `gateway/src/services/provisioning/`, `gateway/src/integrations/` | Preserve v2 binding, digest, capability, idempotency, callback, and secret-reference boundaries. |
| Database/control plane | `supabase/migrations/`, `packages/automation-contracts/disposable-db/` | Additive/forward-fix migrations; LiNKplatform reviews and authorizes shared-target apply. |
| Monitoring/operations | `gateway/src/services/monitoring/`, `gateway/src/services/deployments/`, `ops/` | Keep health, retry outbox, deployment authority, compensation, and audit evidence distinct. |
| Runbooks/evidence | `docs/runbooks/`, `docs/production-roadmap/evidence/` | Exact source identity and truthful HOLD/PASS semantics; no live claim from local proof. |
| Legacy retirement | `docs/production-roadmap/evidence/` plus explicitly inventoried archive paths | WP-12-owned cleanup only; never restore archive material as a rollback. |

## 11. HOLD register

- **H-01 Live state:** no live target, deployment, active workflow, schedule, credential, migration receipt, or health signal was inspected.
- **H-02 Migration apply:** local migrations are not proof of stage/production schema, RLS, RPC grants, or data state.
- **H-03 Template parity:** four current manifest entries conflict with older five-workflow wording; `daily-chairman-briefing` is absent from the current top-level directory and only classified by migration inventory text.
- **H-04 Legacy ingress:** `/v1/ingress/:workflowId` remains source compatibility; later runtime packets must not silently treat it as the v2 provider contract.
- **H-05 Slack persistence:** approval event publication is source-proven; durable transition write is not source-proven on `/v1/slack/actions`.
- **H-06 Documentation:** `docs/README.md` links to the present `OPEN-ISSUES.md` and an absent `runbooks/WAVE4_AUTOMATION_PROOF.md`; the import runbook also names absent Wave 4 templates (`docs/README.md:8-20`, `docs/runbooks/IMPORT_AUTOMATION_TEMPLATES.md:40-47`).
- **H-07 OKF/MCP:** no authoritative OKF v0.2 or MCP contract exists in this repository.
- **H-08 Lisa:** no current Lisa workflow is present; the referenced Lisa dispatch contract path is absent, and live Lisa/OpenClaw state is outside this repository boundary.

## 12. Validation and rollback

Read-only checks performed:

- `git status --short --branch`, `git rev-parse HEAD`, `git rev-parse HEAD^{tree}`, and `git show -s`: clean issue worktree and exact input identity recorded above.
- `rg --files`, targeted `rg` route/client/legacy/MCP/OKF/Lisa probes, `find` inventory checks, and read-only Node JSON extraction: route, client, template, archive, and absence findings recorded above.
- `nl -ba` source/doc/migration reads: exact references recorded throughout.
- No application code, schema, migration, configuration, deployment, schedule, credential, external system, or other repository was changed.

The only permitted change from this packet is this Markdown artifact. Rollback is `git revert <commit-sha>` for the artifact commit; no migration down, workflow deletion, runtime rollback, or external action is authorized by AW-00.
