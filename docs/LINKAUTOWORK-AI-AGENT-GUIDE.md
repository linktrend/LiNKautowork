# LiNKautowork 1.0 — AI agent guide

Audience: every AI agent that will read, review, integrate, or later deploy
this Program. Humans may read it; it is written so an agent can execute
without inventing architecture or live authority.

Status: **source 1.0 consolidation** on work branch
`issue/166-consolidate-linkautowork-1-0-repository-and-publ`. This document
does **not** claim Server01 is live, does **not** authorise protected merges,
and does **not** replace Phase Packager / delivery-controller integration.

Companion packet (non-secret install inputs for a later Server01 agent):
[`end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md`](./end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md).

---

## 1. What this repository is

LiNKautowork is LiNKtrend’s self-hosted automation engine:

- pinned stock n8n Community `2.30.0` (no `link-n8n` fork);
- a policy/security gateway (signed ingress, tokens, GSM names, audit, kill-switch, NATS);
- canonical governance templates under `automations/templates/`;
- durable control data on the shared platform database (`lautowork` + `lautowork_n8n`);
- product-api, operator-console, and a retained (not initial-route) client-web image.

Internal org UUID: `00000000-0000-0000-0000-000000000001` (`linktrend_internal`).
Event namespace: `linkautowork.v1.*`. Ritual windows (Taipei): `08:00` / `10:45` / `14:45`.

It is **not** a customer SaaS marketplace. External Programs consume published
HTTP/NATS/SQL contracts; they do not embed this repo as a library.

---

## 2. Exact identity before any product work

Cursor cached builds may check out `main`. Do not treat `main`, `staging`, or
`latest development` as this 1.0 line until the recorded tag on `main` exists
(see §8).

Verify, in order:

1. Origin is `https://github.com/linktrend/LiNKautowork` (ignore token userinfo).
2. Fetch **only** the supplied work ref first.
3. Compare fetched commit **and** tree to the supplied identity. Stop on mismatch.
4. Checkout that commit (read-only) or the owned `issue/<n>-<slug>` (writer).
5. If the working tree is unexpectedly dirty, stop. Do not reset unknown work.

This consolidation packet admitted:

| Field | Value |
|---|---|
| Repository | `linktrend/LiNKautowork` |
| Writer branch | `issue/166-consolidate-linkautowork-1-0-repository-and-publ` |
| Starting commit | `a3c22a868a89c7627bd3018ece5edb21e7c59351` |
| Starting tree | `bf85913dc6fb0b41c3c235cb6e8050db597802a3` |

Agent 1 (issue 165) sealed the engineering candidate that hosted CI passed:

| Field | Value |
|---|---|
| Engineering commit | `20f3d4cc03445ca443e31c41f22d34347c866acf` |
| Engineering tree | `95bec98a0d65ca30889e595a7bcaa85ddfe52b47` |
| Hosted CI | https://github.com/linktrend/LiNKautowork/actions/runs/34955615212 (`success`) |

`origin/development` at admission equalled that engineering SHA. Docs-only
evidence commits sit **on top** of it on issues 165/166. Protected `main` at
admission was still `2e30109acfb9510cd77e49f759648b2b6a666adc` (bootstrap),
**not** this 1.0 line.

Existing annotated tag `v1.0.0` peels to `7e76a5e77306d42cdcfd4fd59f22473235c7e7fc`
tree `44e85044d16c9a3a6fad5f7e95e607ca0e027358`. That is **not** the 1.0
candidate. Do not deploy it.

---

## 3. Authoritative documents vs development-only

**Start here (1.0 agent authority):**

1. This guide.
2. [`end-to-end-delivery/evidence/source-release/README.md`](./end-to-end-delivery/evidence/source-release/README.md) — AW-07 source packet.
3. [`end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md`](./end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md) — AW-08 inputs.
4. [`runbooks/OPERATIONS.md`](./runbooks/OPERATIONS.md) — source Compose topology (no live start).
5. [`contracts/server01/MIGRATION-PACKAGE.json`](./contracts/server01/MIGRATION-PACKAGE.json) — Platform-owned SQL package (live apply HOLD).
6. Product description still in [`LINKAUTOWORK-INTENT.md`](./LINKAUTOWORK-INTENT.md), [`LINKAUTOWORK-TECHNICAL-PRD.md`](./LINKAUTOWORK-TECHNICAL-PRD.md), [`LINKAUTOWORK-OPERATIONS-MANUAL.md`](./LINKAUTOWORK-OPERATIONS-MANUAL.md).

**Remaining production configuration (not claimed done by 1.0 source):**
[`PRD.md`](./PRD.md), [`WORK-PACKETS.md`](./WORK-PACKETS.md), [`PRODUCTION-READINESS.md`](./PRODUCTION-READINESS.md).

**Superseded for agent entry:** session handoffs, Cursor Cloud planning routes,
dated packet planning, and pre-1.0 checklists. Index and replacement pointers:
[`archive/LINKAUTOWORK-1.0-SUPERSEDED-INDEX.md`](./archive/LINKAUTOWORK-1.0-SUPERSEDED-INDEX.md).
Physical moves of files required by `npm run release:check` are out of this
packet’s allowed paths; those files remain on disk but **must not** override
this guide.

If two documents disagree, this guide plus the source-release packet win for
1.0 agent procedure. The Technical PRD still wins for how the running code is
shaped.

---

## 4. Layout (what you may touch depends on your issue)

| Path | Role |
|---|---|
| `gateway/` | Policy gateway, provider v2, in-process runtime dispatch |
| `apps/product-api`, `apps/operator-console`, `apps/web` | Product surfaces; `client-web` is `--profile retained-images` only |
| `packages/automation-*` | Architect, contracts, operations, eval-runner, librarian |
| `automations/templates/` | Live governance JSON (authority for n8n) |
| `automations/evals/server01-runtime-acceptance/` | Source eval fixture (`n8n_dispatched` always false here) |
| `deploy/prod/` | Production Compose contract, names-only `.env.example` |
| `supabase/migrations/` | Ordered SQL; Platform applies live |
| `ops/` | Deploy/backup/GSM/import helpers; many refuse `--live` |
| `docs/end-to-end-delivery/evidence/source-release/` | 1.0 source receipts |
| `docs/archive/` | Historical / superseded |
| `archive/legacy-dev-mirrors-2026-07-15/` | Untouched bulk mirror |

---

## 5. Toolchain (do not silently unpin)

Admitted CI (`.github/workflows/ci.yml`):

- Runner: `ubuntu-24.04-arm`
- Node: `actions/setup-node` **major 22** (not a patch pin)
- Install: **`npm ci`** against `package-lock.json` lockfileVersion 3
- Playwright: `npx playwright install --with-deps chromium`
- Images: `FROM node:22.13.1-alpine` in application Dockerfiles
- n8n image tag: `n8nio/n8n:2.30.0`
- NATS image tag: `nats:2.10.26-alpine`

**Pin defects (diagnosed, not repaired in this docs packet):**

- No `package.json` `engines` field.
- No `.nvmrc` / `.node-version`.
- Python is stdlib `json.tool` only; no project pin.
- Writer cloud PATH may expose `/exec-daemon/node` (observed v22.14.0) **before** nvm. Prefix `PATH` with the nvm Node 22 binary directory before `npm ci`.

Do not change `package-lock.json` in a docs/consolidation role. Do not install
or start Docker unless your packet explicitly owns live/disposable Docker and
policy allows it.

Locked tool versions observed from this lockfile: TypeScript `5.9.3`, Vitest
`4.1.10`, Playwright `1.57.0`.

---

## 6. Git and roles (hard stops)

- Work on `issue/<n>-<slug>` created/reused by `python3 scripts/gitops/create_issue_branch.py`.
- That helper **fetches `origin/development`**. If your packet requires an exact
  supplied SHA that is not latest development, **do not run it**; reuse the
  already-owned issue branch at that SHA.
- **Implementers do not open PRs, merge, self-review, or promote.** Phase
  Packager/Coordinator (`scripts/gitops/packager_coordinator.py`) opens the
  draft Phase PR. Delivery controller merges to `development`. Principal /
  controller promote `development` → `staging` → `main`.
- Ship = commit + push on the issue branch (checkpoint).
- Finished issues: tests, `completion_gate.py write-evidence`, then
  `review-ready` only from the trusted publisher path. Never write
  `.linktrend/review-ready.json`.
- Protected refs: `development`, `staging`, `main`. Never push them. Never
  `--prefer-incoming`.
- Nested workers / extra Cursor dispatches are forbidden unless the governing
  packet says otherwise.

Secrets: GSM names `LINKTREND_[SERVICE]_[ENV]_[RESOURCE]_[IDENTIFIER]`. Never
commit values. Runtime env files are mode `0600` **outside git**.

---

## 7. Acceptance commands used by this consolidation

```bash
git diff --check
python3 -m json.tool docs/end-to-end-delivery/EXECUTION-MANIFEST.json
# PATH must be nvm Node 22, not /exec-daemon/node
npm run release:check
```

Full hosted proof remains `npm run ci` on GitHub Actions (`LiNKautowork CI`).
Writer VMs without Docker **must not** retry an unchanged `npm run ci` after
`spawnSync docker ENOENT`. Substitute hosted CI on the **engineering** SHA
`20f3d4cc03445ca443e31c41f22d34347c866acf` for Docker-backed steps.

Planning JSON `docs/end-to-end-delivery/EXECUTION-MANIFEST.json` still records
baseline commit `a13a6467fc9bc2fccdddd1de8d9e258c78e57fdd`. Do not rewrite it
from a docs-only packet.

---

## 8. Exact tagged main candidate (for a **separate** Server01 agent)

This implementer **does not** tag, promote, SSH, compose-up, apply SQL, or
resolve GSM.

The Server01 deployment agent must install **only** an annotated tag on
protected `main` after controller promotion of this 1.0 line. Required checks
before any live action:

1. `git fetch origin tag <tag> --no-tags` (or equivalent single-tag fetch).
2. Peeled commit `git rev-parse <tag>^{}` equals `origin/main`.
3. Tree `git rev-parse <tag>^{tree}` equals the tree recorded on that main tip.
4. Tag is **not** the stale `v1.0.0` object `88330d2e5ff1dc1627ab52652714681dd5c1af61`.
5. Hosted `LiNKautowork CI` is green on that peeled commit.
6. Compose file is `deploy/prod/docker-compose.yml`, project `linkautowork-prod`.
7. Env names only from `deploy/prod/.env.example`; values from GSM on the host.
8. Migration package `lautowork.server01.migration-identity/1.0.0` is applied
   **by LiNKplatform**, not by Autowork workers.
9. Release layout: `/srv/linktrend/deploy/linkautowork/releases/<commit>` with
   `current` / `previous` pointers. Runtime env under
   `/srv/linktrend/runtime/linkautowork/*.env.runtime` mode `0600`.

Until those identities exist on `main`, the deployment agent’s result is
**HOLD**. Do not fall back to issue 165/166, `cursor/*`, `development`, or
`staging`.

Non-secret procedure: [`end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md`](./end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md).
Rollback contract (not executed here): [`end-to-end-delivery/evidence/source-release/ROLLBACK.md`](./end-to-end-delivery/evidence/source-release/ROLLBACK.md).

---

## 9. Live HOLDs (still true after this packet)

- Server01 SSH, Docker up, Tailscale mutation, public DNS/TLS.
- GSM resolve of secret **values** (names in git are OK).
- Platform SQL apply, role grants, `lautowork.server01_live_fingerprint()`.
- Live n8n activation, provider dispatch, queue drain, consumer factory writes.
- Host image IDs/digests in `deploy/prod/release-identity.json`.
- Protected merge/promotion by implementers.
- Slack/email/payments/business automations unless separately approved.

Canary: `ops/verify-server01-acceptance.sh --environment prod` is read-only in
source; `--canary` still HOLD for live binding.

---

## 10. Branch hygiene

Repository cleanup is `scripts/cleanup-merged-branches.sh --remote` (default
dry-run). It never deletes `main` / `staging` / `development`, never deletes
local worktrees, and fail-closes if preserve policy cannot be loaded.

On this writer VM, `scripts/gitops/cleanup_preserve.defaults.json` is
**missing**, so apply was refused. Precise classification:
[`end-to-end-delivery/evidence/source-release/BRANCH-CLEANUP-MANIFEST.json`](./end-to-end-delivery/evidence/source-release/BRANCH-CLEANUP-MANIFEST.json).

`cursor/*` and Dependabot refs are not cleanup-candidate forms. Open PR #128
(`dependabot/npm_and_yarn/multi-d0c2d048a7` → `main`) is kept. Issues 165 and
166 are kept.

---

## 11. What “done” means for 1.0 source vs live

| Claim | State |
|---|---|
| Pre-configuration engineering on `development` | Complete at `20f3d4cc…` |
| Source-release receipts + this agent guide | This issue line |
| Integrated `development` including this packet | Packager/controller |
| Tagged `main` candidate | Principal/controller; **absent at admission** |
| Server01 accepted | AW-08 HOLD |

Do not write “production accepted” until AW-08 evidence exists under
`docs/end-to-end-delivery/evidence/live-acceptance/` (out of this packet).
