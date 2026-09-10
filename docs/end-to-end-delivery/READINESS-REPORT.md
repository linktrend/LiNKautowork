# LiNKautowork Server01 planning readiness report

Prepared: 2026-09-10, Asia/Taipei
Verdict: **CANDIDATE PLAN READY / ADVISOR ACCEPTANCE PENDING**

## Founder-readable outcome

The complete deployment plan is ready. It defines the required automation-platform
behavior, exact ownership boundaries, source changes, Server01 topology, data and
secret dependencies, deployment order, live tests, recovery, and the evidence
needed before LiNKautowork can be called usable. It does not invent a mandatory
Program business workflow.

No product file, provider, credential, database, workflow or server was changed.
LiNKautowork is not currently installed on Server01 and is not operational.

## Readiness assessment

| Area | Result | Evidence and limit |
|---|---|---|
| Product authority | READY | Approved production roadmap and current PRD are reused. Initial Server01 scope is gateway + n8n + JetStream + persistence + private operator surfaces + exact package/binding/invocation/receipt behavior. Program-specific and commercial/public automations are separated. |
| Definition of done | READY | Delivery plan covers full behavior, identity, configuration, interfaces, data, deployment, observability, failure paths, recovery and founder acceptance. |
| Work-packet completeness | READY | Eight dependency-ordered packets name exact scope/paths, requirements, inputs, changes, dependencies, outputs, validation, acceptance and recovery. Owners do not overlap by design. |
| Execution-route definition | READY | The established standard-library REST dispatcher is documented in `CURSOR-CLOUD-EXECUTION-ROUTE.md`: Keychain-backed API v1, Grok 4.6 Medium, Fast off, explicit branch-bound `repos[]`, transport readback, worker source attestation, stable packet identity, polling and bounded capacity. |
| Executable after approval | READY | Read-only API GETs proved exact account `cursor-001@linktrend.one`, supported Grok 4.6 Medium/Fast-off parameters, and visibility of `linktrend/LiNKautowork`. AW-01 can be submitted after the final manifest receives `APPROVE`; no new key, login, SDK installation or founder route decision is required. No paid worker was launched during planning. |
| GitHub source access and handoff | READY | The authenticated `linktrend` account has ADMIN repository access; `origin/development` readback is `a13a6467fc9bc2fccdddd1de8d9e258c78e57fdd` / tree `10e6b59394bfd57703d6f3cee5d7bcda3aa7342f`. Issue checkpoints use `completion_gate.py`; Phase Packager opens the PR and the delivery controller integrates it. |
| Manifest schema | READY | `EXECUTION-MANIFEST.json` is intended for the installed `.ide-development/contracts/EXECUTION-MANIFEST.schema.json` and remains `PLAN`; validation evidence is recorded with the planning commit. |
| Repository truth | READY WITH DEPENDENCY | Protected `development` is pinned. Current CI passed. Active PR #125 and repair issue #126 are recorded and must finish through their current owners; this plan does not duplicate them. |
| Host truth | READY | Read-only Server01 inspection proved host identity, capacity, Docker Compose, Tailscale, Prometheus/Grafana and current service inventory. It also proved no LiNKautowork/n8n/NATS install or runtime directory. No load test or mutation ran. |
| Platform interfaces | READY WITH SPECIFIC HOLD | Platform contracts and current protected revision are pinned. Source work can proceed against fakes; live migration/identity/deploy waits only for Autowork service registrations, PACI consumer endpoints/scopes, least-privilege DB roles and exact migration receipts. |
| Automation scope | READY | Required package/instance/binding/invocation/receipt and runtime-operations functions are separate from Program-owned automations. The Cursor/IDE executor is labelled only as a later proposal requiring a founder/Program-owner decision. Existing draft canary is not misclassified as a production automation. |
| Factual reliability | READY | Source, installed configuration and live behavior are classified separately. No historical PASS, healthy unrelated container, source test or active branch is credited as deployment. |
| Installed checkpoint rule | RECORDED / NOT A PLANNING GATE | An accepted implementation Issue checkpoint later requires an exact-commit independent narrow review. This task forbids downstream dispatch, and planning readiness does not depend on manufacturing that review. No self-review is represented as independent. |

No synthetic planning percentage is reported. The package is complete as a plan,
and the first source packet is executable through the verified route after the
founder supplies the required `APPROVE` execution authority.

## Readiness split and first packet

| Layer | State | Exact meaning |
|---|---|---|
| Planning/interface maturity | READY | Approved product behavior, interfaces, owners, paths, packet dependencies, tests, deployment, recovery and acceptance are specified. Advisor acceptance may release downstream planning only. |
| Executable now after `APPROVE` | READY | AW-01 is the first content packet; its repository/Platform inputs and authenticated ordinary Cursor Cloud transport are verified. The local orchestrator prepares the pushed issue branch and exact packet, then submits it. |
| Later live prerequisites | HOLD BY DESIGN | Server01 service install, Platform registrations/PACI scopes, least-privilege database roles, exact migration receipts, GSM runtime secrets and private routes are AW-01/AW-05/AW-08 execution dependencies. They do not block source planning, but live deployment cannot pass without them. |

After Deployment Advisor acceptance of the exact package, the only founder decision
needed to start AW-01 is `APPROVE` for the final manifest digest and named Server01
scope. Advisor acceptance releases downstream planning only. Luna remains an
optional, explicit fallback, not a prerequisite or automatic substitution.

## Verified execution-route evidence

| Evidence | Read-only result |
|---|---|
| Dispatcher source/version | Operational standard-library REST client at the local coordinator path recorded in `CURSOR-CLOUD-EXECUTION-ROUTE.md`, SHA-256 `0cf61dc9b2f6b7f6c6b34ddf94a7c751229e9838d50ed9c1b468f5327e39e2e8`. Installed IDE Development 2.5.2 remains repository governance, not the transport dependency. |
| Model and binding | `ordinary-development` is provider `cursor`, model `grok-4.6`, effort `medium`, Fast `false`; request uses explicit repository URL and starting ref through `repos[]` or `CloudAgentOptions.repos`. |
| Result/status and failure behavior | Submit persists a stable packet/agent identity before POST. Agent GET validates cloud host, agent ID, repository URL when returned, optional starting ref when returned, and no-auto-PR policy. Poll then reads the exact latest run. Worker Git attestation—not transport GET—proves starting/final repository/ref/commit/tree. |
| Source repository access | `gh` account `linktrend` is authenticated with ADMIN access to `linktrend/LiNKautowork`; remote protected `development` commit/tree readback succeeded. |
| Cloud worker authority | Direct read-only GETs proved Keychain account `cursor-001@linktrend.one`, exact model parameters and LiNKautowork repository visibility. Credential value remained in process memory and was not printed. Environment variables, Cursor CLI login and `cursor-sdk` are not dependencies of this operational REST client. |
| Checkpoint and PR handoff | `scripts/gitops/completion_gate.py` records exact pushed Issue checkpoint evidence; the Phase Packager/Coordinator opens the draft Phase PR; `scripts/gitops/delivery_controller.py` performs protected integration after required evidence. |
| Fallback | Registry route `luna-fallback`: Codex CLI `gpt-5.6-luna`, effort `high`, Fast `false`, only when the founder explicitly instructs it. |

## Exact material uncertainties

1. **Final implementation baseline:** PR #125 is a blocked draft and issue #126 is a
   pushed repair, neither protected integration. The execution manifest currently
   binds the protected planning baseline. Downstream planning may consume settled
   interfaces now. Before implementation touches an affected path, reconcile the
   then-current protected baseline; request a new scope decision only if the
   interface or approved design changes.
2. **Platform live consumer readiness:** the current Platform recovery task is
   active. No Autowork-specific live registration, PACI consumer conformance,
   database role or migration receipt was observed. These are AW-01/AW-08 inputs,
   not a reason to redesign Platform here.
3. **Implementation-route capacity:** account, exact model parameters and repository
   visibility are verified read-only. Live submit/poll behavior remains unexercised
   in this planning task because it would create a paid worker; the established
   transport and prior operational receipts are reused without claiming a new run.
4. **Private route names:** Server01 Tailscale is live, but final n8n/operator/API
   Serve names are configuration choices. Default to private Tailscale-only routes;
   no public DNS or second staging host is required.
5. **Alert recipient:** existing Prometheus/Grafana can provide local operator
   visibility. Slack/email delivery remains disabled until a real recipient and
   consent are supplied; this does not block local alert acceptance.

## Approval gate

The founder should approve only the final pushed manifest digest. `APPROVE` in this
task authorises the documented implementation and named Server01 deployment scope;
it does not authorise the proposed Cursor/IDE workflow, later commercial/public
workflows, paid provider expansion, client data, payment activity, or a central
portfolio scheduler. Downstream owners may use this PLAN_READY package for planning
without that execution approval. No separate route-provisioning decision is needed.

Until then: **Awaiting APPROVE.**

Manifest SHA-256 for approval:
`40eb451c010c2916ceaa53537cf7ee0c34e36ad30035df0ad2c2e66a43b5eb51`.

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
| `npm run validate:automations` | NOT RUN TO COMPLETION: clean worktree has no installed `ajv`; dependency installation is prohibited before approval. The catalogue is unchanged, so this is not a new product failure. |
| `npm run catalog:check` | NOT RUN TO COMPLETION for the same missing dependency. The unchanged catalogue receives no new failure classification. |

Planning branch:
`issue/127-plan-linkautowork-end-to-end-deployment-on-links`. The exact pushed
planning commit/tree is reported in the founder handoff because a file cannot
truthfully contain its own final Git identity.
