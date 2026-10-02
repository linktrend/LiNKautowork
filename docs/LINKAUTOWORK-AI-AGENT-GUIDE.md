# LiNKautowork — AI agent guide

Last checked: 2026-10-02. This is the current orientation document for coding,
review, release, operations, and deployment agents. Read it before acting, then
read the linked contract or runbook for the task you own. It describes the
repository and its intended operation; it does not grant production access.

Current branch, receipt, and deployment facts are maintained in the
[release status](./LINKAUTOWORK-RELEASE-STATUS.md). Historical plans and
session notes are under [`archive/development-history/`](./archive/development-history/).

## 1. What the software does

LiNKautowork is LiNKtrend's self-hosted automation engine. It hosts and governs
approved workflows, receives signed requests through a policy gateway,
checks tenant and lifecycle rules, records durable control state, and emits
versioned events for other LiNKtrend Programs. Stock n8n runs workflows; the
gateway and supporting services enforce LiNKtrend's policy and operational
boundaries. Canonical workflow templates are in `automations/templates/`.

This repository is not a customer-facing automation marketplace. Other
Programs integrate through documented HTTP, NATS, and database contracts. The
internal organisation identifier is
`00000000-0000-0000-0000-000000000001` (`linktrend_internal`); the event prefix
is `linkautowork.v1.*`. Ritual times in the product are Taipei time.

## 2. Main parts and technology

- **Workflow engine:** pinned stock n8n Community image `n8nio/n8n:2.30.0`;
  this project does not maintain a fork.
- **Policy gateway:** TypeScript/Node.js service for signed ingress,
  authorization, token handling, audit events, lifecycle and kill-switch
  checks, and NATS publication.
- **Product surfaces:** `apps/product-api`, `apps/operator-console`, and
  `apps/web`. The client web image is retained for later use and is not part of
  the initial public route.
- **Automation packages:** the `packages/automation-*` packages provide
  contracts, authoring, operations, evaluation, and supporting automation
  services.
- **Durable data:** ordered SQL migrations in `supabase/migrations/` describe
  the `lautowork` and `lautowork_n8n` schemas on LiNKtrend's shared platform
  database. LiNKplatform owns and applies production migrations; an Autowork
  agent must not apply them directly.
- **Messaging:** NATS JetStream provides durable internal events. The
  production Compose definition pins NATS to `nats:2.10.26-alpine`.
- **Deployment:** Docker Compose is defined in `deploy/prod/`. Private routing
  templates are under `deploy/templates/`; runtime secret values are supplied
  on the host from Google Secret Manager (GSM), never committed to Git.
- **Build and checks:** Node.js 22, npm with the committed `package-lock.json`
  (lockfile version 3), TypeScript, Vitest, and Playwright. GitHub Actions is
  the authority for full hosted CI, including checks that require Docker.

See the [Technical PRD](./LINKAUTOWORK-TECHNICAL-PRD.md) for component and
contract details, and the [Operations Manual](./LINKAUTOWORK-OPERATIONS-MANUAL.md)
for the founder-facing explanation.

## 3. Repository map

| Location | What it contains |
|---|---|
| `gateway/` | Policy gateway and service interfaces |
| `apps/` | API, operator console, and web application |
| `packages/` | Reusable automation and domain packages |
| `automations/templates/` | Governed workflow templates |
| `automations/evals/` | Source evaluation fixtures; they do not perform live dispatch |
| `deploy/prod/` | Production Compose contract and names-only environment example |
| `deploy/templates/` | Private routing and network boundary examples |
| `supabase/migrations/` | Ordered Platform-owned database migrations |
| `ops/` | Deployment, migration preflight, backup, GSM, and operations helpers |
| `docs/contracts/` | Provider and Server01 contracts |
| `docs/runbooks/` | Current operating and release procedures |
| `docs/end-to-end-delivery/evidence/source-release/` | Historical source-release packet and deployment handoff; read current release status before use |
| `docs/archive/development-history/` | Archived planning, build log, roadmap evidence, and dated handoffs |
| `archive/legacy-dev-mirrors-2026-07-15/` | Separate legacy mirror archive; preserve unchanged |

## 4. How agents operate safely

1. Read this guide, the current [release status](./LINKAUTOWORK-RELEASE-STATUS.md),
   applicable `AGENTS.md` instructions, and the exact task contract/runbook.
2. Verify the repository is `https://github.com/linktrend/LiNKautowork` and
   inspect the exact branch, commit, tree, and working-tree status. Never reset
   or overwrite unknown local work.
3. Use an issue branch created by `python3 scripts/gitops/create_issue_branch.py`.
   Commit and push checkpoints to that branch.
4. Run the required focused checks. Phase Packager/Coordinator creates the
   Phase PR; the delivery controller integrates it to `development`. Only the
   founder/controller handles promotion through `staging` and `main`.
5. Do not make a live change unless the exact task has the required approval,
   access, current backup, and recovery evidence. A passed source test is not
   permission to touch production.

Implementers do not open their own PR, review their own work, merge protected
branches, tag a release, or promote to `staging` or `main`. Never bypass a
required check or invent a receipt. Never commit secrets or runtime `.env`
files. Use GSM secret names in configuration examples and obtain values only
through the approved host process.

## 5. Build and verify

From a clean checkout using Node.js 22:

```bash
npm ci
git diff --check
npm run release:check
npm run ci
```

`release:check` checks supported files and required release artifacts. `npm
run ci` is the full repository suite; hosted GitHub Actions is authoritative
when a local machine lacks Docker or browser dependencies. Report the exact
commit and the actual result of every check. Do not substitute old CI for a
new candidate's receipt.

For JSON files, validate the specific file with `python3 -m json.tool
<path>`. Do not rerun live or Docker-backed commands from a documentation-only
task. Follow the repository's installed completion-gate and packager workflow
for evidence and integration.

## 6. Deployment and operations

Production uses `deploy/prod/docker-compose.yml` with project name
`linkautowork-prod`. The names-only environment contract is
`deploy/prod/.env.example`; actual secret values are rendered from GSM to
mode-`0600` files outside the repository. Application images and deployment
configuration are selected by an exact release commit, not `latest` or a work
branch. Private routing examples are in `deploy/templates/`.

The intended host layout is `/srv/linktrend/deploy/linkautowork/releases/<commit>`
with `current` and `previous` release pointers. Runtime env files belong under
`/srv/linktrend/runtime/linkautowork/*.env.runtime`, outside Git and mode
`0600`. The Compose stack must remain private; do not publish the internal
service ports on the host. Image IDs/digests and live configuration evidence
are recorded on the host as the runbook directs, never as secret values in a
source commit.

Use `docs/runbooks/OPERATIONS.md` for the Compose topology,
`docs/runbooks/SERVER01-OPERATIONS.md` for Server01 operation and restore,
`docs/runbooks/PRODUCTION_RELEASE_GATES.md` for release gates, and
`docs/end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md` for
the deployment input inventory. That older handoff records its own historic
admission state; the current [release status](./LINKAUTOWORK-RELEASE-STATUS.md)
and the protected main ref take precedence.

The ordered database package is described in
`docs/contracts/server01/MIGRATION-PACKAGE.json`. LiNKplatform owns production
database application and acceptance. Autowork deployment agents must not
apply that SQL directly. Until release identity, hosted checks, Platform
approval, backup/isolated-restore evidence, host configuration, and acceptance
are all current and exact, report **HOLD** and leave production unchanged.

For any approved deployment, first prove the peeled annotated tag equals the
protected `origin/main` commit and that both trees match. Require green hosted
LiNKautowork CI for that exact commit. Install the stack inactive, import the
technical fixture inactive, and do not activate a canary without explicit
founder and Platform authority. Before acceptance, prove backup and isolated
restore plus rollback to `previous`. See `docs/runbooks/PRODUCTION_RELEASE_GATES.md`
and the deployment handoff for the ordered checklist; this guide does not
replace those procedures.

## 7. Product and operational references

- [Product intent](./LINKAUTOWORK-INTENT.md)
- [Technical PRD](./LINKAUTOWORK-TECHNICAL-PRD.md)
- [Operations Manual](./LINKAUTOWORK-OPERATIONS-MANUAL.md)
- [Production configuration PRD](./PRD.md)
- [Production work packets](./WORK-PACKETS.md)
- [Production-readiness index](./PRODUCTION-READINESS.md)
- [Documentation index](./README.md)
- [Archive index](./archive/README.md)

Archived records may explain why prior decisions were made. They are not
current instructions where they conflict with this guide, live contracts,
runbooks, or current release status.
