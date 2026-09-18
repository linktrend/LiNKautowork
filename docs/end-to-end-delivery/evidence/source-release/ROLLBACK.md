# Source rollback contract (not executed)

This packet did not deploy, switch release pointers, or apply SQL.

## Application rollback (AW-08, after a live install)

1. Stop new invocations (scoped or global kill switch — live call remains HOLD).
2. Retarget `/srv/linktrend/deploy/linkautowork/current` to
   `/srv/linktrend/deploy/linkautowork/previous`.
3. Start that predecessor Compose definition.
4. Preserve logs, audit IDs, n8n export, and backups. Do not delete evidence rows.

Layout from `docs/runbooks/OPERATIONS.md` and `ops/deploy-stack.sh`:

- `/srv/linktrend/deploy/linkautowork/releases/<commit>`
- `/srv/linktrend/deploy/linkautowork/current`
- `/srv/linktrend/deploy/linkautowork/previous`
- `/srv/linktrend/runtime/linkautowork/*.env.runtime` mode `0600`

## Data / migration rollback

Platform alone backs up, isolated-restores, applies, and receipts
`lautowork.server01.migration-identity/1.0.0`.

- Operational rows: **forward-fix only**.
- `migrate:down` in `20260910_000001_lautowork_server01_live_interfaces.sql`
  is disposable pre-production only and must never run against stage/production.
- Stop on `partial` or `drift`. Autowork workers must not apply SQL.

## Stale tag

Do not roll **forward** onto `v1.0.0` peeled `7e76a5e77306d42cdcfd4fd59f22473235c7e7fc`.
That tag is older than the 1.0 engineering candidate.

## This checkpoint

If the evidence commit is rejected, abandon this issue-branch tip. Do not
reset unknown work or rewrite protected refs. A new identity is required
for any later source change. This packet did not retag, promote, or delete
remote branches.
