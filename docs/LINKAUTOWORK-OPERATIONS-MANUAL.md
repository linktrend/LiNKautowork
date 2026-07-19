# LiNKautowork Operations Manual

**Who this is for:** you — LiNKtrend’s Principal. You make strategic decisions and approve a small number of protected actions. You do not write workflow JSON, run server commands, or manage Docker day to day.

**What this is:** a plain-English handbook for how LiNKautowork works *today*, and what your role in it is. It is not a technical design document.

**Honesty rule:** everything below describes what is actually built in the software right now. Where something is planned but not available yet, it is labeled clearly under [Current status](#current-status-what-is-not-available-yet).

---

## What LiNKautowork is

LiNKautowork is LiNKtrend’s internal automation engine: a self-hosted workflow runner (n8n) plus a security gateway in front of it.

In plain terms:

1. Workflows are defined once in this repository (the templates folder is the authority).
2. Operators deploy those templates onto the runner.
3. Outside systems call the gateway — not raw n8n — so identity, signatures, secrets, logging, and emergency stops are enforced.
4. Important decisions (promotions, restores, kill switches) leave a durable record in the shared company database.

Think of it as the studio’s “nervous system” for scheduled reviews and emergency brakes — not a public product you sell to clients yet.

---

## Your role today

### Where automation starts

Operators (or agents acting as operators) maintain the templates, deploy the stack, and import workflows. You are not expected to open n8n or edit JSON.

### Moments when a human decision is required

| When | What you are asked | What happens if you say no |
| --- | --- | --- |
| Protected promotion / restore decisions | Approve a protected lifecycle action (the system calls this Principal / “chairman” approval) | The transition is rejected; the workflow stays in its prior state |
| Exceptional kill-switch / security incidents | Confirm scope (one workflow vs everything) and later authorize a governed restore | Without your approval path, protected restores do not proceed |
| Ritual briefings (optional attention) | Read strategic / operational / quality gate outputs when they matter | Outputs still ship on schedule; your attention is judgment, not a mechanical blocker for every run |

### What you do **not** need to do

- Write or debug n8n workflows
- Manage servers, Tailscale, or Google Secret Manager day to day
- Approve every routine webhook or scheduled ritual
- Merge every code change (Integrators merge to `development`; you only approve promotions to staging/main when following the studio’s release process)

---

## The moving parts (plain names)

| Plain name | What it is |
| --- | --- |
| Templates | The approved workflow definitions in the repo — source of truth for what should run |
| Gateway | The locked front door: checks signatures, tenant identity, kill switches, then talks to n8n |
| n8n runner | The engine that actually executes workflows (pinned version; not “whatever latest is”) |
| Control ledger | Database tables that remember audits, promotions, and kill-switch events |
| Ritual windows | Three daily Taipei-time checkpoints: morning strategic, mid-morning operational, afternoon quality |
| Kill switch | Emergency brake — one workflow, or everything |
| Events | Messages on the studio event bus so other systems can listen (`aios.*`) |

---

## Walkthrough: how a normal request works

1. Something (another system, a ritual, or an ops tool) sends a signed request to the gateway.
2. The gateway checks: Is the signature valid? Is this the internal studio identity? Is a kill switch active? Are required secrets available from the secret store?
3. If checks pass, the gateway asks n8n to run the matching workflow webhook.
4. The gateway writes an audit record and publishes an event.
5. If anything security-sensitive is wrong, the request is rejected — it does not quietly proceed.

### Rituals (daily cadence, Taipei time)

- **08:00** — strategic gate feed  
- **10:45** — operational pulse (the main “how are operations doing?” window from the original product intent)  
- **14:45** — quality gate feed  

Each is meant to land in Slack and on the event bus, with an audit trail. If input data is weak, the output should still go out on time with a clear “confidence is low” style flag — not silently invent certainty.

### Lifecycle (how a template graduates)

Templates move through named states:

`draft → tested in development → QA approved → ops approved → deployed to production → deprecated → archived`

Certain steps need named role approvals (auditor, Head of Quality, COO). **Protected** steps need your approval. That is how promotions and restores stay intentional.

---

## What happens when something goes wrong

- **Wrong identity or bad signature** — the gateway refuses the call.
- **One workflow misbehaving** — operators can activate a **scoped** kill switch; that workflow’s ingress is blocked and the event is recorded.
- **Platform-wide incident** — a **global** kill switch deactivates active workflows in n8n and blocks new ingress until released through the governed path.
- **Gateway restarts** — kill-switch state is loaded back from the database so a reboot does not accidentally “forget” an emergency brake.
- **Deploy / restore drills** — operators run backup and restore-check scripts; targets are roughly “back within an hour” and “lose at most about fifteen minutes of data” for the MVO reliability bar.

Failures are designed to **stop** unsafe work, not to keep spending or keep firing webhooks while pretending everything is fine.

---

## Current status (what is not available yet)

Framed as **where we are**, not as a defect list:

| Topic | Status today |
| --- | --- |
| Internal automation for rituals, intake, promotion/restore governance | **Built** in templates + gateway |
| Security front door (signatures, secrets, audit, kill switch) | **Built** and tested in automated checks |
| Database control schemas on the shared stage/prod projects | **Applied** (per deploy-readiness close-out) |
| Dropping this onto a VPS and live-testing | **Ready as software**; choosing the machine and filling real secrets is still an **ops** step |
| Public marketplace / selling automations as a product | **Not built** (deliberately later) |
| Bots that rewrite production workflows by themselves | **Not built** as a live feature (research/eval assets exist as a baseline) |
| Many external client tenants | **Not claimed** — MVO runs the one internal studio identity |
| Custom n8n fork image in production | **Not used yet** — production runs a pinned stock n8n; the fork is kept ready for when custom changes are needed |

---

## FAQ

**Do I need to open n8n?**  
No. Operators handle the editor when needed. Your job is approvals and attention on ritual/exception outputs.

**What if I don’t like a promotion?**  
Do not approve the protected action. The lifecycle transition fails closed.

**Can clients use this as a hosted product today?**  
Not as a finished commercial offering. The MVO is internal studio utility with contracts shaped so a later multi-tenant product can be added without rewriting the front door from scratch.

**Where do the “source of truth” documents live?**  
- Intent (why) — `docs/LINKAUTOWORK-INTENT.md`  
- Technical reference (how) — `docs/LINKAUTOWORK-TECHNICAL-PRD.md`  
- This handbook — `docs/LINKAUTOWORK-OPERATIONS-MANUAL.md`  
- Engineering build log — `docs/OPEN-ISSUES.md`  

Older PRD and implementation writeups are archived under `docs/archive/`.

**Who runs deploys?**  
Someone technical follows the operations runbooks (`docs/runbooks/`). You approve release promotions on the git branches when the studio process calls for Principal approval.

---

## One-page reminder

1. Templates in the repo are the authority for what should run.  
2. Everything important goes through the gateway (identity, signature, secrets, audit).  
3. Three Taipei ritual windows: 08:00 / 10:45 / 14:45.  
4. You approve protected promotions/restores; you do not operate servers day to day.  
5. Kill switches are real and remembered across restarts.  
6. Marketplace and self-editing bots are later; VPS live bring-up is an ops step on ready software.
