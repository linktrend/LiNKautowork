-- ============================================================================
-- Confirmed by the Principal (2026-07-15): the VPS running the n8n container
-- referenced below was destroyed, and the Supabase project it and
-- ops/sql/001_mvo_schema.sql pointed at is the same old, abandoned project
-- LiNKsites was told to disregard when starting fresh on linkplatform-stage/
-- -prod. No live data exists anywhere for LiNKautowork's control schema.
-- This is therefore a fresh CREATE, promoted from DRAFT to a real dated
-- migration, exactly as LiNKsites' 20260715_000001_lsites_sites_core.sql was
-- once its own dormancy was confirmed.
-- ============================================================================
--
-- Authority: docs/adr/0001-adopt-shared-platform-org-model.md (Decisions 1-3).
-- Supersedes (once promoted+applied): ops/sql/001_mvo_schema.sql, which will be
-- archived per docs/DOCUMENTATION_GOVERNANCE.md (archive before delete).
--
-- What this migration does, relative to the current ops/sql/001_mvo_schema.sql:
--   1. Consolidates the two control schemas (linkautowork_audit +
--      linkautowork_control) into ONE spec-compliant `lautowork` schema
--      (shared-foundation-spec.md §3: one control/ledger schema per Program).
--   2. Replaces the bare `tenant_id uuid` (which referenced nothing) on every
--      control/ledger table with `org_id uuid references
--      platform.organizations(id)` -- the shared tenant identity from
--      LiNKplatform (spec §4). These are flat, independent ledger tables with
--      no parent, so org_id lands on each directly (ADR Decision 1) -- the same
--      shape as platform.capability_grants / platform.handoff_envelopes, not a
--      parent/child hierarchy like LiNKsites' sites->pages.
--   3. Adds real RLS to every table: each policy OR's LiNKautowork's existing
--      JWT tenant-claim fast-path with a real platform.has_org_access() check
--      (either passing is sufficient -- a widening of who's allowed in, mirroring
--      LiNKsites' 20260715_000001_lsites_sites_core.sql).
--   4. Keeps the exposed RPC public.linkautowork_write_audit_run (preserving the
--      gateway env contract SUPABASE_AUDIT_RPC) but repoints its search_path to
--      the new `lautowork` schema and writes into org_id. Its wire parameter
--      keeps the name `tenant_id` for gateway compat (see ADR open item).
--
-- This migration deliberately does NOT create n8n's schema/tables/role. n8n
-- manages its own internal tables on boot against its connection string; the
-- isolated `lautowork_n8n` schema + dedicated `svc_lautowork_n8n` role are a
-- separate operational provisioning step (ADR Decision 3), not this file.
--
-- Prerequisite: LiNKplatform/supabase/migrations/20260714_000001_
-- platform_foundation.sql must already be applied to the same database
-- (creates the platform schema and platform.has_org_access()).

-- migrate:up

create schema if not exists lautowork;

create table if not exists lautowork.audit_runs (
  id bigserial primary key,
  org_id uuid references platform.organizations(id),
  run_id text not null,
  task_id text not null,
  dpr_id text not null,
  status text not null,
  token_usage integer not null default 0,
  command_log jsonb not null default '{}'::jsonb,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

comment on column lautowork.audit_runs.org_id is
  'FK to platform.organizations(id) in the shared linkplatform-stage/-prod '
  'project. Replaces the old bare tenant_id uuid. Nullable until every existing '
  'row is backfilled (none confirmed to exist yet -- see ADR 0001 Finding).';

create index if not exists idx_lautowork_audit_runs_org_created_at
  on lautowork.audit_runs (org_id, created_at desc);

create table if not exists lautowork.lifecycle_transitions (
  id bigserial primary key,
  org_id uuid references platform.organizations(id),
  workflow_id text not null,
  from_state text not null,
  to_state text not null,
  protected_action boolean not null default false,
  approvals jsonb not null,
  reason text not null,
  created_at timestamptz not null default now()
);

comment on column lautowork.lifecycle_transitions.workflow_id is
  'Free-text template id today (automations/templates/*.json). See ADR 0001 '
  'open question re: a future lautowork.managed_automations registry this could '
  'become an FK to.';

create index if not exists idx_lautowork_lifecycle_transitions_org
  on lautowork.lifecycle_transitions (org_id, created_at desc);

create table if not exists lautowork.killswitch_events (
  id bigserial primary key,
  org_id uuid references platform.organizations(id),
  scope text not null,
  action text not null,
  incident_id text not null,
  reason text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_lautowork_killswitch_events_org
  on lautowork.killswitch_events (org_id, created_at desc);

-- RPC-only write path for audit runs. Kept in `public` (spec §3 allows public
-- to hold functions/views meant to be exposed) and keeps its published name so
-- the deployed gateway's SUPABASE_AUDIT_RPC contract is unaffected. Wire param
-- stays `tenant_id` for gateway compat; it is written into the org_id column.
create or replace function public.linkautowork_write_audit_run(
  tenant_id uuid,
  run_id text,
  task_id text,
  dpr_id text,
  status text,
  token_usage integer,
  command_log jsonb,
  details jsonb,
  created_at timestamptz default now()
)
returns void
language plpgsql
security definer
set search_path = lautowork, public
as $$
begin
  insert into lautowork.audit_runs (
    org_id,
    run_id,
    task_id,
    dpr_id,
    status,
    token_usage,
    command_log,
    details,
    created_at
  ) values (
    tenant_id,
    run_id,
    task_id,
    dpr_id,
    status,
    token_usage,
    coalesce(command_log, '{}'::jsonb),
    coalesce(details, '{}'::jsonb),
    coalesce(created_at, now())
  );
end;
$$;

-- Least-privilege runtime roles, matching the platform_foundation.sql and
-- lsites_sites_core.sql pattern (nologin service roles, guarded creation).
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'svc_lautowork_runtime') then
    create role svc_lautowork_runtime nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'svc_observer') then
    create role svc_observer nologin;
  end if;
end $$;

revoke all on schema lautowork from public;
grant usage on schema lautowork to svc_lautowork_runtime, svc_observer;
grant select on all tables in schema lautowork to svc_observer;
grant select, insert, update, delete on all tables in schema lautowork to svc_lautowork_runtime;
grant usage, select on all sequences in schema lautowork to svc_lautowork_runtime;
alter default privileges in schema lautowork grant select on tables to svc_observer;
alter default privileges in schema lautowork grant select, insert, update, delete on tables to svc_lautowork_runtime;
grant execute on function platform.has_org_access(uuid, platform.member_role) to svc_lautowork_runtime;
grant execute on function public.linkautowork_write_audit_run(uuid, text, text, text, text, integer, jsonb, jsonb, timestamptz) to svc_lautowork_runtime;

do $$
begin
  execute 'alter role svc_lautowork_runtime set search_path = lautowork,public';
end $$;

-- RLS: all three tables now carry org_id directly and have an identical policy
-- shape, so generate the policies once via a foreach loop (matching the loop
-- style in LiNKsites' 20260715_000001_lsites_sites_core.sql) instead of
-- hand-repeating. Each policy OR's LiNKautowork's existing JWT tenant-claim
-- fast-path with a real platform.has_org_access() membership check; either
-- passing is sufficient (Postgres RLS policies are OR'd).
do $$
declare
  t text;
  tenant_tables text[] := array[
    'audit_runs', 'lifecycle_transitions', 'killswitch_events'
  ];
begin
  foreach t in array tenant_tables loop
    execute format('alter table lautowork.%I enable row level security', t);
    execute format('drop policy if exists lautowork_%s_access on lautowork.%I', t, t);
    execute format(
      'create policy lautowork_%s_access on lautowork.%I ' ||
      'for all to svc_lautowork_runtime ' ||
      'using (org_id::text = current_setting(''request.jwt.claim.tenant_id'', true) ' ||
      'or org_id is null ' ||
      'or platform.has_org_access(org_id, ''client_viewer'')) ' ||
      'with check (org_id::text = current_setting(''request.jwt.claim.tenant_id'', true) ' ||
      'or org_id is null ' ||
      'or platform.has_org_access(org_id, ''client_viewer''))',
      t, t
    );
  end loop;
end $$;

comment on schema lautowork is
  'LiNKautowork control/ledger schema (shared-foundation-spec.md §3). n8n''s '
  'own runtime tables live in the logically-isolated lautowork_n8n schema, '
  'created and managed by n8n itself -- never here (ADR 0001 Decision 3).';
comment on table lautowork.audit_runs is
  'Canonical execution telemetry log for LiNKautowork, org-scoped via '
  'platform.organizations.';

-- verification
select n.nspname as schema_name, count(*) as tables
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'lautowork' and c.relkind = 'r'
group by n.nspname;

-- ============================================================================
-- migrate:down -- DO NOT paste this section into a SQL Editor when applying
-- the migration above. It undoes everything created by this file. It exists
-- only for the migration tool to strip automatically.
-- ============================================================================
drop function if exists public.linkautowork_write_audit_run(uuid, text, text, text, text, integer, jsonb, jsonb, timestamptz);
drop schema if exists lautowork cascade;
