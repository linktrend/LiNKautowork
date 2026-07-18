-- ============================================================================
-- Provision the isolated n8n schema + its dedicated role, per ADR 0001
-- Decision 3 and the Consequences open item:
--   "provision the empty lautowork_n8n schema + svc_lautowork_n8n role and
--    repoint DB_POSTGRESDB_SCHEMA off the _dev/_prod split, as a separate
--    operational step under the two-project topology."
--
-- Authority: docs/adr/0001-adopt-shared-platform-org-model.md (Decision 3).
-- Companion to: 20260715_000001_lautowork_control_core.sql (the control/ledger
-- schema). That migration deliberately did NOT create anything for n8n; this
-- one does the small, isolated provisioning it deferred.
--
-- Scope is deliberately tiny and does NOT create any tables. n8n manages its
-- own internal schema automatically: on first boot against a Postgres
-- connection string it runs its own migrations and creates its own tables
-- (workflow definitions, executions, credentials, settings, migration
-- bookkeeping) inside whatever schema DB_POSTGRESDB_SCHEMA points at. Our job
-- (ADR 0001 Decision 3) is to hand n8n an isolated schema + a dedicated role,
-- then get out of the way -- never to hand-design n8n's tables.
--
-- Environment separation note (ADR 0001 Decision 2 / Decision 3): under the
-- shared two-project topology (linkplatform-stage vs linkplatform-prod), env
-- separation lives at the Supabase-PROJECT level, not the schema level. So
-- there is a single `lautowork_n8n` schema per project -- NOT the old
-- `lautowork_n8n_dev` / `lautowork_n8n_prod` schema-name suffixes in one
-- project. n8n should be pointed at `lautowork_n8n` in whichever project is the
-- current target.
--
-- Prerequisite: none beyond a Postgres database. This migration does not depend
-- on the platform schema or the lautowork control schema -- it is a standalone
-- isolation boundary.

-- migrate:up

create schema if not exists lautowork_n8n;

comment on schema lautowork_n8n is
  'n8n''s own internal runtime schema, owned and managed by n8n itself on boot '
  '(it runs its own migrations and creates/alters its own tables here). '
  'LiNKautowork never hand-designs tables here and its own control role must '
  'NEVER be granted access to this schema. This is a hard isolation boundary, '
  'not cosmetic (ADR 0001 Decision 3): (1) upstream-controlled and '
  'version-volatile -- n8n''s internal schema is defined and migrated by '
  'upstream n8n and changes across releases; (2) least-privilege separation -- '
  'n8n''s role owns/DDLs this schema and LiNKautowork''s control role must not '
  'touch it, nor vice versa; (3) audit integrity vs. n8n release cadence -- the '
  'lautowork control/ledger must not be coupled to or migrate-able alongside '
  'n8n''s operational churn.';

-- Dedicated least-privilege role for n8n. This is the ONE schema in this whole
-- system where a broad grant to a single dedicated role is correct: n8n owns
-- and DDLs its own tables on boot, so its role legitimately needs CREATE (DDL)
-- rights over this isolated schema -- unlike every other least-privilege role
-- in this codebase (e.g. svc_lautowork_runtime, svc_observer), which gets
-- narrow DML-only grants on the lautowork control schema. The broad grant is
-- safe precisely because the schema is fully isolated.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'svc_lautowork_n8n') then
    create role svc_lautowork_n8n nologin;
  end if;
end $$;

-- Hard isolation boundary. `revoke all ... from public` closes the default
-- PUBLIC grant so no other role gets in by default. svc_lautowork_runtime
-- (LiNKautowork's own control role) and svc_observer are DELIBERATELY NOT
-- granted anything on this schema: LiNKautowork's own code/role must never be
-- able to read or write n8n's internal tables, full stop. Only svc_lautowork_n8n
-- (n8n itself) may touch this schema.
revoke all on schema lautowork_n8n from public;
grant all privileges on schema lautowork_n8n to svc_lautowork_n8n;

do $$
begin
  execute 'alter role svc_lautowork_n8n set search_path = lautowork_n8n,public';
end $$;

-- verification: the schema and the role both exist. No tables to count here --
-- n8n creates its own on boot -- so this checks existence rather than counting
-- relations (cf. the schema+relation count select in the sibling
-- 20260715_000001_lautowork_control_core.sql migration).
select nspname as schema_name
from pg_namespace
where nspname = 'lautowork_n8n';

select rolname as role_name, rolcanlogin as can_login
from pg_roles
where rolname = 'svc_lautowork_n8n';

-- ============================================================================
-- migrate:down -- DO NOT paste this section into a SQL Editor when applying
-- the migration above. It DROPS n8n's entire schema (and would take n8n's own
-- tables with it via cascade). It exists only for the migration tool to strip
-- automatically. A stray `drop schema ... cascade` pasted alongside the create
-- has caused confusion before -- do not run it by hand.
-- ============================================================================
drop schema if exists lautowork_n8n cascade;
