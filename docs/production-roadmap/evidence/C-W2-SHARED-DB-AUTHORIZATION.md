# C-W2 correction A — Shared database authorization

## Outcome

The accepted `lautowork.assert_command_authorized` boundary in migration `20260804_000001` now consumes the request context that PostgREST actually supplies: JSON from `request.jwt.claims` and `request.headers`. The signed JWT `org_id`, JWT role, request `x-link-org-id`, and target row organisation must agree. Accepted runtime roles are `service_role` and `svc_lautowork_runtime`; absent or mismatched context fails closed.

Migration `20260804_000002` no longer installs a second authorization implementation or prepares claim state for callers. Its RPCs call the shared boundary directly, consistently with the RPCs in migrations `20260804_000003` and `20260804_000004`. No `000003` or `000004` business function was changed for this correction.

The older dotted-setting test context remains available only when `lautowork.test_context = 'on'`. That flag is enabled only in the disposable `automation_contracts` database bootstrap so SQL-level fixtures can remain deterministic; production migrations do not enable it.

## Real PostgREST proof

The disposable database stack now starts PostgREST `v12.2.8`. `postgrest-verify.sh` signs real HS256 JWT bearer tokens and sends them through HTTP with the project API key and `x-link-org-id` header.

Representative RPC calls prove the shared boundary across the three migration packets:

- `20260804_000002`: `linkautowork_resolve_bound_instance`
- `20260804_000003`: `linkautowork_librarian_get_control`
- `20260804_000004`: `linkautowork_active_pause`

Matching scoped JWT, header, and target organisation succeed. Cross-organisation JWT/body disagreement, header disagreement, and an unauthorized JWT role are rejected through the same live PostgREST path. This proof does not rely on manually setting dotted PostgreSQL session settings.

## Validation

- `npm --prefix packages/automation-contracts run verify:db` — PASS, including Wave 2 runtime corrections, concurrent idempotency, WP-08 durable operations, real PostgREST scoped-JWT authorization, restore, and rollback verification.
- `npm run ci` — PASS: 81 gateway tests, all package and librarian suites, real PostgREST authorization in both disposable database rehearsals, smoke and full n8n evaluations, restore verification, and every TypeScript check.
- `git diff --check` — PASS.

No live database, deployment, secret, commit, push, or external system was changed.
