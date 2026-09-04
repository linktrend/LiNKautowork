# ADR 0003: Autonomous Ship / Pull / Promote (Inherited via Wire)

**Status:** Accepted (Principal go-ahead 2026-07-24)
**Date:** 2026-07-24
**Timezone:** Asia/Taipei (no DST)

## Context

Agents were not consistently committing, pushing, or opening PRs into `development`. Review and merge into `development` lacked a deterministic Reviewer/Integrator path. Git promotion docs still said Principal-only for `staging` and `main`, which blocked an autonomous studio loop. Wiring a consumer to IDE Development only symlinked `.cursor` and did not install GitHub robots or Bugbot expectations.

## Decision

1. **IDE Development is the system SOT** for autonomous Git ops doctrine, managed workflow templates, Bugbot inheritance checklist, and Ship/Pull clock doctrine.
2. **Inheritance is two layers:**
   - **A.** Agent behavior via `repo/.cursor` → IDE Development `.cursor` symlink (`scripts/wire-repo.sh`).
   - **B.** GitHub robots + Bugbot checklist installed/synced from `core/github/managed-workflows/` during wire/backfill (symlink alone is not enough).
3. **IDE Development itself** runs under the same regime.
4. **Roles (deterministic):**
   - **Implementer** — long-lived agents (Remote Control preferred): commit → push → PR → `development`.
   - **Reviewer** — **Bugbot** (Cursor GitHub-side), never the implementer.
   - **Fix agent** — always a short-lived **Cloud** agent on the same branch; max **3** attempts; then stop and surface `Issues`.
   - **Integrator** — merge-only automation into `development` when CI green + Bugbot pass.
   - **Promoter** — GitHub Actions schedules.
   - **Lisa** — **primary Ship/Pull clock** (Option A): cron on Mini spawns Cursor ACP shipper/puller; Telegram one-line checkpoint status; Principal **Approve** for `staging`→`main` via Telegram.
5. **Calendar (Asia/Taipei)** — wave names are **clock times** (not A/B letters):

   | Event | Time |
   |---|---|
   | Ship 05 | 05:00 |
   | Pull 07 | 07:00 |
   | Ship 16 | 16:00 |
   | Pull 18 | 18:00 |
   | `development`→`staging` | Tue & Fri 08:00 auto |
   | `staging`→`main` | Mon 08:00 package; Principal Approve 08:30 via Lisa morning digest (Telegram reply) |

6. **Worktrees:** allowed; max **12**; max **20 GB**; delete after merge or abandon.
7. **Module 6 product Release OK / live deploy** remains Principal-gated. This ADR changes **Git branch promotion**, not product deploy authority.
8. **Studio branching default:** short-lived `issue/<id>-slug` per governed work (`/agentsetup`, `/agentcomply`); not forever `dev/*` home.

## Alternatives considered

- Keep Principal-only for all promotions — rejected; blocks autonomy.
- Separate Mini Reviewer agent — rejected; Bugbot is independent and already productized.
- Symlink-only inheritance — rejected; does not install Actions/Bugbot.
- Cursor Automations as primary Ship/Pull clock (Option B) — rejected 2026-07-25; Lisa Option A is primary; Automations optional backup only.

## Consequences

- Update `.cursor/rules/01-git-branching.mdc` and `docs/AUTONOMOUS-GIT-OPERATIONS.md`.
- Managed workflows sync on wire/backfill; consumer-specific `ci.yml` is never overwritten by sync.
- Intent/PRD wording distinguishes Git promote vs Module 6 Release OK.
- Lisa HEARTBEAT/digest gain one-line pipeline checkpoints (Telegram).
- Lisa owns Ship/Pull cron + ACP prompts in openclaw_prime; `docs/CURSOR-AUTOMATIONS-SETUP.md` reframed as backup.

## Validation / rollback

- Validation: wired repos have managed workflow files; doctrine docs resolve; promote crons match table (UTC = Taipei−8h); Lisa ship/pull cron jobs exist on Mini when awake.
- Rollback: restore prior promote YAML schedules; revert branching rule; disable Lisa ship/pull crons; leave Bugbot as-is.

---

## Amendment — 2026-07-25 (Principal locked)

**Option A:** Lisa is the Ship/Pull clock (OpenClaw cron → Cursor ACP shipper/puller on Mini). Forget Option B / Cursor Automations as primary clock.

Clarifications locked the same day:

- Times (Asia/Taipei): Ship 05 / Pull 07 / Ship 16 / Pull 18 (hour labels; morning pair advanced 2026-07-25 so 08:30 digest covers all four daily waves).
- Ship: commit → push → open/update PR → `development` → STOP (no merge/self-review).
- Pull: merge latest `origin/development` into work branches on disk; not hard-gated on all PRs merged; unfinished rolls forward.
- One repo at a time (sequential).
- Studio default: short-lived `issue/<id>-slug` (not forever `dev/*`).
- `/agentsetup` / `/agentcomply` are for **Implementers** (one repo); workspace **Orchestrators** do not get a forever session-home issue branch.
- Bugbot already ON — no human Bugbot enablement work in this amendment.
- Mini must be awake for Lisa ACP at runtime (ops prerequisite; not a code secret).

---

## Amendment — 2026-07-25 (digest 08:30 + morning Ship/Pull)

Principal locked:

- Morning digest moves **06:45 → 08:30**; email includes Pipeline (D) + Monday Main Approve when Clear; Telegram keeps Battery (C) + same Approve.
- Heartbeat at **06:45**; **no 08:45** heartbeat (digest owns that Review #1 slot).
- Morning Ship **05:00**, Pull **07:00** (evening 16/18 unchanged).
- After each Ship/Pull wave: Telegram one-liner **and** email one-liner (Clear or Issues).
- Overnight local coding **19:00–04:00** (was 19:00–07:00) so coding stops before Ship 05.

---

## Amendment — 2026-07-28 (Review Packager + promotion window)

Principal locked (IDE Development redesign):

1. **Ship = checkpoint only:** commit + push on `issue/*`. No PR. No Bugbot. EOD ~17:00 is also checkpoint-only.
2. **`review_ready`:** branch-local `.linktrend/review-ready.json` with `commitSha == HEAD`. Later commits invalidate.
3. **Review Packager:** Tuesday & Friday **08:00** Asia/Taipei (`0 0 * * 2,5` UTC). Discover eligible review-ready work → deterministic readiness → open/ready PR → Bugbot once.
4. **Staging promote:** Tuesday & Friday **10:00** Asia/Taipei (`0 2 * * 2,5` UTC). Promote only work already merged into `development`. If not ready: skip and report why. Never force. No prefer-incoming.
5. **Bugbot:** request command configurable; authoritative default exactly `@cursor review` (with the `@`). Success check remains `Linktrend Review Gate`. Hidden idempotency marker `<!-- linktrend-bugbot-requested: <sha> -->`. Normal max 2 requests per PR (initial + one after consolidated corrections). Request accounting counts only comments that contain an executable trigger (`@cursor review` or `bugbot run`) **plus** that marker; bare historical `cursor review` + marker does **not** consume the limit.
6. **Named CI gates:** `fast-gate` / `staging-gate` / `release-gate` — never “wait for every visible check.” Missing ≠ success.
7. **Integrator:** auto-merge only when non-draft → `development`, head SHA = reviewed SHA, fast-gate green, `Linktrend Review Gate` success.
8. **Review freeze:** do not modify the frozen reviewed branch; continue on another issue branch/worktree.
9. **Ship 05 / Pull 07** remain authoritative morning wave labels (not 06/08).
10. Follow-up contracts for Lisa/OpenClaw (no edits in those repos in this change): `docs/contracts/LISA-OPENCLAW-FOLLOW-UP.md`, `docs/contracts/LISA-MAIN-APPROVE-DISPATCH.md`.

---

## Amendment — 2026-07-28 (review-ready = commit status; supersedes file marker)

**Factual correction** to item 2 of the earlier 2026-07-28 amendment above (that item is obsolete and must not be followed):

1. **Authoritative review-ready mechanism:**
   - Push the completed work branch first so `HEAD == origin/<branch>`.
   - Publish successful GitHub commit status context **`Linktrend Review Ready`** on the **exact branch-tip SHA** (`scripts/mark-review-ready.sh` / `core/github/REVIEW-READY.md`).
   - A later commit becomes unready automatically (new tip SHA has no success status).
2. **There is no** `.linktrend/review-ready.json` readiness file and **no** readiness marker commit in the feature diff.
3. **Pull / freeze skip** (Lisa puller and `scripts/pull-update-work-branches.sh`):
   - Skip when the exact branch-tip SHA has successful `Linktrend Review Ready` status; **or**
   - Skip when an open review PR into `development` has head equal to that tip; **or**
   - Skip on an explicit operator freeze.
   - Do **not** use a deleted JSON-file condition.

## Amendment — 2026-07-30 (lifecycle repair control)

Factual corrections (do not rewrite earlier amendments):

1. **Staging promote** remains Tue & Fri **10:00** Asia/Taipei (not 08:00). Older calendar rows in this ADR that say staging 08:00 are obsolete.
2. **Ship / Implementer:** checkpoint = commit + push only. Implementers do **not** open PRs; Review Packager opens PRs after `Linktrend Review Ready`.
3. **Repair path:** GitHub records durable repair tasks only. **Lisa ACP Repair Dispatcher** dispatches Cursor ACP repair agents. GitHub never spawns Cursor. Max **3** attempts; no prefer-incoming. Immediate failure types do not auto-repair.
4. Contracts: `docs/contracts/AGENT-COMPLETION.md`, `docs/contracts/REPAIR-DISPATCHER.md`, `docs/contracts/ACTIONS-COST-CONTROLS.md`, `docs/contracts/LISA-LOCAL-CLEANUP-HANDOFF.md`.

## Amendment — 2026-08-02 (Phase integration delivery mode)

Principal / WP-01 locked:

1. **Delivery modes** are configurable and packaged: `issue-pr` (default, preserves existing generic Packager behavior) and `phase-integration` (opt-in). Contract: `docs/contracts/DELIVERY-MODES.md`.
2. **Phase integration:** frequent Issue checkpoint pushes (no PR); independently accepted exact Issue SHAs included on a `phase/*` branch; Review Packager opens **one** Phase PR into `development` after required accepted SHAs are included.
3. **Risk exceptions:** Issue-level PRs under `phase-integration` require an explicit risk class (`security`, `authentication`, `database_migration`, `infrastructure`, `major_shared_api`, `unusually_large_scope`, `cross_phase_impact`) via `.linktrend/issue-pr-exception.json`.
4. **Named gates** remain `fast-gate` / `staging-gate` / `release-gate` on the exact PR head SHA; missing/zero/wrong/stale/skipped-neutral are non-success.
5. **Ship remains checkpoint-only** in both modes.

## Amendment — 2026-08-17 (Phase Packager/Coordinator)

Factual correction for Update 3:

1. **Phase Packager/Coordinator** is `scripts/gitops/packager_coordinator.py`. Any authorized agent or operator may invoke it. It accepts completed remote issue commits, preserves dependency order, and creates or updates one `phase/*` branch and one draft Phase PR into `development`.
2. Retained `scripts/gitops/packager_discover.py` still discovers Review-Ready tips into ordinary draft PRs. It is **not** the Phase Packager and does not satisfy Update 3.
3. Workers remain checkpoint-only. They do not open PRs and do not wait for a nonexistent Packager path.
4. Checkpoint pushes do not start managed Fast or Full CI. Opening or updating the Phase PR starts Fast and repository-owned PR CI on the exact Phase head. Full cannot start before Fast and required CI pass.
5. The coordinator produces an exact-identity handoff for the delivery controller. A later Phase head invalidates that handoff. The coordinator cannot merge protected branches or start Full.

## Amendment — 2026-08-18 (Delivery controller)

Factual correction for Update 2:

1. **Delivery controller** is `scripts/gitops/delivery_controller.py`. Any authorized agent or operator may invoke it. It accepts an exact `phase/*` PR handoff, verifies development eligibility, merges through GitHub protection, promotes staging on reusable receipt identity without rerunning Full, prepares main, and completes main only after explicit founder approval.
2. It replaces the nonexistent Integrator merge actor. Review Ready remains a Packager discovery status and does **not** promise a merge trigger by itself.
3. Workers cannot invoke a self-merge path. The controller never pushes directly to `development`/`staging`/`main`, never bypasses branch protection, and deletes only controller-created `promote/*` branches after successful merges.
4. Behavior is identical regardless of which supported agent invokes the command; agent environment markers are ignored for decisions.

## Amendment — 2026-08-17 (Independent-review convergence)

Factual correction for Update 9:

1. **Independent-review convergence** is `scripts/gitops/independent_review_convergence.py`. It tracks one exact-head session, a durable finding ledger, and observational repair-cycle counts.
2. There is **no arbitrary terminal cycle cap**. Unattended work pauses after three review-repair cycles. Recorded founder `continue until clean` authority permits additional progressing cycles without repeated approval. `apply_repair` fails closed after that unattended pause unless that authority is recorded, and after `review_stalled` / HOLD, preserving the exact stalled head, tree, and ledger. `apply_repair` requires `touched_paths` as a nonempty list of nonempty strings and rejects a string or malformed paths before changing state.
3. Stop only for repeated unresolved findings, two no-progress cycles, repair reintroduction, redesign/new authority, infrastructure retry exhaustion, or an explicit resource limit. Same-identity severity reductions count as measurable progress. Compute units are recorded through an explicit accounting path so `maxComputeUnits` can stall truthfully. Those stops are truthful HOLD / `review_stalled` packets and cannot fabricate a clean review. `evaluate_progress` short-circuits HOLD and `review_stalled`. `ingest_review` fails closed on those stops; empty findings cannot mark pending or stalled identities corrected or emit `review_clean`.
4. Distinct nonempty fingerprints never fuzzy-merge; only wording variants of the same identity may match. First-seen findings on repair-touched paths are `introduced_by_repair` and remain blocking; first-seen findings on untouched paths are `newly_discovered_in_unchanged_scope`.
5. Review ingest requires exact `headSha` and `gitTree`, and `paths` as a nonempty list of nonempty strings. Malformed or non-object findings are `malformed_reviewer_output` with truthful HOLD and no cycle consumption. Repair cancels or invalidates any live reviewer. Implementer and reviewer actors stay separate. Reviewer silence or timeout is never clean and cannot authorize Full or repair until a valid exact-bound review transition explicitly clears the stop. A later source change invalidates prior review and Full evidence. Full never runs while HOLD or `review_stalled`.

## Amendment — 2026-08-20 (`V25_BOOTSTRAP_LEAN`)

Founder-approved Coding Execution Protocol 1.0.1 amendment `V25_BOOTSTRAP_LEAN`:

1. A v2.5 Issue checkpoint is accepted from exact pushed commit/tree, scoped diff, focused tests, one provider-independent narrow review bound to that exact identity, and manifest evidence. The review may use the ordinary routed reviewer or Principal-authorized Luna; no vendor/model is mandated. Review Ready and publisher tokens are not required.
2. No singular legacy publisher is canonical for v2.5, including `linktrend-review-ready-publisher`.
3. A failed or missing legacy publisher is `WAIVED_LEGACY_GATE`, never PASS and never an implementation failure.
4. A later exact-head administrator recovery is only a named exception after substantive replacement proof, limited to protection snapshot, restore, and readback.

## Amendment — 2026-08-20 (PKT-01 durable heartbeat, receipts, retry recovery, hosted capacity)

Founder-authorized PKT-01 follow-on to Coding Execution Protocol 1.0.1:

1. RUNNING packet mutation requires a durable heartbeat write plus matching readback bound to the checkout identity.
2. Verification receipts bind to exact checkout commit/tree; merge-ref identity is never promotable.
3. Retry exhaustion must be diagnosed before recovery; silent same-identity retry is forbidden.
4. Hosted-capacity scheduling requires a complete resource snapshot; allocator busy/exhausted is not a diagnosis until then. This amendment does not authorize paid or Fast hosted runs.

## Amendment — 2026-08-20 (PKT-01 continuous-utilization runtime)

Founder-authorized continuation of PKT-01:

1. Continuous utilization is a packaged contract: doctrine, config, schema, example, and MANIFEST surfaces plus the deterministic scheduler runtime.
2. Hosted concurrency authority is `execution-protocol`. Staged admission is up to `5 Cursor + 2 Luna`, then `10 Cursor + 4 Luna` after routing/integration verification, then `20 Cursor + 4 Luna` after another verification. Underfill is `1 Luna` in Stages 1-2 and `2 Luna` in Stage 3. Mac memory and real Cursor capacity remain binding; hourly and two-hour trigger support remains unchanged. Capacity evidence remains bound to the exact provider/runtime identity.
3. `UTILIZATION_GAP` is an event that must be repaired by recomputation, not by paid or Fast fallback.
4. Invalidation delays only the changed identity. Completion unlocks the next eligible job.

## Amendment — 2026-08-20 (PKT-05 lean Issue checkpoint and Phase recovery)

GitOps implementation of `V25_BOOTSTRAP_LEAN`:

1. Issue checkpoints are token-independent. Review Ready / `AUTOMATION_TOKEN` / Issue PR / hosted completion status are nonrequirements.
2. Legacy publisher/status outcomes are `WAIVED_LEGACY_GATE`, never PASS.
3. Phase delivery remains one protected Phase PR/gate, exact review, conditional Full, and founder gate for `main`.
4. Administrator recovery is a named exact-head exception: freeze, protection snapshot, `gh pr merge --admin --match-head-commit` first, minimum temporary exception only if needed, exact authorized merge, immediate restore/readback.
