# Autonomous Git Operations

**Status:** Active (Principal go-ahead 2026-07-24; Option A clock locked 2026-07-25; Review Packager redesign 2026-07-28; portable managed-core v2 Wave 1 2026-08-01)
**ADR:** `docs/adr/0003-autonomous-ship-pull-promote.md` · `docs/adr/0004-portable-managed-core-v2.md`
**Timezone:** Asia/Taipei
**SOT home:** This repo (IDE Development) is the system source. Installed consumers inherit Layer A (physical managed agent surfaces) and Layer B (managed GitHub workflows + Bugbot checklist). IDE Development itself is **not** a consumer rollout entry.

## Two-layer inheritance

| Layer | What | How |
|---|---|---|
| **A. Agent behavior** | Rules, skills, ship/pull checklists | Portable installer (`scripts/ide-development.py`) materialises physical `.ide-development/` + Cursor/Codex adapters inside the consumer. No consumer-to-system `.cursor` symlink. |
| **B. Robots** | Managed `.github/workflows/*` + Bugbot enablement checklist | Installer / sync paths from `core/github/managed-workflows/`; does **not** overwrite consumer `ci.yml` |

Protection of `development`, `staging`, and `main` is required managed-system behavior for every installed repository (`docs/contracts/REPOSITORY-PROTECTION.md`). Live apply is dry-run-gated and external to packaged secrets.

IDE Development uses the same managed workflows for **self-verification** of the system repository. Consumer rollout order and Principal approval gates live in `docs/GITOPS-CONSUMER-ROLLOUT.md`.

## Roles

| Role | Who | Job |
|---|---|---|
| Implementer | Long-lived local / Remote Control / Cloud agents | Branch → checkpoint commit/push → mark `review_ready` when finished |
| Review Packager | GitHub Action (`linktrend-review-packager.yml`) | Tue/Fri 08:00: discover review-ready → open PR → request Bugbot once |
| Reviewer | **Bugbot** | Review PRs into `development` (pass = GitHub check `Cursor Bugbot` → `success`) |
| Repair (Lisa ACP) | GitHub records failure task; **Lisa ACP Repair Dispatcher** dispatches Cursor ACP | Repair CI/Bugbot/ordinary conflicts; max **3** attempts; no prefer-incoming; immediate types do not auto-repair; new SHA re-enters packaging |
| Integrator | GitHub Action (`linktrend-integrator-merge.yml`) | Merge into `development` when **fast-gate** + `Cursor Bugbot` success + head SHA = reviewed SHA |
| Promoter | GitHub Actions schedules | Tue/Fri **10:00** staging; Mon main package |
| Lisa | OpenClaw / Telegram (**primary Ship/Pull clock**) | Cron → spawn Cursor ACP shipper/puller on Mini; one-line checkpoint status; ask Principal to Approve main |
| Principal | Carlos | Approve `staging`→`main` (Mon 08:30 via digest; reply on Telegram); intervene on `Issues` |

## Primary clock — Lisa Option A (locked)

**Lisa is the Ship/Pull clock.** She runs OpenClaw cron on the Mac Mini and spawns Cursor ACP agents (shipper / puller). Cursor Automations are **not** the primary clock (optional backup only — see `docs/CURSOR-AUTOMATIONS-SETUP.md`).

| Event | Local time | Who fires | Behavior |
|---|---|---|---|
| Ship 05 | 05:00 | Lisa cron → Cursor ACP shipper | One repo at a time: **checkpoint** = commit + push on work branch → **STOP**. No PR. No Bugbot. |
| Pull 07 | 07:00 | Lisa cron → Cursor ACP puller | Merge latest `origin/development` into unfinished work branches; **skip frozen reviewed SHAs**; unfinished rolls forward |
| Review Packager | Tue & Fri **08:00** | GitHub (`0 0 * * 2,5` UTC) | **Discover:** ready commit-status tips → draft PRs only (no Bugbot, no serial CI wait). **Evaluate** (PR/check): readiness + fast-gate on exact head → ready → `@cursor review` once |
| Staging promote | Tue & Fri **10:00** | GitHub (`0 2 * * 2,5` UTC) | Promote only what is already safely in `development`. If not ready: **skip and report why**. Never force. |
| Ship 16 | 16:00 | Lisa cron → Cursor ACP shipper | Same as Ship 05 (checkpoint only) |
| Pull 18 | 18:00 | Lisa cron → Cursor ACP puller | Same as Pull 07 |
| EOD checkpoint | ~17:00 | Agent / operator | Checkpoint commit+push only — not a review request |
| Main package | Mon 08:00 | GitHub Promoter (`0 0 * * 1` UTC) | Package only; do **not** merge yet |
| Morning digest | 08:30 | Lisa cron | Email + Telegram day-ahead; Pipeline lines; Mon Main Approve ask when Clear |
| Main Approve | Mon 08:30 | Lisa digest (Telegram reply) | Principal says Approve → Lisa dispatches merge for **exact SHA** |

**Why Packager 08:00 / Staging 10:00:** Pull 07 finishes first; review, CI, integration, and possible repair get a two-hour window. At 10:00 promote only work already merged into `development`. Anything still under review or repair waits for the next window.

**Runtime prerequisite (human/ops):** Mini must be awake (Keep Awake / Remote Control) so Lisa ACP can spawn. Documented in openclaw_prime Lisa ship/pull clock procedure.

**Repo order (Ship/Pull sequential — Principal-locked 2026-07-25; `LiNKtrading-codebase` added with portable v2):** process exactly one repo at a time, in this order (skip missing paths).

This is the **Ship/Pull processing order** for Lisa Option A. It is **not** the consumer install/rollout order. IDE Development appears first as the **system source** (checkpoints / self-verification) and is **not** a portable-install consumer. Locked consumer install order starts at `openclaw_prime`, includes `LiNKtrading-codebase`, and excludes IDE Development — see `docs/GITOPS-CONSUMER-ROLLOUT.md`.

1. IDE Development *(system source — not a consumer install target)*
2. openclaw_prime
3. LiNKplatform
4. LiNKskills
5. LiNKbrain
6. LiNKsites
7. LiNKdeveloper
8. LiNKlibraries
9. LiNKautowork
10. LiNKtrading-codebase

ACP prompts and absolute paths: openclaw_prime `linkbots/lisa/Personality files/agents/ship-pull-clock.md` (follow-up contract for Ship checkpoint-only wording: `docs/contracts/LISA-OPENCLAW-FOLLOW-UP.md`).

## Studio branching default (locked)

- Prefer short-lived **`issue/<id>-slug`** per governed work (not forever `dev/*` home).
- `cursor/*` for cloud/dashboard agents.
- `dev/<machine><ide>` rare ad-hoc only.
- Bootstrap: `/agentsetup`. Already-open migration: `/agentcomply`.
- **Implementer vs Orchestrator:** `/agentsetup` and `/agentcomply` are for **Implementers** that own work in **one repo**. A workspace **Orchestrator** must not be forced onto a random/stolen `issue/*` as “session home.”
- **Branch rule (any agent):** no code/repo touch → no branch required. The moment any agent touches a repo, run `/agentsetup` or `/agentcomply` for **that** repo and use `issue/<id>-slug` for the work package.

## Checkpoints vs review-ready

| Action | When | Opens PR? | Bugbot? |
|---|---|---|---|
| Checkpoint | Ship waves, EOD, anytime | No | No |
| Mark review-ready | Issue finished + proof + evidence; normal-token publisher posts status | No (agent) | No (agent) |
| Review Packager | Tue/Fri 08:00 | Yes | Yes, once per SHA |
| Urgent package | `workflow_dispatch` on packager | Yes | Yes, once per SHA |

Record: GitHub commit status context `Linktrend Review Ready` on the exact tip SHA — see `core/github/REVIEW-READY.md`.

**Production publish path:** normal GitHub automation token only, via trusted `workflow_dispatch` on `linktrend-review-ready-publisher.yml` (default-branch workflow source; issue branch is data only). Local `scripts/gitops/completion_gate.py review-ready` validates first and fails closed with normal-token route diagnostics when privileged credentials are unavailable. Carlos's restricted user identity must not publish this status.

Helpers: `scripts/mark-review-ready.sh` (compatibility wrapper → gate), `scripts/validate-review-ready.sh`, `scripts/clear-review-ready.sh` (fail-closed withdraw helper; normal-token `action=withdraw` dispatch when local normal automation credentials are unavailable).
Do **not** create or use `.linktrend/review-ready.json`.
Bugbot mention-only: `docs/contracts/BUGBOT-MENTION-ONLY.md` (required before consumer rollout).
Completion contract: `docs/contracts/AGENT-COMPLETION.md`.

## Delivery modes

Configurable modes are defined in `docs/contracts/DELIVERY-MODES.md`:

| Mode | Behavior |
|---|---|
| `issue-pr` (default) | Review Packager may open one draft PR per review-ready work branch into `development` (existing generic behavior). |
| `phase-integration` | Issue checkpoints stay PR-less. Independently accepted Issue SHAs feed a `phase/*` branch. Packager opens **one Phase PR** into `development`. Issue-level PRs require an explicit risk classification (`.linktrend/issue-pr-exception.json`). |

Checkpoint pushes never open a PR and never request Bugbot. Named gates still evaluate the **exact** PR head SHA.

## Bugbot contract

- Success check name remains exactly **`Cursor Bugbot`**.
- Request command is **configurable**; authoritative default is exactly: `@cursor review` (with the `@`).
- Idempotent hidden marker: `<!-- linktrend-bugbot-requested: <sha> -->`.
- **Request accounting** (2-request limit): count only comments that contain an **executable** trigger (`@cursor review` or `bugbot run`) **and** the `<!-- linktrend-bugbot-requested: <sha> -->` marker. Bare historical `cursor review` + marker does **not** consume the limit.
- A new functional commit invalidates the previous reviewed SHA and marker.
- Normal maximum: one initial Bugbot request + one after a consolidated correction batch.

## Named CI gates

Do **not** wait for every visible GitHub check. Use named contracts in `core/github/CI-GATE-CONTRACTS.md`:

- `fast-gate` — before Bugbot packaging readiness / Integrator merge
- `staging-gate` — development→staging
- `release-gate` — staging→main Approve merge

Missing required checks are **not** success.

## Integrator auto-merge (development)

Merge only when all are true:

1. Non-draft open PR into `development`
2. Head SHA equals reviewed SHA from Bugbot marker
3. `fast-gate` required checks = success
4. `Cursor Bugbot` = success
5. Not `conflict_blocked`

## Staging promotion

- Tue/Fri **10:00** Asia/Taipei
- Build temporary `promote/staging/<sha>` from staging tip; merge development; open PR into staging
- **staging-gate** must pass on the **combined promotion PR head**
- Merge only that PR — **never** direct-push staging
- No prefer-incoming; on conflict → `conflict_blocked` durable repair task + skip
- If not ready at 10:00 → skip safely and report why

## Main promotion

- Mon 08:00 package: temporary `promote/main/<sha>` PR into main
- Principal Approve binds **staging SHA**, **prior main SHA**, and **promote PR head SHA**
- **release-gate** on the combined promote PR head; merge only that PR — **never** direct-push main
- Authoritative Main Approve **package store**: GitHub `promote/main/*` PR marker + discover CLI — `docs/contracts/LISA-MAIN-APPROVE-DISPATCH.md`

## Conflict recovery

1. Pause the item (`conflict_blocked`)
2. Repair on a branch (never auto-prefer either side)
3. New SHA → re-mark review-ready → re-enter Packager
4. Max **3** repair attempts, then `Issues`

## Pull rules

- Update unfinished work from `origin/development`
- Skip when the exact branch-tip SHA has successful commit status **`Linktrend Review Ready`**, or an open review PR into `development` whose head equals that tip, or an explicit operator freeze
- Do **not** use `.linktrend/review-ready.json` (must not be used)
- Continue other work on another issue branch or worktree during freeze

## Cleanup

After **safe merge only**: delete merged issue branches / worktrees. Never delete by name alone.

## Lisa one-line statuses (Telegram + Ship/Pull email)

Clock labels use **local hour** (Asia/Taipei), not A/B letters:

- `Ship 05: Clear` / `Ship 05: Issues`
- `Pull 07: Clear` / `Pull 07: Issues`
- `Ship 16: Clear` / `Ship 16: Issues`
- `Pull 18: Clear` / `Pull 18: Issues`
- `Review Packager (Tue|Fri): Clear|Issues`
- `Staging promote (Tue|Fri): Clear|Issues`
- `Main ready (Mon): Clear|Issues`

No lists or links in those lines. Detail stays in `memory/pipeline-status.md` (Lisa workspace) for when Carlos asks.

## Implementer checklist (every session + Ship waves)

1. Prefer Remote Control for long-lived agents; Mini awake + Keep Awake (required for Lisa ACP clock).
2. Start from latest `development` (Pull waves enforce sync).
3. Work on **`issue/*`** by default.
4. Commit with conventional commits; **push often (checkpoints)**.
5. When finished: push clean tip → `completion_gate.py write-evidence` → `completion_gate.py review-ready` (or normal-token publisher dispatch if local publish fails closed); do **not** open PR yourself (Packager does); do **not** write `.linktrend/review-ready.json`.
6. Do **not** self-merge; do **not** promote to `staging`/`main`.
7. Do **not** review your own PR (Bugbot is Reviewer).
8. During review freeze: continue only on another issue branch/worktree.

## Fix path

On CI red or Bugbot fail: GitHub records a durable repair task (`docs/contracts/REPAIR-DISPATCHER.md`). **Lisa ACP Repair Dispatcher** dispatches a Cursor ACP repair agent on that branch (GitHub never spawns Cursor; not “send back to original implementer”). Consolidate corrections, then at most one additional Bugbot request. After 3 failed attempts: escalate to Issues; Lisa one-liner `Issues`; no force-merge; no prefer-incoming.

## Worktrees

Allowed. Caps: **12** worktrees, **20 GB** total Cursor-managed. Delete after merge or abandon.

## Module 6 vs Git promote

- **Git promote** (`development`→`staging`→`main`): this document + ADR 0003.
- **Product live deploy / Module 6 Release OK:** still Principal-gated; unchanged by this system.

## Related paths

- Rules: `.cursor/rules/linktrend-git-branching.mdc`, `.cursor/rules/02-autonomous-ship-pull.mdc` (system source also keeps `.cursor/rules/01-git-branching.mdc` as local mirror; consumers install `linktrend-git-branching.mdc`)
- Skills/commands: `/agentsetup`, `/agentcomply`
- Review-ready: `core/github/REVIEW-READY.md` (normal-token publisher + rollback)
- Completion: `docs/contracts/AGENT-COMPLETION.md`
- CI gates: `core/github/CI-GATE-CONTRACTS.md`
- Managed workflows: `core/github/managed-workflows/`
- Managed runtime (v2 payloads): `core/github/managed-runtime/`
- Wire/sync: `scripts/wire-repo.sh`, `scripts/sync-managed-workflows.sh`
- Bugbot checklist: `core/checklists/BUGBOT-INHERITANCE.md`
- Cursor Automations (optional backup): `docs/CURSOR-AUTOMATIONS-SETUP.md`
- Lisa contracts: `docs/contracts/LISA-OPENCLAW-FOLLOW-UP.md`, `docs/contracts/LISA-MAIN-APPROVE-DISPATCH.md`
- Consumer rollout: `docs/GITOPS-CONSUMER-ROLLOUT.md`
- normal automation credentials (ops only): `docs/contracts/GITHUB-APP-GITOPS-CREDENTIALS.md`
