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
Existing PR #125/#126 governed resolution
  -> AW-01
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
  ordered, additive Platform-consumable package for any missing executor request,
  prepared intent/outbox, callback/receipt and credential-binding fields; define
  least-privilege roles/grants for gateway, Product API, executor, n8n, observer and
  migration/backup; define upgrade, fresh install, verification SQL, partial apply,
  rollback/forward-fix and live fingerprint. Do not store task bodies or secrets.
- **Dependencies:** governed resolution of PR #125/#126 and final protected
  rebaseline. Source work against fakes does not require Platform live completion.
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

## AW-02 — Provider v2 admission, lifecycle and durable event boundary

- **Issue:** ISS-02.
- **Owner:** gateway/provider-contract implementer.
- **Scope/owned paths:** `packages/automation-contracts/src/provider-*`, focused
  provider contract tests, `gateway/src/services/provider-*`, provider routes in
  `gateway/src/app.ts`, and `docs/contracts/provider-*-v2.md`. Do not implement a
  Cursor client, workflow JSON, Compose, database migration or consumer ledger.
- **Authority/inputs:** AW-01 schemas/RPCs; existing provider contract
  `2026-08-13.v1`; transactional dispatch rules; Platform claims; initial workflow
  contract in the plan.
- **Required work:** version a contract that accepts an opaque Program work and
  authority reference without owning the Issue; require exact binding,
  automation/configuration digests, `repos[]`, advertised ref, allowed operation,
  budget/time/tool policy, expiry, callback and canonical fingerprint; persist
  before dispatch; support CAS lifecycle, cancel, timeout, callback, late result,
  exact replay and terminal receipts; publish compact JetStream/outbox facts only.
  Remove the current blanket rejection only for the new explicitly authorised
  bound operation; retain rejection of attempts to mutate consumer ledgers/gates.
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

## AW-03 — Direct Cursor SDK/API executor adapter

- **Issue:** ISS-03.
- **Owner:** executor-adapter implementer.
- **Scope/owned paths:** new `services/executor-adapter/**`, its focused tests and
  `deploy/common/executor-adapter.Dockerfile`. Do not edit gateway policy, workflow
  package, migrations, consumer repositories or IDE managed core.
- **Authority/inputs:** provider v2 request/callback schemas; IDE Development
  routing registry and Cursor cloud dispatch contract; existing working direct SDK
  tool/secret references discovered after approval without printing values.
- **Required work:** implement one bounded adapter for Grok 4.6 Medium with Fast
  disabled; explicit `repos[]`; pre-dispatch ref existence; provider idempotency;
  advertised and actual repository/ref/commit/tree/model readback; cancellation and
  archive attempt; allow-listed tools/network; duration/token/spend ceilings;
  sanitised logs; authenticated callback; zero named-environment or desktop
  dependency. It executes the supplied operation but never chooses work or changes
  a consumer ledger/gate/PR.
- **Dependencies:** AW-02 frozen provider v2; authenticated Cursor capacity and
  spend-ceiling evidence are configuration inputs, not source-design blockers.
- **Output:** non-root image, health/readiness, one-shot request consumer and exact
  provider receipt mapping.
- **Minimum validation:** mocked SDK contract matrix; provider sandbox canary after
  approval; wrong/missing readback, effective-model mismatch, missing ref, `201`
  interruption lookup, duplicate wake, cancellation, timeout, provider 4xx/5xx,
  redaction and arbitrary-command rejection.
- **Acceptance:** a real sandbox call proves the SDK path and exact readback; no
  secret appears in process arguments/logs; a repeated event returns the committed
  dispatch identity without a second provider job.
- **Recovery:** restart consumes only unacknowledged durable work and reconciles by
  provider idempotency lookup before any new call.

## AW-04 — Golden executor automation and n8n behavior

- **Issue:** ISS-04.
- **Owner:** LiNKautowork Automation Architect implementer; IDE Development owner
  supplies the first consumer contract and expected result.
- **Scope/owned paths:**
  `automations/catalog/governed-repository-executor/1.0.0/**`, catalog generated
  index, and package/eval fixtures. Do not change provider/gateway/adapter source,
  activate n8n or add future Program workflows.
- **Authority/inputs:** Golden Automation Package v0.1, ADR 0002 single source
  authority, provider v2, adapter contract and initial scope in the plan.
- **Required work:** complete manifest, inactive n8n workflow, input/output/config
  schemas, evals, monitoring, maintenance, deployment, provenance/licence, examples,
  changelog and runbook. Workflow handles request, validation result, provider
  acceptance, wait/callback, terminal receipt and compensation paths. No credentials
  are embedded. The package is exact-version, digest-bound and initially internal.
- **Dependencies:** AW-02 and AW-03 contract freeze.
- **Output:** independently evaluated and certified package candidate plus exact
  package/workflow/configuration digests.
- **Minimum validation:** package validator/catalog check; disposable real n8n
  import/export digest; success, rejection, duplicate, cancel-before/after,
  timeout, provider outage, callback replay/late callback, kill switch, restart and
  redaction evals.
- **Acceptance:** independent evaluator is not the author; every declared branch
  passes; live package remains inactive until AW-08 canary authority.
- **Deployment/recovery:** publisher imports the exact source package once, verifies
  export identity, binds version, and activates only in the canary step. Rollback
  deactivates and restores the last certified workflow/configuration.

## AW-05 — Server01 topology, immutable build and secure configuration

- **Issue:** ISS-05.
- **Owner:** deployment source/configuration implementer.
- **Scope/owned paths:** `deploy/prod/**`, required new deploy Dockerfiles except
  the AW-03 adapter Dockerfile, `deploy/templates/**`, `ops/deploy-stack.sh`,
  environment rendering/validation scripts, and deployment sections of
  `docs/runbooks/OPERATIONS.md` and `TAILSCALE_HARDENING.md`. Reconcile, do not
  overwrite, active PR #125 changes.
- **Authority/inputs:** Server01 paths/networks in the plan; existing Docker,
  Tailscale and shared monitoring; GSM names; exact images/SBOM; AW-01 role names.
- **Required work:** add executor service and least-privilege networks; resource
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
  provider admission, executor adapter, automation package or Platform code.
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
  with LiNKplatform migration/identity owner and IDE Development first-consumer
  owner. Founder performs only genuine approval/authentication/acceptance actions.
- **Scope/owned paths:** Server01
  `/srv/linktrend/deploy/linkautowork/**`,
  `/srv/linktrend/runtime/linkautowork/**`, scoped Docker resources, Tailscale
  routes, Prometheus/Grafana assets, Platform receipts, and sanitised
  `docs/end-to-end-delivery/evidence/live-acceptance/**`. Do not alter Platform
  release directories, unrelated containers, protected refs or other repositories.
- **Authority/inputs:** final approved manifest digest; AW-07 protected release;
  Platform identity/migration receipts; GSM references; first consumer binding and
  test Issue; current host preflight.
- **Required work:** backup/preflight; install inactive stack; apply Platform-owned
  migrations through Platform owner; create scoped identities/secrets after
  approval; configure private routes/monitoring; import exact package inactive;
  smoke dependencies; activate one canary binding; run full success/negative/
  restart/recovery matrix; conduct founder walkthrough; record acceptance.
- **Dependencies:** AW-07 and the four specific Platform receipts in the delivery
  plan. Missing future workflows, Slack, payment, public routes and client accounts
  do not block.
- **Output:** usable Server01 service, live receipts, restore and rollback evidence,
  operational dashboard/runbook and acceptance record.
- **Minimum validation:** health/readiness; private port scan; auth/role negatives;
  migration fingerprint; n8n import/export digest; JetStream persistence; real
  Cursor canary and exact readback; idempotency/concurrency/cancel/timeout/callback
  failures; kill switch; restart continuity; alerts; backup/isolated restore;
  application rollback; founder workflow.
- **Acceptance:** every definition-of-done row is current `PASS`, or an explicitly
  approved `NOT_APPLICABLE` later-expansion row. No `HOLD` or `MISSING` remains in
  the initial release.
- **Recovery:** immediately pause binding/activate kill switch on unexpected effect,
  preserve evidence, roll application to predecessor, and use Platform-approved
  restore/forward-fix for data. Report technical and founder acceptance separately.
