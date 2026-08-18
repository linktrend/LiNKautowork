# Named CI gate contracts

**Audience:** Review Packager, Integrator, Staging/Main promotion, agents, CI maintainers.
**Status:** Binding for IDE Development GitOps redesign.
**Related:** `docs/adr/0003-autonomous-ship-pull-promote.md`, `core/github/REVIEW-READY.md`, `docs/contracts/DELIVERY-MODES.md`.

---

## Why named gates exist

Workflows must **not** wait for “every visible GitHub check.” That pattern is fragile (renamed checks, optional jobs, third-party noise). Instead, each lifecycle stage waits only on a **named gate contract**.

Missing required checks are **failure / not-ready**, never success. Empty/zero SHA, wrong SHA relative to the PR head, stale event heads, and skipped/neutral conclusions (unless a gate explicitly allows them) are also **non-success**.

Phase PRs (`phase/*` → `development`) and Issue PRs use the same gate ids and exact-SHA fail-closed rules.

---

## Gate names

| Gate | Used by | Purpose |
|------|---------|---------|
| `fast-gate` | Review Packager (before Bugbot), Integrator (before merge to `development`) | Deterministic PR validation that must pass before human/Bugbot review or auto-merge. |
| `staging-gate` | Development → Staging promotion | Validates the promotion candidate before staging advances. |
| `release-gate` | Staging → Main merge (Approve path) | Validates the exact release SHA before main advances. |

Check conclusion names that satisfy each gate are defined below for **this** repository. Consumer repos map their own job names to the same gate ids when they adopt the managed workflows.

---

## IDE Development mappings

### `fast-gate`

All of the following must conclude **success** on the PR head SHA (when the workflow exists and is required for that event):

| Check name (GitHub check / workflow job display) | Source workflow display name |
|--------------------------------------------------|------------------------------|
| `Verify IDE Development` | `CI` (`.github/workflows/ci.yml`) |
| `Linktrend Branch Source Policy` | `Linktrend Branch Source Policy` (`.github/workflows/branch-source-policy.yml`) |

Packager and Integrator must list **both** workflow display names under `workflow_run.workflows`. Completion of either workflow reevaluates the exact PR/head; Bugbot/merge proceeds only when **every** named fast-gate check is success on that SHA.

### `staging-gate`

For development→staging **promotion PRs** from temporary `promote/staging/*` branches:

| Check name | Source |
|------------|--------|
| `Verify IDE Development` | Must be **success on the promotion PR head** (combined staging candidate), not merely on `development` alone |

### `release-gate`

For staging→main **promotion PRs** from temporary `promote/main/*` branches (Approve path):

| Check name | Source |
|------------|--------|
| `Verify IDE Development` | Must be **success on the promotion PR head** (combined main candidate), not merely on `staging` alone |

Prior green results on source branches are **not** proof of the combined promotion.

---

## Bugbot success check (separate from gates)

| Check name | Meaning |
|------------|---------|
| `Linktrend Review Gate` | Required Bugbot success conclusion for Integrator auto-merge. |

Bugbot is **not** part of `fast-gate`. Deterministic gates run first; Bugbot is requested only after `fast-gate` is green (or after Review Packager has confirmed deterministic readiness).

---

## Integrator decision matrix (summary)

Auto-merge to `development` only when **all** are true:

1. PR is into `development`, non-draft, open.
2. Head SHA equals the recorded reviewed SHA (Bugbot marker / review-ready association).
3. `fast-gate` all required checks = success.
4. `Linktrend Review Gate` = success for that head SHA.
5. No `conflict_blocked` / mergeability conflict.
6. Within conflict-repair budget (see conflict recovery).

Otherwise: leave open, comment why, or wait.

---

## Consumer adoption

When syncing managed workflows into a consumer:

1. Keep gate **ids** (`fast-gate`, `staging-gate`, `release-gate`) stable.
2. Replace IDE check names with that repo’s primary verify workflow job names via repository variables:
   - `LINKTREND_INTEGRATOR_REQUIRED_CHECKS` (fast-gate check names, comma-separated)
   - `LINKTREND_STAGING_GATE_CHECKS`
   - `LINKTREND_RELEASE_GATE_CHECKS`
3. **`workflow_run.workflows` is STATIC YAML** and cannot be driven by repository variables. For each consumer, substitute or generate the managed workflow so the list contains **every** GitHub Actions workflow **display name** that produces a configured named gate check. IDE Development lists `CI` and `Branch Source Policy`.
4. Document the mapping in the consumer’s `docs/` or workflow comments.
5. Never invent “wait for all checks” as a shortcut.
6. Configure the normal-token credential contract (`docs/contracts/GITHUB-APP-GITOPS-CREDENTIALS.md`) before claiming autonomy. Resolve and consume the normal automation token in the **same trusted job**; never via job outputs.
7. Do **not** roll out until this corrected system is on the default branch, smoke-tested, and Bugbot `manualTriggerOnly` is confirmed.

Optional / informational checks that must **not** block `fast-gate`:

- Docs-only or advisory workflows not listed in the gate tables
- `Linktrend Review Gate` (separate success check — see Bugbot contract)
- Unrelated third-party checks not in the gate tables

Missing required checks are **not ready** (missing ≠ success).

---

## Wake paths (Actions vs external checks)

| Event | Used for |
|-------|----------|
| `pull_request_target` | Initial evaluate on trusted workflow definition (scripts from default branch) |
| `workflow_run` (every gate-producing workflow, e.g. `CI` + `Branch Source Policy`) | Reevaluate when GitHub Actions gates finish (Actions does not emit usable `check_run` workflow events for its own suites) |
| `check_run` (non-`github-actions`) | External apps such as Linktrend Review Gate |
| `schedule` / `workflow_dispatch` | Discovery / promote build windows |

Privileged jobs always check out `github.event.repository.default_branch` with `persist-credentials: false`. Ordinary testing of proposed code remains in unprivileged `ci.yml` (`contents: read`).

---

## Change control

Changing required check names is a **contract change**: update this file, tests that assert the names, and any workflow `env` lists **and** static `workflow_run.workflows` lists in the same PR.

## Aggregate repository CI gate (Update 7)

Branch protection must require the stable managed aggregate context
`Linktrend Repository CI Gate` rather than an unconditional raw application-Full
context. See `docs/contracts/REPOSITORY-CI-TRIGGER.md` and
`scripts/gitops/repository_ci_contract.py`.
