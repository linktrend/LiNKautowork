# LiNKautowork Production Roadmap and Build Manual

**Status:** Approved production-preparation program
**Owner:** LiNKautowork
**Audience:** Implementing agents, independent auditors, Integrator, and Principal
**Execution model:** Three dependency-ordered waves, each followed by independent Sol Medium audit and a separate implementation-agent correction cycle
**Deployment boundary:** This program ends with a VPS-ready release candidate. Live Supabase, GSM, n8n, DNS, payment-provider, and VPS changes require their own controlled deployment authorization.

## 1. Purpose of this document

This document is the self-contained authority for transforming the current governance-only n8n control plane into the intended LiNKautowork product. It explains the product in plain English, defines ownership boundaries, establishes the target architecture and definition of done, and orders all pre-VPS work into executable work packets.

An implementation agent must not infer missing product behavior from the archived PRD, legacy LiNKaios assets, or the present five-workflow manifest. Those artifacts describe an older and much narrower Minimum Viable Operations implementation. The intended product is defined here.

## 2. Product intent

LiNKautowork is LiNKtrend's governed automation factory, catalogue, hosting platform, and operations system.

It has two business purposes:

1. **Internal automation operations.** LiNKtrend systems such as LiNKdeveloper, LiNKsites, LiNKbrain, LiNKskills, LiNKmedia, and future Programs have automations deliberately designed and linked to them. A system invokes the automation already assigned to an operation; it does not search a catalogue and decide autonomously which automation to use.
2. **Commercial hosted automations.** A client chooses a specific automation product on the LiNKautowork website. After signup, LiNKautowork provisions a separate workflow copy with that client's configuration, credentials, schedules, integrations, execution history, monitoring, and organisation scope inside a shared managed n8n environment.

LiNKautowork starts with n8n as its only required runtime. Existing Make, Zapier, GitHub, n8n, open-source, and other automation sources may be used as reference material, but certified automations are adapted into governed n8n packages. The package contract records an engine discriminator so another runtime can be added later without redesigning identity, catalogue, evaluation, or telemetry contracts.

## 3. Non-goals and hard boundaries

- Consumer systems do not browse or search the automation catalogue at runtime.
- Clients do not receive arbitrary access to the catalogue or the n8n editor.
- LiNKautowork does not own the business Issue, Program lifecycle, or final grading authority of a calling system.
- LiNKautowork does not replace LiNKplatform identity, organisation membership, authentication, credential issuance, or capability rules.
- LiNKautowork does not replace LiNKskills, LiNKbrain, or LiNKlibraries.
- No Automation Architect or Librarian may silently rewrite a production workflow.
- The agent that proposes a workflow change may not be the sole agent that certifies that change.
- Secrets are references to Google Secret Manager resources. Secret values never enter source control, telemetry, audit details, or UI payloads.
- Legacy LiNKaios paths are not restored. Current-system integrations must use contracts owned by the current system.

## 4. Ecosystem ownership

| System | Owns | Relationship to LiNKautowork |
|---|---|---|
| LiNKplatform | Organisations, actors, authentication, credentials, capability contracts, generic Librarian host | Supplies canonical `org_id`, actor identity, auth claims, and institutional Librarian runtime |
| LiNKautowork | Automation definitions, versions, instances, n8n execution, automation evals, telemetry, monitoring, maintenance, product provisioning | Runs linked internal and client automation instances |
| LiNKdeveloper and other Program harnesses | Issues, Runs, domain state, acceptance gates, outcome authority | Call a pre-linked automation and consume its receipt |
| LiNKskills | Skills, skill packs, skill evals, skill telemetry | May supply certified procedural skills to Automation Architect or maintenance roles |
| LiNKbrain | Governed knowledge and memory | May supply authorised knowledge; never owns automation execution or promotion |
| LiNKlibraries | Reusable development-time code, UI parts, templates, and technical assets | May supply components used to build LiNKautowork; never owns runnable automation packages |

## 5. Core terminology

| Term | Meaning |
|---|---|
| Automation definition | Versioned reusable source package describing one automation product or internal automation |
| Golden Automation Package | Required folder, manifest, contracts, workflow source, evals, monitoring, provenance, and runbook format |
| Automation instance | One configured copy of a definition linked to LiNKtrend or a client organisation |
| System binding | Explicit link between a consumer system operation and an approved automation instance |
| Product offering | Public commercial description of a specific automation clients may sign up for |
| Execution receipt | Durable record of request, version, instance, result, timing, evidence references, and failure class |
| Evaluation | Controlled test of an automation version against declared scenarios and assertions |
| Telemetry | Operational facts emitted by real runs: status, latency, retries, cost, failure class, and outcome signals |
| Automation Architect | AI role that creates, adapts, composes, or refines candidate packages |
| Librarian | One institutional curation role hosted generically by LiNKplatform and operating with separate automation-specific rules and data |
| Maintenance Issue | Durable troubleshooting or repair task created from monitoring, evaluation, or human findings |

## 6. Golden Automation Package

Every approved definition must live under `automations/catalog/<automation-id>/<version>/` and include:

```text
automation-id/version/
├── automation.json
├── workflow.json
├── contracts/
│   ├── input.schema.json
│   └── output.schema.json
├── evals/
│   ├── suite.json
│   └── fixtures/
├── operations/
│   ├── monitoring.json
│   ├── runbook.md
│   └── maintenance.json
├── provenance/
│   └── sources.json
├── examples/
├── CHANGELOG.md
└── README.md
```

The manifest must define identity, semantic version, lifecycle state, owner, purpose, internal/commercial classification, runtime engine and version, workflow digest, input/output schema references, secret reference names, permissions, external dependencies, retry/idempotency behavior, approval policy, criticality, SLO, evaluation suite, provenance/licensing, monitoring profile, deployment policy, and deprecation/replacement information.

The package validator must reject missing files, invalid IDs or versions, unpinned workflow digests, embedded credential-like values, unresolved schema references, missing eval cases, missing monitoring/runbook data, invalid lifecycle transitions, unsafe public webhook declarations, and unapproved licences.

## 7. Automation Architect lifecycle

The Automation Architect is an invoked AI role, not a permanently resident authority. It supports:

- `create`: produce a new package when no suitable source exists;
- `adapt`: reverse-engineer one existing automation into the Golden format and n8n;
- `compose`: combine selected portions of multiple sources into one coherent automation;
- `refine`: create a new candidate version from failures, telemetry, API changes, or approved requirements.

Every mode must record source provenance, licence, extracted behavior, rejected behavior, credential removal, compatibility assumptions, input/output mapping, failure modes, and evaluation coverage. It produces a candidate only. Publishing, certification, and deployment are separate gates.

## 8. Definition catalogue and instance registry

The definition catalogue answers operator questions: what definitions and versions exist, which are certified, which are deprecated, what they require, and which product offering or internal system owns them.

The instance registry answers operational questions: which organisation owns an instance, which definition version it runs, its n8n workflow ID, system binding or client subscription, configuration digest, GSM secret references, schedule, deployment state, health state, last successful run, and active incident.

Catalogue search is an operator/build-time capability. A consumer Program uses an explicit system binding and never performs catalogue selection at runtime.

## 9. Execution contract

An invocation identifies the organisation, actor/service, linked instance, calling Program, Issue/Run references, idempotency key, validated input, and trace/correlation ID. The gateway resolves the binding and certified version, checks organisation and capability scope, validates the input schema, checks kill switches, dispatches n8n, persists start/completion/failure events, emits metrics, and returns an execution receipt.

The calling Program decides whether the business Issue passed. LiNKautowork reports what the automation did and whether its own contract succeeded.

## 10. Client provisioning model

Clients choose a named product offering on the website. Signup creates an organisation-scoped provisioning request. After commercial/auth checks, the provisioner creates a workflow copy in the shared n8n environment, binds the certified version, stores configuration and secret references, configures schedules/webhooks/client-specific Slack or other nodes, performs a smoke evaluation, activates the instance, and issues a provisioning receipt.

Standard clients share the managed n8n environment while retaining separate workflow IDs, credentials, config, webhooks, execution history, and `org_id`. Dedicated n8n deployments are a later exceptional tier, not a first-release requirement.

## 11. Evaluation, telemetry, and improvement

Every production run produces telemetry, but does not rerun the full certification suite. Full eval suites run for candidate versions, scheduled regression checks, incident reproduction, dependency upgrades, and pre-promotion gates.

The institutional Librarian consumes automation-specific evidence through a separate automation queue and schema. It may recommend deprecation, create or commission an improvement candidate, or open a maintenance Issue. It must never copy Skills or Brain data into the automation catalogue. A candidate follows independent eval, Librarian review, risk-based approval, canary instance, observation window, and controlled rollout. Failure triggers rollback.

## 12. Monitoring and maintenance

Monitoring covers missed schedules, execution failure, latency/SLO breach, retry growth, queue backlog, credential/config health, external dependency errors, schema/output drift, cost anomalies, canary comparison, n8n health, gateway health, NATS health, Supabase write failures, and backup freshness.

Maintenance first performs bounded deterministic actions such as retry, connection refresh, worker restart, or rollback to the last certified configuration. Unresolved findings create a durable maintenance Issue. Troubleshooting produces evidence and a candidate repair; it does not patch production in place.

## 13. Human interfaces

The operator dashboard must expose catalogue, versions, instances, bindings, execution health, alerts, incidents, maintenance Issues, evals, Librarian candidates, approvals, canaries, deployments, rollback, kill switches, costs, dependency health, and secret-reference status without secret values.

The public website and client portal must expose approved product offerings, signup/configuration intake, authentication, organisation-scoped provisioning status, instance health and receipts, support/incident status, and subscription/entitlement state. It must not expose internal catalogue records, other organisations, n8n editor access, raw credentials, or internal maintenance traces.

## 14. Security and data rules

- `platform.organizations` and `org_id` are canonical; `tenant` is retained only at compatibility boundaries.
- Every instance, execution, provisioning request, incident, and client-visible record is organisation-scoped.
- RLS and service-side checks both enforce organisation isolation.
- Public `SECURITY DEFINER` RPCs revoke `PUBLIC` execution and grant only named runtime roles.
- Service-role credentials remain server-only.
- GSM values are resolved just in time or into protected runtime files; only secret names/references may be persisted.
- Input/output evidence must be classified and redacted before telemetry or UI exposure.
- Webhooks require explicit auth, rate limiting, replay/idempotency protection, and bounded payload sizes.
- Protected production changes require independent evidence and risk-based approval.
- Audit records are append-only; mutable projections may be rebuilt from events.

## 15. Reliability and recovery

Production readiness requires defined SLOs, Prometheus-compatible metrics, alert routing, health/readiness probes, backup and real disposable restore proof, configuration export, workflow export, version rollback, canary deployment, incident runbooks, dependency upgrade procedure, and verified restart continuity.

No local test result is production evidence. Live stage and production gates require exact deployed version, migration receipt, configuration digest, secret-reference inventory, HTTPS/private-boundary proof, external-service smoke tests, monitoring signal, backup/restore evidence, rollback evidence, and approval.

## 16. Three-wave execution plan

### Wave 1 — Product foundation and automation supply chain

Outcome: a mechanically enforced Golden Automation Package, versioned definition catalogue, Automation Architect tooling, and database contracts for definitions, versions, instances, and bindings.

Work packets: WP-01 through WP-04. WP-01 freezes contracts. WP-02, WP-03, and WP-04 may then execute in parallel against the frozen contract. The wave ends with full local CI and an independent Sol Medium audit.

### Wave 2 — Managed runtime, evidence, and autonomous operations

Outcome: safe instance provisioning and invocation, execution telemetry, real eval runner, automation-mode Librarian adapter, monitoring, maintenance Issues, bounded remediation, canary, and rollback.

Work packets: WP-05 through WP-08. WP-05 and WP-06 start in parallel; WP-07 depends on their evidence contracts; WP-08 consumes instance, telemetry, and eval contracts. The wave ends with integration tests and independent Sol Medium audit.

### Wave 3 — Operator/client product and VPS readiness

Outcome: operator dashboard, commercial website/client portal, organisation-scoped signup/provisioning experience, consolidated security/operations packaging, legacy removal, and a release candidate ready for separately authorised VPS deployment.

Work packets: WP-09 through WP-12. Backend/API and UI shells may run in parallel after Wave 2 contracts. Provisioning/product integration follows. Final hardening validates the assembled candidate. A Sol Medium subagent performs the final independent audit; implementation-agent corrections must pass re-audit.

## 17. Audit protocol

For every wave:

1. Implementation agents work only within assigned files and acceptance criteria.
2. The master integrates and runs the declared test matrix.
3. A separate Sol Medium subagent receives the frozen wave diff, work packets, commands, and evidence.
4. The auditor returns `PASS` or `HOLD` with specific findings; it makes no implementation edits.
5. `HOLD` findings become bounded correction packets assigned only to implementation subagents.
6. The full affected test matrix reruns.
7. The Sol Medium auditor or a fresh Sol Medium audit context verifies the correction.
8. The next wave starts only on `PASS`.

## 18. Final pre-VPS release gate

All work possible without live infrastructure must be complete: code, tests, migrations, fixtures, contracts, dashboards, provisioning simulation, security controls, monitoring definitions, runbooks, backup/restore tooling, deployment manifests, GSM migration plan, stage smoke scripts, rollback scripts, and evidence templates.

The final handoff must clearly list human/external inputs that cannot be fabricated: VPS choice, DNS/TLS/Traefik target, authorised Supabase migration application, new GSM project and secret mapping, platform auth issuer, Slack/client credentials, payment-provider account, monitoring destinations, and Principal production approval.
