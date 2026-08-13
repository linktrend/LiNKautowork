# Delivery modes (managed-core GitOps)

**Status:** Binding for managed-core packaging and Review Packager / Integrator behavior.
**Package:** IDE Development managed-core (consumer-installable doctrine + scripts).
**Related:** `docs/AUTONOMOUS-GIT-OPERATIONS.md`, `docs/adr/0003-autonomous-ship-pull-promote.md`, `docs/adr/0005-streamlined-delivery-coordinator.md`, `docs/contracts/STREAMLINED-DELIVERY.md`, `core/github/CI-GATE-CONTRACTS.md`, `docs/contracts/AGENT-COMPLETION.md`.
**Schema:** `core/managed-core/schemas/delivery-modes.schema.json`

## Purpose

Define **configurable generic delivery modes** for how independently accepted Issue work enters `development`. Modes are product-agnostic. Consumers select a mode; they do not invent product-specific GitOps.

## Modes

| Mode id | Default? | Integration shape |
|---|---|---|
| `issue-pr` | **Yes** (preserve existing generic behavior) | Each review-ready work branch may receive its own draft PR into `development` (current Packager discover behavior). |
| `phase-integration` | Opt-in via config | Frequent Issue **checkpoints** (commit+push only). Independently accepted exact Issue SHAs are included on a **Phase branch**. Packager opens **one Phase PR** into `development` for that Phase head. |

Checkpoint pushes **never** open a PR and **never** request Bugbot, in either mode.

## Phase integration lifecycle

1. **Issue checkpoint:** Implementer commits and pushes on `issue/<id>-<slug>`. No PR. No Bugbot.
2. **Independent Issue acceptance:** Exact tip SHA receives successful `Linktrend Review Ready` (or equivalent acceptance record). Later commits invalidate acceptance for the new tip.
3. **Phase inclusion:** Accepted Issue SHAs are merged/cherry-picked onto `phase/<slug>` (or another configured Phase branch prefix). Machine-readable Phase records list each accepted Issue SHA and prove inclusion (committed at `.linktrend/phase-delivery-record.json` on the Phase tip).
4. **Phase PR:** After all required accepted Issue SHAs are included, the Phase tip is marked review-ready through the same trusted completion / normal-token publisher path used for Issue tips (exact SHA; configured `phase/<slug>` is publisher-eligible without weakening `issue/<number>-<slug>` safeguards). Review Packager opens **one** draft PR only after validating that Phase delivery record and inclusion evidence: `phase/*` → `development`.
5. **Named gates:** `fast-gate` (then Bugbot when required), Integrator merge, `staging-gate`, and `release-gate` evaluate the **exact PR head SHA**. Missing, empty/zero SHA, wrong SHA, stale event head, skipped/neutral (unless explicitly allowed), or failed checks are **non-success**.

## Risk-based Issue PR exceptions

Under `phase-integration`, an Issue-level PR into `development` is allowed **only** when an explicit risk classification is declared:

- `security`
- `authentication`
- `database_migration`
- `infrastructure`
- `major_shared_api`
- `unusually_large_scope`
- `cross_phase_impact`

Declare the exception with a committed file on the Issue tip:

```json
{
  "schemaVersion": 1,
  "riskClass": "security",
  "reason": "short human-readable justification"
}
```

Path: `.linktrend/issue-pr-exception.json`

Without a valid exception, Packager must **not** open an Issue PR in `phase-integration` mode even when the tip is review-ready (acceptance still stands for Phase inclusion).

Under `issue-pr` mode, risk exceptions are unused; normal Packager Issue PR behavior remains.

## Machine-readable Phase record

Authorized integration tooling writes / updates a Phase delivery record (fixture and live outputs) with at least:

| Field | Meaning |
|---|---|
| `deliveryMode` | `phase-integration` |
| `phaseBranch` | Phase branch name |
| `baseSha` | Integration base (usually `development` tip at Phase open) |
| `headSha` | Exact Phase tip SHA under review |
| `mergeSha` | Merge commit SHA after Integrator merge, else `null` |
| `phasePr` | `{ number, url, base }` when a Phase PR exists |
| `acceptedIssues[]` | `{ branch, sha, accepted, included }` for each required Issue |
| `namedGateEvidence` | Gate id, exact SHA, status, per-check outcomes |
| `riskExceptionIssuePrs[]` | Optional Issue PRs opened under explicit risk classes |

Path on the Phase tip: `.linktrend/phase-delivery-record.json`

Schema: `core/managed-core/schemas/delivery-modes.schema.json` (`phaseDeliveryRecord`).

Packager discovery **must** load and validate this record (branch, `headSha`, and `phase_ready_for_pr` inclusion evidence) before opening a Phase PR.

## Configuration

Repository config file (optional): `.github/linktrend-delivery-mode.json`

```json
{
  "schemaVersion": 1,
  "deliveryMode": "phase-integration",
  "phaseBranchPrefix": "phase/"
}
```

Environment override (tests / automation): `LINKTREND_DELIVERY_MODE=issue-pr|phase-integration`.

When unset, default is **`issue-pr`** so existing consumers keep current behavior.

For a new v2 local-coordinator consumer, version 2 may add bounded fast/full/
release profiles, dependency files, attempt/revision limits, resource limits,
and `mainPromotion`. The complete version-2 shape and validation rules are
frozen in `docs/planning/streamlined-delivery/FROZEN-INTERFACES.md` and the
packaged `delivery-runtime.schema.json`. Recommended new-install values are
`deliveryMode=phase-integration`, `orchestrationMode=local-coordinator`, two
fast jobs, one heavy job, a 300-second fast target, two attempts, two sealed
revisions, automatic staging, and principal-approved main.

`phaseBranchPrefix` is shared by Packager discovery (`is_allowed_work_branch`) and required branch-source CI policy (`scripts/gitops/work-branch-allowlist.sh` / `branch-source-policy.yml`). A custom prefix (for example `wave/`) must be allowlisted consistently in both places.

## Named gates (unchanged ids)

Gate ids remain `fast-gate`, `staging-gate`, and `release-gate`. Application-specific CI job names map to those ids via repository variables. Consumer-owned CI workflows are never overwritten by managed sync.

Exact-SHA fail-closed rules apply equally to Issue PRs and Phase PRs.

## Non-goals

- Not a live checkout/symlink dependency for consumers.
- Not mandatory Bugbot on checkpoints.
- Not GitHub Issues as an operational database.
- Not consumer rollout or live GitHub settings mutation by the packaging agent.
