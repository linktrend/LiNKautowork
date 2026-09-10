# LiNKautowork Server01 atomic work packets

Status: **PLAN**. No packet is authorised to mutate product, provider, database or
Server01 until the founder approves the final manifest in this task.

## Common execution contract

Every packet starts from the exact accepted predecessor, uses an
`issue/<n>-<slug>` branch, discovers IDE Development 2.5.2 locally, and records a
Batch Header with scope, inputs, plan and risks. Ordinary source execution uses the
established Cursor REST dispatcher with Grok 4.6 Medium, Fast off and explicit
repository URL/ref in `repos[]`. GitHub preflight plus worker attestation proves
repository/ref/commit/tree; transport GET proves only the fields it actually
returns. Named saved Cursor environments are forbidden. The founder has already
permitted necessary Luna High fallback within the approved packet scope and for
server/privileged operations; a switch records the concrete Cursor failure and
preserves single-writer ownership.

The operational route is the Keychain-backed standard-library REST client recorded
in `CURSOR-CLOUD-EXECUTION-ROUTE.md`. Read-only API checks proved the exact account,
model parameters and LiNKautowork repository access. AW-01 is the first content
packet and its inputs are ready; it may start after founder `APPROVE`. No new
credential, Cursor CLI login, SDK installation or route choice is an AW-01
prerequisite. The coordinator must first reconcile the prior Server01 owner and add
only its exact task-ID/LiNKautowork grant while retaining global suspension; the
route document specifies that reversible transition. Luna is a governed fallback
already covered by the agreed execution model, not a second approval request.

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
      -> Lane B: AW-02 -> AW-03 -> AW-04 --+
      -> Lane C: AW-05 ---------------------+
      -> AW-06 -> AW-07 -> AW-08 live acceptance
```

Maximum safe planned concurrency is **two implementation workers** after AW-01,
in one exact window: AW-02 in Lane B with AW-05 in Lane C. Their literal packet
paths are disjoint and AW-01 freezes their shared interfaces first. AW-03 consumes
AW-02 but owns the root package manifest/lockfile, so it remains repository-exclusive
and waits for any active AW-05 writer to finish. AW-04 follows AW-03; AW-06 consumes
both lanes and owns cross-cutting operations. The independently verified shared
dispatcher extension enforces one writer per lane and rejects overlapping/shared
scope. Reassign freed capacity on completion without inventing another pairing.
No concurrent shared migration, manifest/lockfile, composition-root or Server01
mutation is allowed.

## Implementation lane table

| Lane | Outcome / packets | Exact owned paths | Prohibited or shared paths | Upstream inputs / entry | Worker and maximum | Completion / integration |
|---|---|---|---|---|---|---|
| L-A interface freeze | AW-01; exact migration, identity and live-interface package | `supabase/migrations/**`; `docs/contracts/server01/**`; `packages/automation-contracts/tests/server01-*` | All gateway, deploy, IDE and Platform files; sole migration owner | Final protected rebaseline and prior-owner handoff | Grok 4.6 Medium, Fast off; max 1 | Migration/contract tests and independent review PASS; checkpoint to Phase Packager for `development` |
| L-B runtime | AW-02 -> AW-03 -> AW-04; admission, n8n bridge and technical fixture | Union of the exact AW-02/03/04 manifest paths; lane packets expand conceptual prefixes to literal files/directories | No migrations/deploy production/Platform/IDE; `gateway/src/app.ts`, `package.json` and `package-lock.json` are AW-03-only shared owners | AW-01 accepted; then strict AW-02 -> AW-03 -> AW-04 interface chain. Only AW-02 may overlap AW-05; AW-03 is exclusive | Grok 4.6 Medium, Fast off; max 1 active within lane | Each focused suite/review/checkpoint passes; checkpoints integrate in dependency order to `development` |
| L-C deployment source | AW-05; immutable Compose/release/configuration and acceptance verifier | Exact AW-05 manifest paths under `deploy/**`, named `ops/**`, deployment test and runbook files | No gateway runtime/provider source, migrations, catalogue or IDE; uses the existing gateway image/config contract | AW-01 accepted; prepares the generic gateway build independently of AW-02. AW-07 rebuilds it from accepted AW-03 source | Grok 4.6 Medium, Fast off; max 1, concurrently with AW-02 only | Compose/source checks and review PASS; checkpoint to Phase Packager for `development` |
| L-D operations | AW-06; JetStream, monitoring, backup and recovery | Exact AW-06 manifest paths | No migration, provider/runtime bridge, automation fixture or Platform code | L-B and L-C accepted | Grok 4.6 Medium, Fast off; max 1 | Recovery/observability acceptance and review PASS; checkpoint to `development` |
| L-E integration | AW-07; assembled immutable source candidate | Evidence path only; shared-file conflict resolution belongs to integration owner, never implementers | No new product source; exact accepted AW-01..06 candidates only | All source checkpoints/reviews accepted | Local Phase Packager/Coordinator; max 1 integration owner | Consolidated affected validation, logical Phase PR and delivery-controller integration to `development` |
| L-F live | AW-08; Server01 install/canary/recovery/founder acceptance | Exact Server01/evidence paths in manifest | No concurrent Platform migration, other service mutation or protected-ref change | AW-07 protected release plus live Platform receipts | Governed Luna/server operator; max 1 privileged mutation owner | Live acceptance matrix, recovery and founder acceptance; promotion destination follows protected `staging` then `main` gates |

The integration owner is coordinator task
`01a089cb-ef0d-75a2-b87f-4f3dd8163b24` using the installed Phase
Packager/Coordinator and delivery controller. Implementers keep lane continuity
through repairs. Replacement workers start from the pushed checkpoint and remaining
scope; they do not restart discovery. Required narrow reviews remain independent
and exact-identity bound. Consolidated validation is run once on AW-07 and repeated
only for affected changes or failures.

## AW-01 — Freeze live interfaces and migration/identity package

- **Issue:** ISS-01.
- **Owner:** LiNKautowork data/contract implementer; LiNKplatform remains sole live
  migration and identity operator.
- **Scope/owned paths:** `supabase/migrations/**`,
  `docs/contracts/server01/**`, and
  `packages/automation-contracts/tests/server01-*.test.ts` for new
  migration/package surfaces. Do not edit `.ide-development/**`, Platform
  repository files, runtime Compose or existing PR #125/#126 changes.
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
  new `gateway/src/routes/provider-v2/**`, and
  `docs/contracts/provider-*-v2.md`. Do not edit the application composition root,
  which AW-03 owns. Do not implement a
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
  tests, `gateway/tests/app-runtime-dispatch.test.ts`, and the minimum composition
  wiring in `gateway/src/app.ts`. AW-03 is also the sole owner of `package.json`
  and `package-lock.json` if a justified runtime dependency is unavoidable; all
  other packets must leave them unchanged. It consumes the AW-02 route/service surface
  without rewriting it. The initial-release dispatcher is an in-process gateway
  module compiled into the existing gateway image. AW-03 must not add a separate
  service, container, image, network or configuration namespace; any future split
  requires a separate architecture decision. Do not edit policy contracts,
  workflow packages, migrations, consumer repositories or IDE managed core.
- **Authority/inputs:** AW-02 request/callback schemas; existing `N8nClient`,
  provider store/outbox boundaries, Golden Package runtime contract and n8n 2.30.0.
  Compose it through `gateway/src/app.ts` and the existing configuration contract:
  `N8N_BASE_URL`, `N8N_API_BASE_PATH`, `N8N_WEBHOOK_PATH_PREFIX`, GSM-resolved
  `N8N_API_KEY_SECRET_NAME`/`N8N_API_KEY`, and `NATS_URL`. No new configuration
  name is part of the initial-release handoff.
- **Required work:** durably deliver the exact instance/binding/package/workflow/
  configuration identity to n8n; acknowledge only after accepted execution state;
  authenticate callback/result; reconcile duplicate wakes, cancellation, timeout,
  restart and late result; enforce declared node/integration and duration/budget
  policy; emit sanitised evidence. It never chooses an automation, owns a Program
  Issue, or provides arbitrary shell execution.
- **Dependencies:** AW-02 frozen runtime contract.
- **Output:** an internal typed runtime-dispatch interface under
  `gateway/src/services/runtime-dispatch/**`, composed into the gateway, with
  health/readiness and exact n8n execution/receipt mapping. Its accepted source
  checkpoint and the frozen existing configuration contract are the complete
  handoff to final image assembly; AW-05 does not consume an AW-03 image.
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
- **Scope/owned paths:** `deploy/prod/**`, required deploy Dockerfiles for the
  existing service topology, `deploy/templates/**`, `ops/deploy-stack.sh`,
  environment rendering/validation scripts,
  `ops/verify-server01-acceptance.sh`,
  `scripts/tests/deployment-readiness.test.mjs`, and deployment sections of
  `docs/runbooks/OPERATIONS.md` and `TAILSCALE_HARDENING.md`. Reconcile, do not
  overwrite, active PR #125 changes.
- **Authority/inputs:** Server01 paths/networks in the plan; existing gateway
  Dockerfile and configuration names; existing Docker, Tailscale and shared
  monitoring; GSM names; exact images/SBOM; AW-01 role names. AW-03 is fixed as an
  in-process gateway module, not a deployable service or image.
- **Required work:** build the generic gateway image and add only the services in
  the settled initial-release topology; least-privilege networks; resource
  limits; immutable image/tag/digest manifest; health/readiness; private routes;
  external GSM/Docker secret injection; mode-`0600` runtime files; atomic release
  pointer; install/upgrade/rollback commands. Remove documentation or parser claims
  that contradict final machine-readable Compose. Do not expose protected ports or
  create another staging server. Reconcile the deployment-readiness test if the
  existing issue-126 candidate integrates it; otherwise add that exact focused test
  to assert private ingress, persistent non-host-network NATS, migration dry-run
  refusal and reproducible build inputs. Add the single Server01 acceptance script
  to check current release/image identity, Compose service health, private-only
  ports/routes, n8n/NATS persistence, receipt/kill-switch state and required backup
  artifact presence. It must be read-only except for the separately authorised
  canary actions supplied as explicit arguments; it is not a second test framework.
- **Dependencies:** AW-01 accepted. This lane is path-disjoint from the active L-B
  packet and may run concurrently only with AW-02 through the verified shared
  dispatcher extension. It can prepare the existing gateway build/config contract without
  AW-03 source; AW-07 rebuilds that image from the accepted AW-03 checkpoint.
  It must finish or reconcile terminal before repository-exclusive AW-03 starts.
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
