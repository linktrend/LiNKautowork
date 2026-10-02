# WP-04 — Automation Control Data Model

## Objective

Add the `lautowork` database contracts needed for definitions, immutable releases, instances, explicit system bindings, product offerings, provisioning, deployments, secret references, eval evidence, and append-only operational history.

## Dependencies

WP-01 identity and lifecycle contracts. LiNKplatform foundation migration is a prerequisite, but no live application is authorized.

## Owned paths

- New dated files under `supabase/migrations/**`
- `packages/automation-contracts/**`
- Disposable database test fixtures/harness
- `docs/contracts/**` and migration manifest/evidence

Do not modify LiNKplatform migrations or apply anything to stage/production.

## Required records

- `automation_definitions`
- `automation_releases`
- `automation_sources`
- `automation_products`
- `automation_instances`
- `automation_bindings`
- `automation_secret_bindings` containing references/health only
- `provisioning_requests` and `provisioning_steps`
- `automation_deployments`
- `automation_executions` and append-only execution events
- `automation_eval_runs` and results
- `automation_health_snapshots`
- `automation_alerts`, incidents, and maintenance cases
- `automation_improvement_candidates`
- `approval_requests` and append-only decisions
- append-only domain audit events

## Security requirements

1. Use `org_id` referencing `platform.organizations` for all organisation-scoped records.
2. Do not introduce a second tenant/organisation authority.
3. Enforce same-organisation instance/binding/provisioning references.
4. Certified releases are immutable; mutations create a new release.
5. Secret tables reject value-like columns and persist only GSM references, purpose, state, expiry, rotation metadata, and scope.
6. Enable RLS on private schema tables as defense in depth and define actual operation-specific policies.
7. Any `SECURITY DEFINER` function has fixed `search_path`, internal authorization checks where applicable, revoked `PUBLIC` execution, and explicit grants to named service roles.
8. Append-only evidence rejects update/delete for runtime roles.
9. Provide safe RPCs/commands for state transitions rather than broad table mutation.

## Tests

- Disposable Postgres migration up verification.
- Foreign-key and check-constraint matrix.
- Cross-org read/write denial.
- Binding to other-org instance denial.
- Certified-release mutation denial.
- Passing eval requirement for certification.
- Deprecated/retired release cannot provision.
- Secret-value-shaped payload rejection at contract layer.
- Append-only update/delete denial.
- Function privilege inspection proves no unintended `PUBLIC` execution.

## Acceptance criteria

- Migrations are additive and preserve existing MVO tables and RPCs.
- TypeScript/Zod contracts match SQL fields and lifecycle states.
- A migration manifest records prerequisites, hashes, verification SQL, forward-fix/rollback strategy, and LiNKplatform review/application ownership.
- No stage/prod database connection is required for CI.
- Supabase current breaking changes relevant to Data API exposure and privileged functions are documented in the packet evidence.

## Stop conditions

Stop rather than edit shared Platform objects, weaken RLS for convenience, expose service-role keys, or apply migrations live.
