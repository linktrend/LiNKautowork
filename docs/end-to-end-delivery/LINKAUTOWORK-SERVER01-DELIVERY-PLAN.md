# LiNKautowork Server01 delivery plan and deployment PRD

Status: **complete planning package; awaiting founder approval**
Target: the existing production host `linkserver-01`
Persistent install root: `/srv/linktrend/deploy/linkautowork`
Runtime configuration root: `/srv/linktrend/runtime/linkautowork`
Docker project: `linkautowork-prod`

## 1. Outcome in plain English

LiNKautowork is done for this release when the founder can privately open its
operator surfaces, register and bind an exact validated automation package, invoke
that binding through the gateway, see n8n execute it, receive a durable result
receipt, inspect health and history, stop the automation with a kill switch, and
recover the service and its data from a tested backup.

The installed system is not just a healthy container. It must prove the whole
chain:

```text
Program-owned operation and authority
  -> Platform identity and exact Program-selected automation binding
  -> LiNKautowork gateway admission and durable request
  -> n8n governed workflow
  -> declared integration nodes and bounded result
  -> immutable LiNKautowork receipt and JetStream event
  -> Program-owned acceptance decision
```

LiNKautowork hosts and operates the automation. The calling Program continues to
own its Issue, Run, ledger, approvals, business result, merge, release, and final
acceptance. LiNKautowork never searches the catalogue on the caller's behalf and
does not become a portfolio orchestrator.

## 2. Release scope decision

### 2.1 Required initial release

The founder's assigned scope is interpreted as the following indivisible initial
release:

- the Express automation gateway, stock pinned n8n, and persistent NATS
  JetStream on Server01;
- durable `lautowork` control/execution data and isolated `lautowork_n8n` runtime
  data on the existing Platform-owned Supabase projects;
- a usable automation-platform path: exact package admission, organisation-scoped
  instance and binding, authenticated invocation, n8n execution, durable receipt,
  monitoring, pause/kill-switch and recovery;
- private n8n and operator-console access over the existing Tailscale boundary;
- Product API internally, because the operator console and durable finite action
  surface depend on it;
- monitoring, alerts, audit, backup, isolated restore, restart continuity,
  kill-switch, failure and rollback acceptance;
- exact source, image, configuration, migration, workflow, and receipt identity.

### 2.2 Required automation-platform functions and owners

These are platform functions, not invented Program business automations.

| Function | Required behavior | Runtime owner | Business authority and acceptance owner |
|---|---|---|---|
| Package/instance/binding lifecycle | Admit one exact validated Golden Automation Package, create an organisation-scoped instance, bind it only to the operation selected by its Program owner, and keep package/workflow/configuration digests immutable. | LiNKautowork | The supplying Program owns the automation's business requirements and approves the binding. |
| Bound n8n invocation | Authenticate and validate one exact binding and input contract, persist before execution, run the selected workflow in n8n, and return a bounded durable receipt with duplicate, cancel, timeout and failure behavior. | LiNKautowork | The calling Program owns its task, input, permission-to-act and outcome acceptance. |
| Runtime operations | Observe gateway, n8n, JetStream, database, workflow and backup state; open/dedupe/resolve incidents; perform only pre-authorised bounded retry/pause/rollback actions; never approve business work. | LiNKautowork | LiNKautowork Operations; founder is authority for protected recovery and production rollback. |

The existing `ide-repository-status@1.0.0` package remains a draft, inactive,
manual structural canary. Its own runbook forbids production import, so it is not
credited as an initial Program automation.

Technical deployment acceptance uses a no-external-effect fixture or disposable
workflow to prove the package/binding/invocation/receipt path without inventing
business intent. Its exact shape is a routine implementation choice constrained by
the Golden Package contract; it is not presented as a production business workflow.

### 2.3 Proposed first Program automation — not approved scope

A `governed-repository-executor` using the Cursor SDK/API and IDE Development as a
first consumer is one possible later acceptance scenario. No reviewed founder-
approved product source requires that particular workflow, provider, consumer or
name. It therefore requires an explicit founder/Program-owner scope decision before
it may be added. This plan does not authorise building it, editing IDE Development,
or treating its absence as a LiNKautowork deployment failure.

### 2.4 Explicit later expansion

The following are useful but not blockers for this assigned release:

- additional Program-specific executor automations and bindings;
- the proposed Cursor/IDE `governed-repository-executor` unless separately
  approved by its Program owner and the founder;
- the older ritual, urgent-event, promotion-review, and restore-authorisation
  templates until their current Program owners re-specify them as Golden
  Automation Packages;
- client signup, payment, public marketplace, public client portal, client-hosted
  or dedicated n8n instances;
- Slack, email, public DNS, public TLS routes, or genuine external posting;
- other automation engines, provider types, or autonomous catalogue selection;
- a continuously polling portfolio scheduler or central server orchestrator.

Existing client and commercial source remains preserved and buildable. It is not
deleted, exposed publicly, or represented as accepted by this internal release.

## 3. Definition of done

All rows are required. `PASS` must point to current live evidence; source or
configuration evidence alone receives no operational credit.

### 3.1 Behavior and founder usability

- Founder can reach n8n and the operator console through private Tailscale access,
  authenticate with the Platform-issued operator identity, and see no public n8n,
  gateway, NATS, database, or operator port.
- A Program calls the exact bound automation ID/version/digests; `latest`, unknown
  versions, unbound operations, wrong organisation, wrong audience, expired or
  revoked credentials, and changed idempotency content fail closed.
- One no-external-effect acceptance automation completes end to end through the
  real installed n8n runtime. Package, workflow, configuration, instance, binding,
  execution and receipt identities match exactly. This proves platform execution,
  not a Program business outcome.
- Identical duplicate requests return the original logical request/receipt.
  Changed content under the same idempotency key is rejected. Concurrent delivery
  cannot produce a second provider job.
- Cancellation before dispatch prevents a call; cancellation after acceptance is
  reconciled truthfully. Timeout, provider rejection, callback replay, late result,
  invalid callback and NATS interruption each have tested terminal behavior.
- The receipt states what the automation did and does not mark the Program Issue,
  gate, PR, release or deployment complete.

### 3.2 Configuration and security

- Runtime is built from an exact protected LiNKautowork commit/tree and immutable
  image digests. n8n remains pinned to `2.30.0` unless a separately reviewed
  compatibility packet changes it.
- Platform `platform.auth-claims/1.1.0` and the PACI token envelope are consumed
  exactly. Production runtime uses distinct scoped identities for gateway,
  Product API, n8n database access, runtime dispatch, deployer, backup/restore and
  observer. Broad `service_role` is not a production runtime identity.
- All secret values reside only in Google Secret Manager and are injected into
  mode-`0600` runtime material or Docker secrets outside the repository. Receipts,
  logs, commands, n8n exports and UI never contain values.
- Invocations use an allow-listed automation version, binding operation, input
  schema, external dependency/node policy, time/budget ceiling and callback.
  Arbitrary shell payloads, implicit package selection and unrestricted server
  paths are rejected.
- n8n editor, gateway, NATS and operator console stay on private Docker/Tailscale
  boundaries. Only an explicitly approved future client route may be public.

### 3.3 Data, durability and recovery

- Platform applies the exact ordered LiNKautowork migration package after backup,
  isolated restore and verification; immutable receipts bind project, pre/post
  fingerprints, migration hashes and operator identity.
- Provider requests, attempts, prepared intents, callbacks, receipts, events,
  kill switches, workflow instances and audit facts survive gateway/n8n/host
  restart. Raw prompts, secrets and private task bodies are not copied into events.
- JetStream data uses a persistent named volume, durable consumers, explicit
  subject/version policy, acknowledgement, redelivery, deduplication and bounded
  retention. An event-bus outage cannot erase the database truth.
- A backup includes database/application records, n8n workflow/config export,
  encrypted n8n state required for continuity, JetStream state or a documented
  safe rebuild boundary, release/config manifests and secret references. A real
  isolated restore proves RTO `<=60 min` and approved RPO `<=15 min` without
  overwriting the live environment.
- Rollback restores the last accepted immutable application release and compatible
  workflow/configuration; data rollback uses the predeclared restore/forward-fix
  decision and never blindly reruns non-idempotent migrations.

### 3.4 Operations and observable acceptance

- Docker health/readiness proves dependency usability, not only process liveness.
  Restart policy and boot-order behavior are tested.
- Existing Server01 Prometheus and Grafana are reused. Metrics cover request
  admission, queue/outbox age, JetStream consumer lag/redelivery, n8n executions,
  provider latency/results, callback age, failures, kill switches, database writes,
  backup age and restore status. Alert rules are installed and exercised.
- The operator console shows catalogue/version, binding, instance, request,
  attempt, receipt, incident, workflow/deployment, kill-switch, dependency and
  backup status without secret or raw-payload leakage.
- Evidence records exact live release, image digests, configuration digest,
  migration receipts, workflow/package digest, Platform contract versions,
  successful and negative test receipts, monitoring signal, backup/restore and
  rollback rehearsal.
- A founder acceptance walkthrough demonstrates submit, observe, receipt,
  duplicate replay, safe rejection, pause/kill-switch, recovery and rollback
  visibility. Approval of the walkthrough is recorded separately from technical
  PASS.

## 4. Evidence-based starting position

Observation time: 2026-09-10 13:34 Asia/Taipei (05:34 UTC).

| Surface | Source | Installed configuration | Demonstrated live functionality | Classification |
|---|---|---|---|---|
| Pre-VPS product | Accepted Wave 1-3 source and evidence exist; `docs/PRD.md` says pre-configuration engineering is complete. | No Server01 runtime values. | None for this repository. | Existing, needs current integration and live proof. |
| Gateway | Express routes, auth, kill-switch, metrics, n8n client and provider v1 surfaces exist. | No Server01 container/config. | Not running. | Source exists; configuration/deployment missing. |
| Provider/runtime invocation | Durable provider v1 contracts and persistence source exist, but activation is `HOLD`; the route explicitly rejects Issue/gate/ledger targets. | No live n8n activation binding is proven. | No real bound automation execution or consumer E2E. | Reconcile the generic n8n activation path; do not infer a Cursor product requirement. |
| Golden packages | One draft `ide-repository-status@1.0.0` canary exists. | Not imported; its runbook forbids production import. | None. | Usable executor package missing. |
| n8n | Stock `n8nio/n8n:2.30.0` Compose source and isolated schema contract exist. | No Server01 service, volume, API key or encryption-key injection. | Not running. | Deployment/config missing. |
| NATS JetStream | `nats:2.10.26-alpine`, `-js`, and persistent production volume are defined with no host port. | No Server01 service or volume. | Not running. | Deployment/config missing. |
| Supabase persistence | Eight domain migration files plus provider persistence source exist. | Platform migration authority is actively recovering Server01 and the shared projects; Autowork package application/roles are not proven. | No current Autowork live fingerprint/receipt. | Specific upstream/runtime dependency. |
| Product API/operator console | Runnable source, finite API, tests and containers exist. | No Platform issuer/client registration/session URL or Server01 route proven. | Not running. | Source exists; auth/config/deploy missing. |
| Client web | Preserved buildable source exists. | No public route, legal/pricing/payment/provider values. | Not running. | Later expansion, not initial release. |
| Host foundation | Repository provides Compose, deployment scripts, runbooks and alerts. | Server01 has Docker Compose v5.5.1, Tailscale, Prometheus and Grafana; no LiNKautowork runtime directory. | Existing unrelated containers are healthy; LiNKautowork absent. | Shared host foundation usable; component missing. |
| Capacity | Compose source lacks final live limits. | Server01: 12 CPUs, 251 GiB RAM (243 GiB available), 147 GiB free on `/srv`; Docker build cache is material. | Host was up 2d18h with no failed systemd units observed. | Sufficient for planned admission, subject to pre-deploy snapshot and resource limits. |
| Source delivery | Protected `development` is `a13a6467fc9bc2fccdddd1de8d9e258c78e57fdd`, tree `10e6b59394bfd57703d6f3cee5d7bcda3aa7342f`; CI passed. | Phase PR #125 is open/blocked and issue #126 has a pushed repair. | No protected integration of that candidate. | Record and avoid duplication. Downstream planning may use settled interfaces now; execution rebases after governed resolution only if affected. |

The development receipt gate failure on current `development` is not called a
source failure: CI and CodeQL passed, while the legacy receipt gate is non-canonical
under IDE Development 2.5.2. The open Phase PR's failing Fast gate remains a real
unresolved candidate condition until its owner closes it.

## 5. Pinned upstream and interface decisions

### 5.1 Revisions reviewed

| Repository/surface | Ref | Commit | Tree | Use in this plan |
|---|---|---|---|---|
| `linktrend/LiNKautowork` | protected `development` | `a13a6467fc9bc2fccdddd1de8d9e258c78e57fdd` | `10e6b59394bfd57703d6f3cee5d7bcda3aa7342f` | Planning and manifest baseline. |
| LiNKautowork Phase PR #125 | `phase/s01-autowork-011` | `6ac64b3bc8fee856e1c9c77f41e06d6358dbc32e` | `5f85d86b0c74f4d86c6332df618c1bc119aa8791` | Existing source-readiness candidate; not protected acceptance. |
| LiNKautowork issue #126 | repair branch | `fe953eccb903cc572d3a3d6c40c67bd184e5a614` | `537c83b321e85da5d5e0875ed0127767adb02c78` | Existing focused repair; not protected acceptance. |
| `linktrend/LiNKplatform` | protected `development` | `dde2640f35a1cfa10f9e907b2acd1791e729d40c` | `6d221b8c0807f9eb43164770ebb65fc944607fd3` | Approved Platform contracts and current recovery source. |

The Platform plan reviewed is
`docs/LINKPLATFORM-SHARED-FOUNDATION-DETAILED-IMPLEMENTATION-PLAN.md` at the
pinned Platform revision. Relevant settled interfaces are:

- Platform owns canonical actor, runtime binding, credential lifecycle,
  organisation membership, PACI issuance/JWKS/introspection, shared environment,
  migration apply/receipts and generic deployment foundation.
- LiNKautowork owns its domain migrations, gateway, automation packages,
  execution/persistence semantics, n8n, JetStream and receipts.
- Claims are exact camelCase `platform.auth-claims/1.1.0`; production machine
  tokens use the Platform PACI ES256 envelope, 15-minute TTL, no refresh token,
  exact issuer/audience and scoped operations. Platform access is not Program
  permission to act.
- Platform alone applies shared stage/production migrations after backup,
  isolated restore and receipts. LiNKautowork supplies a hashed package and
  conformance checks.
- GSM is the sole secret authority. Runtime records contain credential IDs and
  secret references, never values.
- Platform Handoff Envelopes carry references and opaque correlations, not task
  bodies. The invocation boundary accepts a Program-owned opaque work reference
  and a separately validated bounded input.

### 5.2 Specific unresolved upstream interface

Planning is not blocked by general Platform recovery. Execution packet AW-01 is
blocked only until Platform can provide and live-prove these exact consumer
surfaces for LiNKautowork:

1. production service registrations and runtime bindings for gateway, Product API
   and n8n runtime dispatch;
2. PACI issuer, JWKS, introspection/session endpoint and operation scopes accepted
   by LiNKautowork conformance tests;
3. least-privilege database login/grants for `lautowork` and `lautowork_n8n`;
4. governed application receipts for the exact LiNKautowork migration package.

No other Platform completion claim is required to start source work against
fakes. No live migration, credential or deployment can pass without these four
receipts.

## 6. Target architecture on Server01

### 6.1 Services

| Component | Placement | Exposure | Persistence/authority |
|---|---|---|---|
| gateway | Compose, non-root | private Tailscale route only | `lautowork` plus NATS events; policy authority for ingress |
| n8n 2.30.0 | Compose, non-root | private operator route only | `lautowork_n8n` plus encrypted local n8n volume |
| NATS JetStream | Compose | Docker networks only; no host port | named volume `nats_jetstream_prod` |
| Product API | Compose, non-root | private for initial release | finite PostgREST/RPC adapter; Platform auth |
| operator console | Compose, non-root | private Tailscale route | read/action client of Product API |
| runtime dispatcher | Gateway-owned bounded service/module; split into a container only if implementation evidence requires it | Docker networks only | invokes the exact bound n8n workflow; no shell gateway, Program selection or ledger authority |
| operations worker | Compose profile/service | Docker networks only | event/durable-work driven monitoring and bounded actions; no portfolio scheduling |
| Prometheus/Grafana | existing host services | existing operator boundary | add only LiNKautowork scrape/rules/dashboard assets |

The commercial `client-web` image may be built and retained with the release but
is not routed or accepted in the initial release.

### 6.2 Networks and paths

- `autowork-edge`: Tailscale reverse proxy to gateway/Product API/operator
  console as approved; n8n editor gets a separate private route.
- `autowork-runtime`: gateway, n8n and any separately justified runtime dispatcher.
- `autowork-events`: gateway, NATS and operations worker only.
- No container binds `4222`, `8222`, `5678`, or `8080` on `0.0.0.0`.
- Immutable releases live at
  `/srv/linktrend/deploy/linkautowork/releases/<commit>` with an atomic `current`
  pointer. Generated config and credentials remain under
  `/srv/linktrend/runtime/linkautowork`, not the checkout.
- Existing `/srv/linktrend/deploy/platform` and every running service remain
  separate. LiNKautowork does not modify Platform release directories.

### 6.3 Request and durability sequence

1. Consumer chooses an already bound exact automation version and supplies
   Platform token, Program-owned authority/work reference, request correlation,
   idempotency key and bounded schema-valid input.
2. Gateway validates Platform claim, consumer authority reference, binding,
   package/config digests, declared integration/node policy, expiry, kill switches
   and schema.
3. One transaction persists request, canonical fingerprint and `PREPARED` intent.
4. Transactional outbox publishes the compact request reference to JetStream.
5. A durable consumer delivers the request to the exact bound n8n workflow.
   Acknowledgement occurs only after n8n accepts the exact workflow/configuration
   identity and the durable execution state is readable.
6. The workflow executes only its declared approved nodes/integrations and returns
   the contract result or a classified failure. Any future Program-specific
   provider adapter is supplied and approved with that Program automation.
7. Callback is authenticated, fingerprinted and admitted once. Database receipt
   commits before completion events. Late or repeated callbacks return the stored
   decision and never repeat side effects.
8. JetStream publishes compact state/receipt events. Consumer reads the receipt
   and independently updates its own Program records.

## 7. Configuration and OSS inventory

| Item | Current Server01 state | Sole/shared owner | Required action after approval | Consumer connection |
|---|---|---|---|---|
| Ubuntu/Linux host | installed, healthy | Server01/Platform owner | no reinstall; preflight kernel/time/disk | all services |
| Docker Engine/Compose | installed; Compose `v5.5.1`; existing workloads healthy | Server01 shared owner | no reinstall; create isolated project/networks/limits | LiNKautowork Compose |
| Tailscale | installed and online | Server01 shared owner | add only approved private Serve routes/firewall policy | founder/operator browser and private API |
| Prometheus/Grafana | installed and active | Server01 shared observability owner | add scoped scrape/rules/dashboard; no second stack | gateway, n8n exporter/metrics, NATS, runtime bridge |
| n8n Community | absent | LiNKautowork | deploy pinned `n8nio/n8n:2.30.0`; configure API/encryption/database/URL | gateway and bound workflows |
| NATS JetStream | absent | LiNKautowork | deploy pinned `nats:2.10.26-alpine`; persistent volume/durable consumers/limits | gateway, runtime bridge and operations worker |
| gateway/Product API/operator console | absent | LiNKautowork | build immutable repo images; inject scoped config | Programs and founder |
| durable n8n activation path | source has gateway-to-n8n ingress plus provider HOLD boundaries; assembled durable path is unproven | LiNKautowork | reconcile existing pieces and close only evidence-backed gaps | every later Program-selected automation |
| PostgreSQL/Supabase | existing Platform projects under active recovery | LiNKplatform shared owner | Platform applies Autowork migrations and creates scoped roles | gateway/Product API/n8n |
| Google Secret Manager | approved shared authority; Autowork values not inventoried here | Platform/GSM owner | inventory names without values; create/rotate/inject after approval | all credentialed services |
| Slack/email/payment/public DNS | not required for initial release | respective Program/provider owners | JIT only for later approved workflows | no initial consumer |

Read-only SSH verification succeeded through alias `linkserver-01` as user
`linktrend`. That user has non-interactive `sudo`; Docker Engine `29.8.0` and
Compose `5.5.1` are available through the privileged route. Direct user access to
the Docker socket and `/srv/linktrend` write access are denied, while scoped sudo
access can write there. AW-08 must therefore use the existing sudo/SSH route and
must not change host ownership or add the user to a broader Docker group.

The current production Compose builds application images locally from the exact
release checkout and pinned Dockerfiles; no external artifact registry is part of
the accepted initial path, so registry credentials are `NOT_APPLICABLE`. AW-05
must make the handoff immutable by recording protected source commit/tree,
Dockerfile and lockfile digests, BuildKit output image IDs/content digests, and the
release-directory manifest before the atomic `current` switch. Adding GHCR or
another registry is later scope, not an undeclared prerequisite.

The established local coordinator uses a standard-library REST dispatcher and a
credential retrieved from macOS Keychain into process memory. Read-only API calls
verified account `cursor-001@linktrend.one`, Grok 4.6 Medium with Fast disabled,
and visibility of `linktrend/LiNKautowork`. It does not depend on `CURSOR_API_KEY`,
Cursor CLI login or the `cursor-sdk` package. Sanitised commands, packet fields,
transport/readback limits and GitHub-hosted worker inputs are defined in
`CURSOR-CLOUD-EXECUTION-ROUTE.md`. The key is never copied or printed. `APPROVE` is
the only remaining founder decision required to submit AW-01; Luna High remains an
explicit optional fallback.

## 8. Deployment, validation and recovery sequence

1. **Admit source baseline and route.** AW-01 is the first content packet. Refresh
   protected `development` commit/tree, reconcile only paths affected by PR
   #125/#126, and perform the exact coordinator owner-scope transition in
   `CURSOR-CLOUD-EXECUTION-ROUTE.md` after the prior Server01 owner hands off.
   Preserve global suspension and every other owner. Any design-affecting source
   change returns for founder decision; mechanical identity refresh stays within
   the approved scope but must be recorded before mutation.
2. **Implement source packets.** Grok 4.6 Medium through the established Cursor
   REST dispatcher is the ordinary route. Each issue uses explicit `repos[]`,
   transport readback plus worker Git attestation, frequent
   pushed checkpoints, focused tests and one independent narrow review bound to
   exact commit/tree. Luna High is limited to Principal-selected fallback or
   necessary server/privileged operations.
3. **Integrate in dependency order.** Phase Packager opens logical Phase PRs;
   delivery controller merges only exact reviewed candidates to `development`.
   No implementer opens/merges its own PR. `development -> staging -> main` remains
   branch promotion, not a second installation.
4. **Build immutable release.** Hosted CI performs heavy Full/security checks once
   on the assembled exact candidate. Server01 checks out only the protected release
   identity and builds with the pinned Dockerfiles/lockfile already used by Compose.
   The deployer records image IDs/content digests and release files before install;
   no unconfigured external registry is assumed.
5. **Platform data gate.** Platform takes checkpoint/backup, proves isolated
   restore, applies the exact Autowork package first to the approved validation
   context and then production under its receipts. No second persistent staging
   installation is created on another host.
6. **Ephemeral host proof.** On Server01, render Compose with names-only config,
   verify networks/ports/resources, then run an isolated ephemeral project against
   disposable data/fakes for startup, migration compatibility and failure tests.
   Remove only labelled disposable resources after evidence.
7. **Install inactive production release.** Create immutable release, runtime
   directory, Docker secrets/networks/volumes and private routes. Start core
   services with the acceptance fixture inactive and no Program binding.
8. **Configure and smoke.** Verify identity, database, n8n, JetStream, gateway,
   Product API, console, metrics, backup and kill-switch. Import the exact package
   inactive; compare live export digest.
9. **Canary activation.** Bind only the no-external-effect technical acceptance
   fixture, activate it, run negative cases, then one real bounded n8n success.
   Observe the declared window and prove no duplicate/late effects. A Program
   automation is a separate owner-defined follow-on.
10. **Recovery and acceptance.** Restart services/host-safe subset, replay
    JetStream/outbox, perform isolated restore and application rollback rehearsal,
    exercise alerts, and conduct the founder walkthrough. Record final technical
    and founder acceptance separately.

Rollback is always to the last accepted immutable release and compatible workflow
configuration. The deployer atomically switches `current`, starts the previous
Compose definition, verifies readiness, and records a rollback receipt. Database
recovery follows Platform's receipted restore or forward-fix decision; it never
deletes retained data or rolls SQL backward by assumption.

## 9. Evidence and status accounting

Evidence is stored under `docs/end-to-end-delivery/evidence/` only when it is
sanitised and suitable for Git. Sensitive or bulky live records stay in the
approved receipt store and are referenced by immutable digest/URI.

Every acceptance row records:

- repository/ref/commit/tree and image digest;
- package/workflow/configuration/schema/manifest digest;
- Platform contract and migration receipt identity;
- host, environment, route and timestamp;
- command/check and bounded output/result;
- responsible owner and independent reviewer;
- `PASS`, `HOLD`, `MISSING`, or `NOT_APPLICABLE` with evidence limit;
- rollback/recovery reference.

Source, provider selectability, consumer binding, live deployment, canary,
technical acceptance and founder acceptance remain separate. A healthy container,
successful CI run or provider `201` cannot satisfy another row.

## 10. Approval and hard stops

The founder's future `APPROVE` in this task must identify the final manifest digest
and authorise source implementation plus deployment to `linkserver-01`. The
ordinary Cursor Cloud route is verified and needs no additional founder access
decision. Downstream
owners may consume the settled planning interfaces before that approval for their
own planning; they may not treat PLAN_READY as deployment or mutation authority. Main
promotion, live provider mutation, production migration and workflow activation
are executed only where that recorded approval and packet evidence cover the exact
action.

Stop and request direction only for:

- adding a specific Program automation, including the proposed Cursor/IDE workflow;
- a new paid service or cost ceiling;
- destructive or irreversible data action;
- public exposure, client data, legal/payment terms or genuine account consent;
- missing founder-only authentication that cannot be completed through authorised
  tooling;
- an upstream contract incompatible with the four settled Platform surfaces in
  section 5.2.

Routine implementation, account/key creation under approved accounts, source
repair, deployment configuration, negative testing and recovery are packet work
after approval.
