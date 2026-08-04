# LiNKautowork — Intent

**Status:** Confirmed Intent for the LiNKautowork Program itself (this repository), written in the same spirit as LiNKdeveloper's Intent artifact — a plain-English statement of what is being built, why, for whom, and what "done" means. Grounded in what the code, compose stacks, Supabase migrations, and live templates actually deliver today (2026-07-19), not in aspirational PRD roadmap language.

**Audience:** The Principal (sole human authority) and any agent or Integrator that needs to understand *why this Program exists* before reading the Technical PRD.

**Companion document:** [`LINKAUTOWORK-TECHNICAL-PRD.md`](./LINKAUTOWORK-TECHNICAL-PRD.md) — exhaustive how-it-works reference.

---

## 1. Problem

LiNKtrend runs an AI-native studio that must automate internal operations (ritual gates, urgent event intake, promotion/restore governance, emergency brakes) without a human sitting in every webhook path.

A bare n8n instance is not enough:

- Anyone who can hit a webhook can trigger work without tenant, lineage, or signature checks.
- Secrets end up in workflow JSON or host env files if there is no Just-In-Time retrieval path.
- Kill-switch and lifecycle decisions disappear on process restart if they live only in memory.
- Studio Programs need a shared event language (`linkautowork.v1.*`) and an auditable ledger, not ad-hoc Slack posts.

The problem LiNKautowork solves is: **give LiNKtrend a governed, self-hosted automation runtime — n8n for execution, a policy gateway for security and audit, canonical templates for what is allowed to run, and durable control data on the shared platform database — so studio operations can be automated safely.**

---

## 2. Who it is for

| Role | Relationship to LiNKautowork |
|---|---|
| **Principal (Carlos)** | Sole human authority. Approves protected lifecycle actions (promotion/restore decisions). Reviews ritual outputs and exceptional kill-switch incidents. Does not write workflow JSON or manage day-to-day gateway ops. |
| **LiNKtrend studio (agent roles)** | Operators and Integrators deploy stacks, import templates, and keep CI green under this Program's contracts. |
| **Other Programs** (LiNKplatform, LiNKsites, LiNKdeveloper, …) | Consumers of shared org identity (`platform.organizations`) and explicitly wired `linkautowork.v1.*` events. They do **not** embed LiNKautowork as a library — they call the gateway / subscribe to events when wired. |

LiNKautowork is **not** a customer-facing SaaS product in the MVO. External marketplace / multi-client hosting is deliberately deferred.

---

## 3. What "done" looks like (Program-level)

For the current Minimum Viable Operations (MVO) bar, "done" means:

1. **Runtime** — Docker Compose stacks for stage (`deploy/dev`) and prod (`deploy/prod`) run NATS + gateway + pinned stock n8n `2.30.0`.
2. **Policy** — Signed ingress, service tokens, control tokens, canonical internal org UUID enforcement, and GSM-backed secret resolution are implemented in `gateway/`.
3. **Templates** — Live governance templates in `automations/templates/` are the authority for what n8n should run; historical Program shells are non-authoritative archive material.
4. **Control data** — Supabase schemas `lautowork` (audit / lifecycle / kill-switch) and `lautowork_n8n` (n8n isolation) exist on `linkplatform-stage` / `linkplatform-prod`, with kill-switch + lifecycle persistence and hydrate-on-boot.
5. **Interoperability** — Gateway publishes the supported `linkautowork.v1.*` NATS subjects.
6. **Deploy readiness** — Code + schemas + compose + secrets contract + governance templates are ready for VPS live bring-up (`docs/DEPLOY_READINESS.md`). Choosing/provisioning the VPS and filling real GSM values remain **ops inputs**, not software holes.

**Studio-level "coding done" bar (as of 2026-07-19):** gateway packages typecheck and pass tests (`npm run ci`); templates validate; env contract and secret scan pass. That is **not** the same as "a continuous production VPS has been live-operated for months" — first live bring-up steps are documented and still operator-driven.

---

## 4. Scope — inputs and outputs

### Inputs (what LiNKautowork takes)

- Canonical workflow JSON under `automations/templates/` (and `manifest.json`).
- Signed mission envelopes (tenant, mission/run/task/dpr lineage, trigger source) on gateway ingress.
- GSM secret **names** in env examples; resolved values at runtime outside the repo.
- Shared platform org identity from LiNKplatform (`platform.organizations`, `platform.has_org_access()`).
- Operator actions: deploy stack, import templates, activate kill-switch / lifecycle transitions, backup drills.

### Outputs (what LiNKautowork produces)

- Executed n8n workflows (governed dispatch + scheduled ritual gates).
- Durable rows in `lautowork.audit_runs`, `lautowork.lifecycle_transitions`, `lautowork.killswitch_events`.
- NATS events on `linkautowork.v1.*`.
- Ritual gate outputs (strategic / operational / quality) to Slack + events + audit when templates are active.
- Ops evidence: live exports, backup archives, CI green on promotion SHAs.

### Explicit out of scope (deliberate — not forgotten)

| Out of scope | Why / status |
|---|---|
| Public automation marketplace / client self-service provisioning | PRD Gate 2 — deferred |
| Autonomous bot-driven JSON self-editing of production workflows | PRD Gate 1 / Karpathy loop as live autonomy — deferred; eval assets exist as baseline |
| Full commercial multi-tenant client isolation beyond internal org | MVO enforces one canonical internal org UUID; broader SaaS tenancy not claimed complete |
| Maintaining a LiNKtrend fork of n8n (`linktrend/link-n8n`) | Principal decision 2026-07-23: not needed — stock upstream image only; remote fork may be archived later |
| Owning LiNKbrain memory / LiNKskills RPE product logic | Bridge and events only; those Programs own their domains |
| Historical Program invoke shells | Removed from the live template set; retained only as non-authoritative archive evidence |

---

## 5. Guiding governance principles

1. **Templates are authority.** `automations/templates/` wins over anything edited only in a live n8n UI. Live exports are evidence, not source of truth.
2. **Fail closed on identity and signature.** Wrong tenant UUID, bad HMAC, replayed nonce, or active kill-switch → reject; silence is never approval.
3. **No secrets in repo or workflow JSON.** GSM Just-In-Time retrieval; `.env.example` holds names only.
4. **Durable emergency brakes.** Kill-switch and lifecycle transitions persist to Supabase and hydrate on gateway boot.
5. **Shared org model.** Control tables use `org_id` → `platform.organizations` (ADR 0001); wire/env still say `tenant_*` where contracts require it.
6. **Pin what you run.** n8n image tag and deploy git SHA are immutable; never `:latest` in prod.
7. **Protected actions need Principal approval.** Lifecycle `protectedAction` and restore/promotion decisions require `chairmanApproved`.
8. **Promotion is auditable.** `development` → `staging` → `main` via PR policy; production deploys only from `main`.

---

## 6. Success criteria

| Criterion | Evidence that counts |
|---|---|
| MVO control plane is structurally complete | Gateway tests green; CI (`validate:templates`, env contract, secret scan, typecheck) green |
| Schemas applied | `lautowork` + `lautowork_n8n` on stage/prod per `DEPLOY_READINESS.md` |
| Kill-switch survives restart | Activate → row in `killswitch_events` → gateway restart → ingress still blocked |
| Ritual windows exist | `ritual-gates-unified.json` schedules 08:00 / 10:45 / 14:45 Asia/Taipei |
| Event interoperability | `linkautowork.v1.*` subjects published |
| Live VPS continuous operation | **Ops milestone**, not a claimed coding gap — see Deploy Readiness "Still an ops input" |

---

## 7. Relationship to other documents

| Document | Role |
|---|---|
| `docs/OPEN-ISSUES.md` | Append-only build / compliance log — what was built, deferred, and limited. Prefer over stale prose elsewhere. |
| `docs/LINKAUTOWORK-TECHNICAL-PRD.md` | Exhaustive technical reference for how the system works. |
| `docs/LINKAUTOWORK-OPERATIONS-MANUAL.md` | Plain-English handbook for the Principal. |
| `docs/DEPLOY_READINESS.md` | Live DONE definition for VPS bring-up (kept operational). |
| `docs/runbooks/*` | Operator procedures (deploy, Tailscale, release gates, proof notes). |
| `docs/archive/*` | Superseded PRD / implementation / contract / upstream docs — history only. |

---

## 8. One-sentence Intent

**LiNKautowork is LiNKtrend's self-hosted automation engine: a pinned stock upstream n8n Community runtime behind a signed policy gateway, with canonical governance templates, persisted kill-switch/lifecycle controls, shared-platform org identity, and `linkautowork.v1.*` events — so studio rituals and emergency brakes run safely without putting secrets or ungoverned webhooks in the critical path.**
