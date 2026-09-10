# LiNKautowork Server01 atomic work packets

Status: **PLAN**. No packet is authorised to mutate product, provider, database or
Server01 until the founder approves the final manifest in this task.

## Common execution contract

Every packet starts from the exact accepted predecessor, uses an
`issue/<n>-<slug>` branch, discovers IDE Development 2.5.2 locally, and records a
Batch Header with scope, inputs, plan and risks. Ordinary source execution uses the
direct Cursor SDK/API with Grok 4.6 Medium, Fast off, explicit repository URL/ref in
`repos[]`, and repository/ref/commit/tree/model readback. Named saved Cursor
environments are forbidden. Luna High is used only for a founder-selected fallback
or the server/privileged operations that cannot safely run through the ordinary
route.

The operational route is the Keychain-backed standard-library REST client recorded
in `CURSOR-CLOUD-EXECUTION-ROUTE.md`. Read-only API checks proved the exact account,
model parameters and LiNKautowork repository access. AW-01 is the first content
packet and its inputs are ready; it may start after founder `APPROVE`. No new
credential, Cursor CLI login, SDK installation or route choice is an AW-01
prerequisite. Luna is an explicit founder-selected fallback only.

An Issue checkpoint requires exact pushed commit/tree, scoped diff, focused tests,
manifest evidence, and one provider-independent narrow review bound to that exact
identity. The implementer does not self-review, open or merge a PR. Phase Packager
opens the logical Phase PR; delivery controller integrates to `development`.

Each handoff contains changed paths, exact inputs/contracts, commands/results,
remaining HOLDs, rollback, and evidence references. Heavy Full/build/browser/image
work runs once in hosted CI on the assembled candidate; local/server checks are
only those necessary for configuration and live acceptance.

## Dependency order

```text
Settled protected interfaces available to downstream planning
  -> AW-01 after execution rebaseline
      -> AW-02 -> AW-03 -> AW-04
      -> AW-05 -----------------+
  -> AW-06 (after AW-02..AW-05) |
  -> AW-07                       |
  -> AW-08 live acceptance <-----+
```

AW-02 and AW-05 may proceed concurrently after AW-01 because their owned paths do
not overlap. All other dependencies are strict.

## AW-01 — Freeze live interfaces and migration/identity package

- **Issue:** ISS-01.
- **Owner:** LiNKautowork data/contract implementer; LiNKplatform remains sole live
  migration and identity operator.
- **Scope/owned paths:** `supabase/migrations/**`,
  `docs/contracts/server01/**`, and contract tests for new migration/package
  surfaces. Do not edit `.ide-development/**`, Platform repository files, runtime
  Compose or existing PR #125/#126 changes.
- **Authority/inputs:** this plan; protected Autowork baseline; Platform protected
  revision pinned in the plan; `platform.auth-claims/1.1.0`, PACI envelope,
  migration manifest/receipt, health and recovery contracts; existing
  `20260804_*` Autowork migrations and provider persistence v1.
- **Required work:** inventory exact current migrations; create one hashed,
  ordered, additive Platform-consumable package for any missing invocation request,
  prepared intent/outbox, callback/receipt and credential-binding fields; define
  least-privilege roles/grants for gateway, Product API, runtime dispatch, n8n, observer and
  migration/backup; define upgrade, fresh install, verification SQL, partial apply,
  rollback/forward-fix and live fingerprint. Do not store task bodies or secrets.
- **Dependencies:** final protected execution rebaseline. PR #125/#126 are relevant
  only to paths/interfaces they actually change; they do not block downstream
  planning against the settled interfaces. Source work against fakes does not
  require Platform live completion.
- **Output:** exact contract/version matrix, migration package manifest/digests,
  fixtures and conformance commands accepted by the Platform owner.
- **Minimum validation:** clean disposable Postgres/PostgREST fresh install and
  upgrade; role/RLS matrix; idempotency/concurrency/append-only tests; migration
  manifest hash validation; `git diff --check`.
- **Acceptance:** independent review confirms ownership, least privilege,
  organisation isolation, secret-free receipts, retry safety and executable
  recovery. Live acceptance remains HOLD until Platform application receipts.
- **Deployment/recovery:** Platform alone backs up, isolated-restores, applies and
  receipts the package. Stop on drift or partial application; use the declared
  forward-fix/restore decision.

## AW-02 — Automation admission, lifecycle and durable event boundary

- **Issue:** ISS-02.
- **Owner:** gateway/runtime-contract implementer.
- **Scope/owned paths:** `packages/automation-contracts/src/provider-*`, focused
  provider contract tests, `gateway/src/services/provider-*`, provider routes in
  `gateway/src/app.ts`, and `docs/contracts/provider-*-v2.md`. Do not implement a
  Program-specific provider client, workflow JSON, Compose, database migration or
  consumer ledger.
- **Authority/inputs:** AW-01 schemas/RPCs; existing provider contract
  `2026-08-13.v1`; transactional dispatch rules; Platform claims; initial workflow
  contract in the plan.
- **Required work:** version or reconcile a contract that accepts an opaque Program
  work and authority reference without owning the Issue; require exact binding,
  automation/configuration digests, allowed operation, bounded input/evidence
  references, budget/time/node policy, expiry, callback and canonical fingerprint;
  persist before dispatch; support CAS lifecycle, cancel, timeout, callback, late
  result, exact replay and terminal receipts; publish compact JetStream/outbox facts
  only. Retain rejection of attempts to mutate consumer ledgers/gates. Do not add a
  particular Program workflow or provider contract without its owner.
- **Dependencies:** AW-01 contract freeze.
- **Output:** provider v2 schemas, service/store adapter, HTTP routes, compatibility
  policy and v1 coexistence/deprecation note.
- **Minimum validation:** valid request; wrong org/audience/binding/digest/ref;
  unapproved repo/tool; expired/revoked claim; same/different idempotency replay;
  concurrent acceptance; cancel races; callback auth/replay; late result; NATS and
  database failure; v1 regression; `npm run typecheck` and focused Vitest.
- **Acceptance:** no route can dispatch without durable `PREPARED` state and exact
  authority; no callback or wake can double-dispatch or alter a terminal receipt;
  receipts explicitly disclaim consumer completion.
- **Recovery:** replay the durable outbox/JetStream reference. Database remains
  truth; event failure never fabricates provider state.

## AW-03 — Durable n8n activation and callback bridge

- **Issue:** ISS-03.
- **Owner:** n8n runtime-integration implementer.
- **Scope/owned paths:** new `gateway/src/services/runtime-dispatch/**` and focused
  tests. A separate service/container is added only if implementation evidence
  shows the gateway-owned module cannot meet isolation or liveness requirements.
  Do not edit policy contracts, workflow packages, migrations, consumer
  repositories or IDE managed core.
- **Authority/inputs:** AW-02 request/callback schemas; existing `N8nClient`,
  provider store/outbox boundaries, Golden Package runtime contract and n8n 2.30.0.
- **Required work:** durably deliver the exact instance/binding/package/workflow/
  configuration identity to n8n; acknowledge only after accepted execution state;
  authenticate callback/result; reconcile duplicate wakes, cancellation, timeout,
  restart and late result; enforce declared node/integration and duration/budget
  policy; emit sanitised evidence. It never chooses an automation, owns a Program
  Issue, or provides arbitrary shell execution.
- **Dependencies:** AW-02 frozen runtime contract.
- **Output:** bounded runtime bridge with health/readiness and exact n8n execution/
  receipt mapping.
- **Minimum validation:** disposable n8n contract matrix; wrong/missing workflow or
  configuration identity, duplicate wake, cancellation races, timeout, n8n 4xx/5xx,
  restart, callback replay/late callback, redaction and arbitrary-node rejection.
- **Acceptance:** a real disposable n8n call proves the installed runtime path; no
  secret appears in logs; a repeated delivery returns the committed execution
  identity without a second workflow execution.
- **Recovery:** restart consumes only unacknowledged durable work and reconciles the
  existing execution/receipt before any new delivery.

## AW-04 — Server01 runtime acceptance fixture and n8n behavior

- **Issue:** ISS-04.
- **Owner:** LiNKautowork runtime/evaluation implementer.
- **Scope/owned paths:**
  `automations/evals/server01-runtime-acceptance/**` and
  `deploy/test/fixtures/server01-runtime-acceptance/**`. Do not change the
  production catalogue, provider/gateway bridge source, activate live n8n or add a
  Program workflow.
- **Authority/inputs:** Golden Automation Package v0.1, ADR 0002 single source
  authority, provider v2, runtime-bridge contract and initial scope in the plan.
- **Required work:** create or select a no-external-effect disposable workflow and
  fixtures that prove exact package/instance/binding/invocation/result/receipt
  behavior. It must use approved core nodes, embed no credentials, make no external
  call, and cover terminal and compensation paths. It is technical acceptance
  evidence, not a production business automation or catalogue offering.
- **Dependencies:** AW-02 and AW-03 contract freeze.
- **Output:** exact technical acceptance fixture and workflow/configuration digests.
- **Minimum validation:** package validator/catalog check; disposable real n8n
  import/export digest; success, rejection, duplicate, cancel-before/after,
  timeout, provider outage, callback replay/late callback, kill switch, restart and
  redaction evals.
- **Acceptance:** every declared branch passes; the fixture remains inactive until
  AW-08 technical canary authority and is removed or disabled after acceptance.
- **Deployment/recovery:** publisher imports the exact source package once, verifies
  export identity, binds version, and activates only in the canary step. Rollback
  deactivates and restores the last certified workflow/configuration.

## AW-05 — Server01 topology, immutable build and secure configuration

- **Issue:** ISS-05.
- **Owner:** deployment source/configuration implementer.
- **Scope/owned paths:** `deploy/prod/**`, required new deploy Dockerfiles except
  any separately justified AW-03 runtime-bridge image, `deploy/templates/**`, `ops/deploy-stack.sh`,
  environment rendering/validation scripts, and deployment sections of
  `docs/runbooks/OPERATIONS.md` and `TAILSCALE_HARDENING.md`. Reconcile, do not
  overwrite, active PR #125 changes.
- **Authority/inputs:** Server01 paths/networks in the plan; existing Docker,
  Tailscale and shared monitoring; GSM names; exact images/SBOM; AW-01 role names.
- **Required work:** add only the runtime services justified by AW-03 and
  least-privilege networks; resource
  limits; immutable image/tag/digest manifest; health/readiness; private routes;
  external GSM/Docker secret injection; mode-`0600` runtime files; atomic release
  pointer; install/upgrade/rollback commands. Remove documentation or parser claims
  that contradict final machine-readable Compose. Do not expose protected ports or
  create another staging server.
- **Dependencies:** AW-01 interfaces; may proceed concurrently with AW-02.
- **Output:** deterministic production Compose/release manifest and Server01
  installation/rollback runbook.
- **Minimum validation:** Compose render with names-only config; SBOM/licence/
  vulnerability and secret scan; network/port/resource assertions; deterministic
  images; ephemeral Server01 dry deployment against fakes after approval; existing
  service non-interference.
- **Acceptance:** exact release can be installed inactive without touching existing
  Platform/OpenClaw/Brain/Skills/Buzz/Odoo services; only approved private routes
  exist; rollback command restores the predecessor.
- **Recovery:** atomic `current` switch and previous Compose definition; retain at
  least the current and last accepted release until final acceptance.

## AW-06 — Runtime operations, JetStream, observability and recovery

- **Issue:** ISS-06.
- **Owner:** operations/recovery implementer.
- **Scope/owned paths:** `packages/automation-operations/**`,
  `gateway/src/services/monitoring/**`, `ops/alerts/**`, backup/restore/export
  scripts, and new Server01 operations/recovery runbook sections. Do not edit
  provider admission, runtime bridge, automation package or Platform code.
- **Authority/inputs:** AW-01 persistence; AW-02 states/events; AW-05 topology;
  existing Server01 Prometheus/Grafana; RTO/RPO in the plan.
- **Required work:** durable JetStream subjects/streams/consumers, ack/redelivery/
  dedupe/retention/lag; dependency readiness; incident dedupe; authenticated
  event-driven retry/pause/rollback; Prometheus rules and Grafana dashboard;
  backup manifest and encrypted application/n8n/workflow/event-state capture;
  isolated restore and restart/rollback procedures. Do not add a portfolio poller.
- **Dependencies:** AW-02 through AW-05.
- **Output:** operations profile, alerts/dashboard, backup/restore tools and
  recovery evidence templates.
- **Minimum validation:** JetStream restart/redelivery/dedupe/lag; database and
  NATS outage; alert fire/recover; corrupted/tampered backup; isolated restore;
  RTO/RPO measurement; rollback; secret/log redaction.
- **Acceptance:** existing Prometheus/Grafana monitor all required signals; backup
  and isolated restore reproduce exact fingerprints within targets; operations
  actions require durable authority and are fully auditable.
- **Recovery:** preserve live data, stop automation first, use verified backup or
  last release, and issue a recovery receipt. Never delete or recreate shared
  Platform state by assumption.

## AW-07 — Governed integration and immutable release candidate

- **Issue:** ISS-07.
- **Owner:** integration/packager and independent reviewer roles under installed
  protocol; no implementer self-integration.
- **Scope/owned paths:** integration evidence and
  `docs/end-to-end-delivery/evidence/source-release/**`. Product paths are read-only
  during this packet; defects return to their owning issue packet.
- **Authority/inputs:** exact accepted AW-01 through AW-06 checkpoints and reviews;
  installed Phase Packager/delivery controller; CI contract.
- **Required work:** assemble in dependency order; reject overlapping/stale work;
  run one affected Full/CI/build/browser/image/security/SBOM suite on exact head;
  record candidate commit/tree/images/config/package digests; integrate to
  `development`, promote through `staging` and `main` only under their exact gates.
  Branch `staging` is not a staging host.
- **Dependencies:** AW-01 through AW-06 accepted.
- **Output:** immutable protected release candidate and source receipt bundle.
- **Minimum validation:** named CI gates, scoped diff, link/path validation,
  manifest schema/lifecycle validation, independent exact-head review and remote
  protected-ref/tree readback.
- **Acceptance:** protected candidate identity and all artifact digests match; no
  open defect/HOLD affects the initial release. Provider/live claims remain HOLD.
- **Recovery:** any source change invalidates prior reviews/receipts and returns to
  the owning packet on a new identity.

## AW-08 — Install, configure, canary and founder acceptance on Server01

- **Issue:** ISS-08.
- **Owner:** Luna High server/deployment operator where privileged work is needed,
  with LiNKplatform migration/identity owner. A Program owner joins only after a
  separate Program automation is defined. Founder performs only genuine
  approval/authentication/acceptance actions.
- **Scope/owned paths:** Server01
  `/srv/linktrend/deploy/linkautowork/**`,
  `/srv/linktrend/runtime/linkautowork/**`, scoped Docker resources, Tailscale
  routes, Prometheus/Grafana assets, Platform receipts, and sanitised
  `docs/end-to-end-delivery/evidence/live-acceptance/**`. Do not alter Platform
  release directories, unrelated containers, protected refs or other repositories.
- **Authority/inputs:** final approved manifest digest; AW-07 protected release;
  Platform identity/migration receipts; GSM references; technical acceptance
  fixture; current host preflight.
- **Required work:** backup/preflight; install inactive stack; apply Platform-owned
  migrations through Platform owner; create scoped identities/secrets after
  approval; configure private routes/monitoring; import exact package inactive;
  smoke dependencies; activate one technical canary binding; run the full
  success/negative/
  restart/recovery matrix; conduct founder walkthrough; record acceptance.
- **Dependencies:** AW-07 and the four specific Platform receipts in the delivery
  plan. Missing Program workflows, Slack, payment, public routes and client accounts
  do not block platform acceptance.
- **Output:** usable Server01 service, live receipts, restore and rollback evidence,
  operational dashboard/runbook and acceptance record.
- **Minimum validation:** health/readiness; private port scan; auth/role negatives;
  migration fingerprint; n8n import/export digest; JetStream persistence; real
  technical n8n canary; idempotency/concurrency/cancel/timeout/callback failures;
  kill switch; restart continuity; alerts; backup/isolated restore; application
  rollback; founder platform walkthrough.
- **Acceptance:** every definition-of-done row is current `PASS`, or an explicitly
  approved `NOT_APPLICABLE` later-expansion row. No `HOLD` or `MISSING` remains in
  the initial release.
- **Recovery:** immediately pause binding/activate kill switch on unexpected effect,
  preserve evidence, roll application to predecessor, and use Platform-approved
  restore/forward-fix for data. Report technical and founder acceptance separately.
