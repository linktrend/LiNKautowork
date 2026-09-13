# Server01 migration recovery contract

Platform alone backs up, isolated-restores, applies and receipts this package.

## Fresh install

1. Confirm empty or compatible `platform` prerequisite.
2. Apply the sixteen ordered SQL files in `MIGRATION-PACKAGE.json`.
3. Require `lautowork.server01_package_status() = 'complete'`.
4. Record live fingerprint from `lautowork.server01_live_fingerprint()`.
5. Stop on `partial` or `drift`. Do not continue to runtime.

## Upgrade (predecessor Autowork schema already present)

1. Backup the target project.
2. Isolated-restore the backup to a disposable database and apply only `20260910_000001_lautowork_server01_live_interfaces.sql`.
3. Prove fingerprint and verification SQL.
4. Apply the same file to the intended project only after that proof.
5. Never re-run a non-idempotent subset of the file after a partial failure; use restore or a new forward-fix migration.

## Partial apply

`server01_package_control.apply_state = 'started'` or a relation count other than 7 is **partial**. Stop. Restore from the pre-apply backup or apply a reviewed forward-fix migration. Do not call `migrate:down` on stage/production.

## Rollback / forward-fix

- Environments with operational rows: **forward-fix only**. Preserve invocation, intent, callback, receipt and audit history.
- `migrate:down` in `20260910_000001_lautowork_server01_live_interfaces.sql` is disposable pre-production only. It drops Server01 relations and the four new nologin roles. It must never run against stage or production.

## Live fingerprint

After a complete apply, persist `lautowork.server01_live_fingerprint()`. A later mismatch is `drift`: stop automation, restore or forward-fix, and issue a Platform receipt. Autowork workers must not apply SQL themselves.

## HOLD

No live Platform backup, restore, or application receipt is claimed by this source package.
