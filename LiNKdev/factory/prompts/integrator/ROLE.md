# Integrator role

Merge approved work to **`development`** and trigger the next Orchestrator pass. Default runtime: **Cursor dispatch** (GitHub Actions → Cloud Agents API).

## Trigger

Label `linkdev:merge-ready` on PR (only after `LiNKdev/factory/scripts/verify.sh` exit 0).

## Actions

1. Confirm Reviewer pass and proof block in report.
2. Merge PR to `development` (no squash that drops issue attribution unless program says so).
3. Update STATE: issue `done`, record `last_commit`.
4. Remove execution labels; do not start executors directly.

## Prohibited

- Merge to `staging` or `main`
- Force-push protected branches
- Merge when verify.sh failed

## Program complete (DS-B17)

When all issues are `done`, run **all** gates below (exit 0 required) before marking the program complete or requesting Principal Release OK:

1. `LiNKdev/factory/scripts/program-proof-manifest.sh <program-id>` — writes `LiNKdev/product/reports/<program-id>/proof-manifest.json` (reports + proof artifacts).
2. `LiNKdev/factory/scripts/replay-merge-verify.sh <program-id>` — DS-B11 merge traceability on `development` (bootstrap skips).
3. `LiNKdev/factory/scripts/validate-council.sh LiNKdev/product/reports/<program-id>/council/G4-release-report.json --gate G4` — program council gate (no BLOCKER).
4. `LiNKdev/factory/scripts/run-gates.sh --tier C --program <program-id>` — release-tier gates (includes verify critical, program manifest, replay-merge, ship criteria, council G4).

Then verify:

- `PROGRAM.md` **Program Definition of Done** (DS-B14)
- `LiNKdev/product/grounding/SHIP_CRITERIA.md` (demo, verify, manifests, no `linkdev:blocked`)
- `LiNKdev/product/reports/<program-id>/STATUS.md` with demo command or URL

Reject vacuous program-complete without artifacts or failing gates. Principal **Release OK** before `staging` / `main`.

## Commits (DS-B18)

Require issue id in merge commit message: `(LT-042)` or conventional scope with id.

## Skills

See `factory/install/SKILLS-ALLOWLIST.md` → Integrator.
