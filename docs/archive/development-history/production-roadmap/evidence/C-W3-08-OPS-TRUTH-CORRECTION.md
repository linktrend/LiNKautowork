# C-W3-08 operations truth and disposable-resource correction

Date: 2026-08-04 14:14 Asia/Taipei
Scope: release-job safety, required operations scheduling, current-surface legacy retirement, and disposable Docker ownership only.

## Corrected behaviour

- `certified-package-publisher` now runs a no-network, fail-closed preflight by default. It validates the package catalogue and accepts only already-certified packages. Import and activation require an explicit `--activate`, an exact `stage` or `prod` environment, an approved-target identifier, a release-window authorisation reference, and generated runtime `N8N_BASE_URL`/`N8N_API_KEY` values. It imports inactive first and performs the one explicit activation patch only after those checks.
- Production Compose exposes the publisher as a release profile and the authenticated monitor/maintenance scheduler as the required `operations` profile. The current operations runbook gives guarded commands for both; neither command is a pre-VPS instruction.
- The authoritative supported-surface scanner now covers root instructions, Open Issues, application/runtime/deploy/ops/script trees, and GitHub workflows. Retired runtime names are absent from those surfaces. The two obsolete promotion workflows whose reusable upstream was retired were removed rather than leaving an unusable runtime reference.
- Disposable evaluator containers and volumes are labelled. Disposable contracts/browser backing services and their default network carry explicit LiNKautowork labels. Reconciliation selects only those labels, never uses Docker prune, and has a narrow, verified one-time list for historic crash leftovers.

## Local validation

```text
bash -n ops/publish-certified-packages.sh ops/reconcile-disposable-eval-resources.sh ops/run-operations-scheduler.sh
ops/publish-certified-packages.sh --environment stage --dry-run
ops/publish-certified-packages.sh --environment prod --package missing@1 --dry-run   # correctly rejects
ops/reconcile-disposable-eval-resources.sh
npm run release:check
docker compose -f deploy/prod/docker-compose.yml --env-file deploy/prod/.env.example config
docker compose -f packages/automation-contracts/disposable-db/docker-compose.yml config
npm --prefix packages/automation-eval-runner run test
git diff --check
```

All passed. Compose's names-only preflight warns that `SUPABASE_DB_PASSWORD` and `N8N_ENCRYPTION_KEY` have no values, which is expected: their real values must be generated outside Git for an authorised environment.

## Verified crash cleanup

Read-only checks confirmed no attached containers and zero attached network containers. The correction then removed only these exact unused historic resources:

- volumes `linkautowork-wp06-probe` and `linkautowork-wp06-probe2`
- networks `linkautowork-contracts-db-64479_default` and `linkautowork-contracts-db-69480_default`

No broad prune, external target, secret, migration, package activation, or live deployment was performed.
