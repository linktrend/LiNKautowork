# WP-04 Automation Control Migration Manifest

Status: implemented locally; not applied to Supabase stage or production.

## Purpose

`20260804_000001_lautowork_automation_control_model.sql` adds the LiNKautowork-owned records needed to operate Golden Automation Packages after WP-01: definitions, immutable releases, sources, products, org-scoped instances and bindings, secret references, provisioning, deployments, execution/evaluation evidence, health/alerts/incidents/maintenance, improvement candidates, approvals, and domain audit evidence.

It is additive. It does not alter existing MVO tables/RPCs, `platform.*`, or n8n's `lautowork_n8n` schema.

## Prerequisites and ownership

| Prerequisite | Owner | Required before a live apply |
|---|---|---|
| `platform.organizations` and `platform.has_org_access(uuid, platform.member_role)` | LiNKplatform | Yes; Platform must review and sequence application. |
| `20260715_000001_lautowork_control_core.sql` | LiNKautowork | Yes. |
| `20260718_000001_lautowork_control_persistence.sql` | LiNKautowork | Yes. |
| WP-01 Golden Automation Package v0.1 | LiNKautowork | Frozen contract consumed by release fields/states. |

LiNKautowork authors this migration. LiNKplatform alone reviews, sequences, applies, and operates shared stage/production migrations. This packet has no authority to connect to or change either project.

## Files and hashes

| File | SHA-256 |
|---|---|
| `supabase/migrations/20260804_000001_lautowork_automation_control_model.sql` | `99d9812362e4569aefcacd4a753f60768864d13849b0ed954c0cfaeb662ff941` |
| `packages/automation-contracts/src/index.ts` | `7f42600c83f362c33650de41678bb65277dd2a3d8fff9750fd9a2132b3fb1679` |
| `packages/automation-contracts/disposable-db/verify.sql` | `88d42b704e81f3cafa7c10b93545fd2e0de7beabd80e01ebb7fae8fbf5c6aabe` |
| `packages/automation-contracts/disposable-db/rollback-verify.sql` | `ecf78fcd75eab264912a177891977b36dec25b36bbbce57320343caf296edf89` |

Any modification requires recalculating this table and rerunning the disposable verification.

## Security design

- Every organisation-scoped record has `org_id` and an FK to `platform.organizations(id)`.
- Composite `(id, org_id)` foreign keys prevent a referenced record from silently crossing organisation boundaries. Additional lineage triggers prove that an instance's definition/release/product, a provisioning request's release, a deployment's instance/release/digests, and an execution's instance/release/deployment all describe the same automation.
- Packages/releases use WP-01 lifecycle values. Release content is immutable; only narrowly defined lifecycle moves are possible through privileged commands.
- Certification requires an independent, passed evaluation whose package/workflow digest and n8n version match the release exactly.
- `automation_secret_bindings` has references/health metadata only. It contains no JSON/metadata escape hatch and no raw value column. SQL and package contracts reject secret-shaped keys, private keys, common opaque-token prefixes, connection-string URLs with userinfo, and Bearer credential values.
- Private `lautowork` tables have RLS enabled and forced. Read policies use the canonical `request.jwt.claim.org_id`; the legacy `tenant_id` claim is not an authority fallback. A service request remains scoped to that canonical organisation.
- The four new `SECURITY DEFINER` RPCs fix `search_path`, revoke `PUBLIC` execution, and have explicit `svc_lautowork_runtime` grants. Each derives the target organisation from the addressed release, execution, or approval record, checks that the supplied `p_org_id` agrees only as a consistency guard, then requires canonical-org membership or trusted service authority. Caller-supplied `p_org_id` is never an authorisation grant.
- Sources, execution events, evaluation results, health snapshots, incident/maintenance events, approval decisions, and domain audit events are append-only via reject-update/delete triggers.

The database is a defence-in-depth boundary; it does not substitute for the future gateway/API authorization work in WP-05 and WP-09.

## Verification SQL and disposable harness

Run only in a disposable Docker PostgreSQL database:

```bash
npm --prefix packages/automation-contracts run verify:db
```

The harness creates a minimal local `platform` prerequisite, applies the **up** portion of the existing migrations plus this migration, then proves:

1. a hash-matching independent passing evaluation certifies an `eval_pending` release;
2. canonical-org RLS hides another organisation's rows and a legacy tenant claim alone grants no access;
3. each privileged RPC rejects an organisation-A request attempting to operate an organisation-B release, execution, or approval;
4. composite FKs and lineage triggers reject cross-org and same-org-but-different-automation binding, instance, provisioning, deployment, and execution combinations;
5. secret-shaped configuration is rejected, including connection-string URLs and Bearer values;
6. release content cannot be mutated after creation, retired releases cannot be provisioned, and append-only execution evidence cannot be updated;
7. privileged RPCs have no `PUBLIC EXECUTE` grant;
8. the disposable down section removes tables, privileged RPCs, and trigger helpers, then passes a post-rollback assertion.

It destroys the local container volume on completion. It has no Supabase URL, service-role key, GSM access, or production credential.

## Forward fix and rollback

Use forward fixes for any environment that has operational evidence. A new migration must repair data while preserving release, execution, incident, approval, and audit history.

The `migrate:down` section is for a disposable pre-production test database only. It drops the new tables, privileged public RPCs, and trigger helpers and necessarily discards operational history; it must never be used against stage or production. The disposable harness now executes and verifies this path after its forward verification.

Before a live migration, LiNKplatform must provide a review result covering existing schema state, role mapping, Data API exposure, backup, restore, migration order, and rollback/forward-fix procedure.

## Supabase compatibility note

This private schema is not intentionally exposed through the Supabase Data API. If a future API exposes any table, access grants and RLS policies must be reviewed together; RLS is not a replacement for controlling schema/API exposure. The implementation uses explicit `TO` roles, a `USING` predicate for reads, no public grants on privileged functions, and fixed `search_path` for `SECURITY DEFINER` functions. The current Supabase RLS guidance was checked during WP-04 preparation; production application must re-check current Supabase release notes and advisors at that time.
