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
| Executable after approval | READY WITH FIRST COORDINATOR ACTION | Read-only API GETs proved exact account `cursor-001@linktrend.one`, supported Grok 4.6 Medium/Fast-off parameters, and visibility of `linktrend/LiNKautowork`. Global suspension remains and the current coordinator ID is not yet allowlisted. After `APPROVE`, it must reconcile the prior owner and atomically add only its exact LiNKautowork grant before AW-01 submit. No new key, login, SDK installation or founder route decision is required. |
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
| Executable now after `APPROVE` | READY AFTER TERMINAL OWNER HANDOFF | Coordinator task `01a089cb-ef0d-75a2-b87f-4f3dd8163b24` owns `linktrend/LiNKautowork`; AW-01 is first. Prior Phase-admission task is terminal HOLD, but its queue row remains stale `running`. The coordinator immediately coordinates with prior owner `01a0843c-0df9-74e2-907a-05c5f736d6ed` to record the handoff; while pending, it may prepare only path-disjoint AW-01 issue metadata, with no takeover, dispatch or queue mutation. After reconciliation it preserves `SUSPENDED` and adds its exact single-repo grant under the shared lock. No second founder decision is required. |
| Later live prerequisites | HOLD BY DESIGN | Server01 service install, Platform registrations/PACI scopes, least-privilege database roles, exact migration receipts, GSM runtime secrets and private routes are AW-01/AW-05/AW-08 execution dependencies. They do not block source planning, but live deployment cannot pass without them. |

After Deployment Advisor acceptance of the exact package, the only founder decision
needed to start AW-01 is `APPROVE` for the final manifest digest and named Server01
scope. Advisor acceptance releases downstream planning only. Necessary Luna use
within that approved scope is already allowed; a switch records the concrete
ordinary-route failure rather than requesting approval again.

## Verified execution-route evidence

| Evidence | Read-only result |
|---|---|
| Dispatcher source/version | Operational standard-library REST client at the local coordinator path recorded in `CURSOR-CLOUD-EXECUTION-ROUTE.md`, SHA-256 `9c5b5486842e695e47f32896728ec15568237f304ea86115cde50997e419c260`. Adjacent `LANE-VERIFICATION.json` records 23 offline tests PASS and independent review PASS on that exact hash. Installed IDE Development 2.5.2 remains repository governance, not the transport dependency. |
| Model and binding | `ordinary-development` is provider `cursor`, model `grok-4.6`, effort `medium`, Fast `false`; the operational request uses one explicit repository URL and starting ref through REST `repos[]`. |
| Result/status and failure behavior | Submit persists a stable packet/agent identity before POST. Agent GET validates cloud host, agent ID, repository URL when returned, optional starting ref when returned, and no-auto-PR policy. Poll then reads the exact latest run. Worker Git attestation—not transport GET—proves starting/final repository/ref/commit/tree. |
| Source repository access | `gh` account `linktrend` is authenticated with ADMIN access to `linktrend/LiNKautowork`; remote protected `development` commit/tree readback succeeded. |
| Cloud worker authority | Direct read-only GETs proved Keychain account `cursor-001@linktrend.one`, exact model parameters and LiNKautowork repository visibility. Credential value remained in process memory and was not printed. Environment variables, Cursor CLI login and `cursor-sdk` are not dependencies of this operational REST client. |
| Checkpoint and PR handoff | `scripts/gitops/completion_gate.py` records exact pushed Issue checkpoint evidence; the Phase Packager/Coordinator opens the draft Phase PR; `scripts/gitops/delivery_controller.py` performs protected integration after required evidence. |
| Fallback | Registry route `luna-fallback`: Codex CLI `gpt-5.6-luna`, effort `high`, Fast `false`. Necessary use is already allowed within this execution model; after `APPROVE`, a recorded ordinary-route failure may switch without a new decision. |

## Startup ownership and environment evidence

| Requirement | Current evidence and execution treatment |
|---|---|
| Owner/repository/first packet | Coordinator `01a089cb-ef0d-75a2-b87f-4f3dd8163b24`; repository `linktrend/LiNKautowork`; first packet AW-01. The cloud packet `owner` is this exact task ID. |
| Existing work | PR #125 remains draft; issue #124 and #126 worktrees are present and clean. Provider GETs show all recorded LiNKautowork cloud jobs terminal. A bounded task read proved `autowork-phase-admission-015` terminal HOLD before Phase creation on missing supported GitHub credentials; its old-owner queue row is stale `running`. Owner `01a0843c-0df9-74e2-907a-05c5f736d6ed` records the coordinated terminal handoff before worker admission; issue-metadata preparation may proceed independently while that bounded reconciliation is pending. |
| Baselines | Planning identity is the pushed issue-127 branch plus manifest digest below. LiNKautowork protected `development` remains the manifest identity. LiNKplatform protected `development` advanced mechanically to `f6373fccc89732cbb88bb18562daa69cc031a2e3` / tree `83feddf7d935561cfede60df456ea616a021d726`; GitHub compare from the planned pin changes only migration-control restore/fingerprint source, its focused test and the fixture declaration, with no approved contract, PACI, schema or migration path. |
| Suspension/ownership | `SUSPENDED` remains. Current `RESUME-SCOPE.json` maps exact owner task IDs to repositories and does not contain this coordinator. The route document defines post-APPROVE exclusive shared-lock serialization across read/check/write, atomic replacement adding only this coordinator/LiNKautowork pair, and entry-only rollback preserving other grants. |
| Cloud runtime/dependencies | CI uses Ubuntu 24.04 ARM, Node 22 and `npm ci`; application images use Node 22.13.1 Alpine. No submodule or private npm dependency was found. Disposable worker install is an execution step after approval. |
| Permissions | Keychain/API GET is non-interactive. Cloud writers have only issue-branch Git/network capability under prompt and transport controls; they cannot create issues, publish privileged checks, merge, deploy or access production secrets/data. Coordinator tooling owns those actions. |
| Parallelism | Maximum safe source concurrency is two in one verified window after AW-01: AW-02 plus AW-05, using lane IDs `L-B` and `L-C` bound to manifest SHA-256 `8a19a79b1461abad4abef25970a7ff3ad7c4363c042fc9c26b276d4551da34c5`. AW-03 remains repository-exclusive because it owns root package/lock files. The dispatcher extension is verified; the manifest's installed local slot value remains historical plan truth, while live admission applies the narrower documented window and authenticated capacity. |
| Server/artifact path | SSH alias `linkserver-01`, user `linktrend`, non-interactive sudo verified; Docker 29.8.0/Compose 5.5.1; 147 GiB free `/srv`. Direct Docker/socket and `/srv` write are intentionally denied. Existing Compose builds locally from exact protected source; external registry is not required, and image IDs/digests form the immutable handoff. |

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
`8a19a79b1461abad4abef25970a7ff3ad7c4363c042fc9c26b276d4551da34c5`.

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
