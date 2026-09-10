# LiNKautowork Server01 planning readiness report

Prepared: 2026-09-10, Asia/Taipei
Verdict: **PLAN READY / EXECUTION HOLD**

## Founder-readable outcome

The complete deployment plan is ready. It defines the actual initial business
workflow, exact ownership boundaries, source changes, Server01 topology, data and
secret dependencies, deployment order, live tests, recovery, and the evidence
needed before LiNKautowork can be called usable.

No product file, provider, credential, database, workflow or server was changed.
LiNKautowork is not currently installed on Server01 and is not operational.

## Readiness assessment

| Area | Result | Evidence and limit |
|---|---|---|
| Product authority | READY | Approved production roadmap and current PRD are reused. Initial Server01 scope is explicitly gateway + n8n + JetStream + persistence + private operator surfaces + one real governed repository executor. Commercial/public expansion is separated. |
| Definition of done | READY | Delivery plan covers full behavior, identity, configuration, interfaces, data, deployment, observability, failure paths, recovery and founder acceptance. |
| Work-packet completeness | READY | Eight dependency-ordered packets name exact scope/paths, requirements, inputs, changes, dependencies, outputs, validation, acceptance and recovery. Owners do not overlap by design. |
| Execution route | READY | Manifest uses Coding Execution Protocol `1.0.1` / `V25_BOOTSTRAP_LEAN`, direct Cursor SDK/API Grok 4.6 Medium route, explicit `repos[]`, exact readback, bounded retries, independent narrow review and protected delivery rules. |
| Manifest schema | READY | `EXECUTION-MANIFEST.json` is intended for the installed `.ide-development/contracts/EXECUTION-MANIFEST.schema.json` and remains `PLAN`; validation evidence is recorded with the planning commit. |
| Repository truth | READY WITH DEPENDENCY | Protected `development` is pinned. Current CI passed. Active PR #125 and repair issue #126 are recorded and must finish through their current owners; this plan does not duplicate them. |
| Host truth | READY | Read-only Server01 inspection proved host identity, capacity, Docker Compose, Tailscale, Prometheus/Grafana and current service inventory. It also proved no LiNKautowork/n8n/NATS install or runtime directory. No load test or mutation ran. |
| Platform interfaces | READY WITH SPECIFIC HOLD | Platform contracts and current protected revision are pinned. Source work can proceed against fakes; live migration/identity/deploy waits only for Autowork service registrations, PACI consumer endpoints/scopes, least-privilege DB roles and exact migration receipts. |
| Initial automation intent | READY FOR FOUNDER APPROVAL | `governed-repository-executor@1.0.0` and the supporting runtime-operations workflow are fully defined with Program owners. Existing draft canary is not misclassified as usable. |
| Factual reliability | READY | Source, installed configuration and live behavior are classified separately. No historical PASS, healthy unrelated container, source test or active branch is credited as deployment. |
| Independent review of this planning commit | HOLD | This task forbids downstream dispatch. No self-review is represented as independent. After the exact planning commit is pushed, a permitted independent narrow reviewer must bind a verdict to that commit/tree before the Issue checkpoint can be accepted. |

No synthetic planning percentage is reported. The package is complete as a plan;
runtime readiness remains `HOLD` until the named evidence exists.

## Exact material uncertainties

1. **Final source baseline:** PR #125 is a blocked draft and issue #126 is a pushed
   repair, neither protected integration. The execution manifest currently binds
   the protected planning baseline. It must be mechanically rebaselined after the
   existing owner finishes, and the final manifest digest must be the one approved.
2. **Platform live consumer readiness:** the current Platform recovery task is
   active. No Autowork-specific live registration, PACI consumer conformance,
   database role or migration receipt was observed. These are AW-01/AW-08 inputs,
   not a reason to redesign Platform here.
3. **Authenticated Cursor capacity and spend ceiling:** the repository contains the
   direct route rules, but no Server01 Autowork executor binding was exercised.
   Discover and verify the existing SDK/API route and GSM reference after approval;
   do not infer access from a secret name.
4. **Private route names:** Server01 Tailscale is live, but final n8n/operator/API
   Serve names are configuration choices. Default to private Tailscale-only routes;
   no public DNS or second staging host is required.
5. **Alert recipient:** existing Prometheus/Grafana can provide local operator
   visibility. Slack/email delivery remains disabled until a real recipient and
   consent are supplied; this does not block local alert acceptance.

## Approval gate

The founder should approve only the final pushed manifest digest. `APPROVE` in this
task authorises the documented implementation and named Server01 deployment scope;
it does not authorise later commercial/public workflows, paid provider expansion,
client data, payment activity, or a central portfolio scheduler.

Until then: **Awaiting APPROVE.**

Manifest SHA-256 for approval:
`f63ac4165c5a23201f6b5b4b344ce3c8b2b74b2231832f935249f3f9e6a3f92a`.

## Planning validation record

Run in the governed issue worktree on 2026-09-10:

| Check | Result |
|---|---|
| Installed execution-manifest JSON Schema | PASS; no errors. |
| Installed semantic plan/runtime lifecycle validator | PASS; no errors. |
| `python3 -m json.tool` | PASS. |
| `git diff --check` | PASS. |
| `npm run release:check` | PASS. |
| Relative documentation links | PASS. |
| `npm run validate:automations` | NOT RUN TO COMPLETION: clean worktree has no installed `ajv`; dependency installation is prohibited before approval. No source failure is inferred. |
| `npm run catalog:check` | NOT RUN TO COMPLETION for the same missing dependency. No catalogue change exists in this documentation packet. |

Planning branch:
`issue/127-plan-linkautowork-end-to-end-deployment-on-links`. The exact pushed
planning commit/tree is reported in the founder handoff because a file cannot
truthfully contain its own final Git identity.
