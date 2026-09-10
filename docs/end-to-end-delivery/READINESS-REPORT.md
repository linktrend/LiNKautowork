# LiNKautowork Server01 planning readiness report

Prepared: 2026-09-10, Asia/Taipei
Verdict: **PLAN READY / EXECUTABLE-NOW HOLD**

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
| Execution-route definition | READY | Installed IDE Development 2.5.2 defines `cursor-cloud-dispatch-v2`: `core/execution/cursor_cloud_dispatch.py`, config `core/managed-core/content/config/cursor-cloud-dispatch.json`, API `https://api.cursor.com/v1/agents`, preferred `cursor-sdk`, Grok 4.6 Medium, Fast off, explicit `repos[]`/`CloudAgentOptions.repos`, status readback, archive-on-mismatch and at most two API attempts. |
| Executable-now worker route | HOLD | Safe read-only checks found no `CURSOR_API_KEY`, no matching GSM secret reference, no installed `cursor-sdk`, and `cursor-agent status` returned `Not logged in`. CLI login is explicitly not Cloud API authority. No paid worker was launched. Founder must authorise Cursor Cloud provisioning/verification or explicitly select Luna High fallback before AW-01 can start. |
| GitHub source access and handoff | READY | The authenticated `linktrend` account has ADMIN repository access; `origin/development` readback is `a13a6467fc9bc2fccdddd1de8d9e258c78e57fdd` / tree `10e6b59394bfd57703d6f3cee5d7bcda3aa7342f`. Issue checkpoints use `completion_gate.py`; Phase Packager opens the PR and the delivery controller integrates it. |
| Manifest schema | READY | `EXECUTION-MANIFEST.json` is intended for the installed `.ide-development/contracts/EXECUTION-MANIFEST.schema.json` and remains `PLAN`; validation evidence is recorded with the planning commit. |
| Repository truth | READY WITH DEPENDENCY | Protected `development` is pinned. Current CI passed. Active PR #125 and repair issue #126 are recorded and must finish through their current owners; this plan does not duplicate them. |
| Host truth | READY | Read-only Server01 inspection proved host identity, capacity, Docker Compose, Tailscale, Prometheus/Grafana and current service inventory. It also proved no LiNKautowork/n8n/NATS install or runtime directory. No load test or mutation ran. |
| Platform interfaces | READY WITH SPECIFIC HOLD | Platform contracts and current protected revision are pinned. Source work can proceed against fakes; live migration/identity/deploy waits only for Autowork service registrations, PACI consumer endpoints/scopes, least-privilege DB roles and exact migration receipts. |
| Automation scope | READY | Required package/instance/binding/invocation/receipt and runtime-operations functions are separate from Program-owned automations. The Cursor/IDE executor is labelled only as a later proposal requiring a founder/Program-owner decision. Existing draft canary is not misclassified as a production automation. |
| Factual reliability | READY | Source, installed configuration and live behavior are classified separately. No historical PASS, healthy unrelated container, source test or active branch is credited as deployment. |
| Installed checkpoint rule | RECORDED / NOT A PLANNING GATE | An accepted implementation Issue checkpoint later requires an exact-commit independent narrow review. This task forbids downstream dispatch, and planning readiness does not depend on manufacturing that review. No self-review is represented as independent. |

No synthetic planning percentage is reported. The package is complete as a plan.
It is not implementation-ready today because the ordinary worker route lacks
verified Cloud API authority and client capacity.

## Readiness split and first packet

| Layer | State | Exact meaning |
|---|---|---|
| Planning/interface maturity | READY | Approved product behavior, interfaces, owners, paths, packet dependencies, tests, deployment, recovery and acceptance are specified. Advisor acceptance may release downstream planning only. |
| Executable now after `APPROVE` | HOLD | AW-01 is the first content packet and has ready repository/Platform inputs, but the required ordinary Cursor Cloud worker cannot be authenticated or invoked from this environment. |
| Later live prerequisites | HOLD BY DESIGN | Server01 service install, Platform registrations/PACI scopes, least-privilege database roles, exact migration receipts, GSM runtime secrets and private routes are AW-01/AW-05/AW-08 execution dependencies. They do not block source planning, but live deployment cannot pass without them. |

The founder-only decision needed before execution is one of: (a) `APPROVE` plus
authorisation to provision and verify the existing Cursor Cloud route without
printing the secret, or (b) `APPROVE` plus an explicit instruction to use the
registered `luna-fallback` route (Codex CLI GPT-5.6 Luna High, Fast off). Luna is
not an automatic fallback and the plan does not silently substitute it.

## Verified execution-route evidence

| Evidence | Read-only result |
|---|---|
| Dispatcher source/version | Installed managed core `2.5.2`; control `cursor-cloud-dispatch-v2`; implementation `core/execution/cursor_cloud_dispatch.py`; config `core/managed-core/content/config/cursor-cloud-dispatch.json`; both present at protected baseline commit `a13a6467fc9bc2fccdddd1de8d9e258c78e57fdd`. |
| Model and binding | `ordinary-development` is provider `cursor`, model `grok-4.6`, effort `medium`, Fast `false`; request uses explicit repository URL and starting ref through `repos[]` or `CloudAgentOptions.repos`. |
| Result/status and failure behavior | `POST /v1/agents` must return `201`; `GET /v1/agents/{agentId}` must read back repository/ref/commit/tree/provider/model/effort/Fast; mismatch triggers archive and rejection; prepared/committed intent makes logical replay idempotent. |
| Source repository access | `gh` account `linktrend` is authenticated with ADMIN access to `linktrend/LiNKautowork`; remote protected `development` commit/tree readback succeeded. |
| Cloud worker authority | `CURSOR_API_KEY` reference absent from the environment and accessible GSM inventory; `cursor-sdk` not installed; `cursor-agent` `2026.08.11-e8db854` reports `Not logged in`. No account/repository readback from Cursor Cloud is therefore claimed. |
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
3. **Implementation-route capacity:** the route is source-verifiable but current
   account/client access is not. `CURSOR_API_KEY` and a matching GSM reference are
   absent, `cursor-sdk` is absent, and Cursor CLI is logged out. This blocks the
   first worker dispatch, while remaining separate from LiNKautowork product scope.
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
without that execution approval. Because current Cursor Cloud access is unverified,
execution still requires the route decision stated above; the package does not
mislabel that prerequisite as ready.

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
