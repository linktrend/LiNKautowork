-- LiNKautowork Phase 1 (MVO) baseline schema
-- Single Supabase project with strict schema separation by environment and control plane.

create schema if not exists n8n_dev;
create schema if not exists n8n_prod;
create schema if not exists linkautowork_audit;
create schema if not exists linkautowork_control;

create table if not exists linkautowork_audit.audit_runs (
  id bigserial primary key,
  tenant_id uuid not null,
  run_id text not null,
  task_id text not null,
  dpr_id text not null,
  status text not null,
  token_usage integer not null default 0,
  command_log jsonb not null default '{}'::jsonb,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_audit_runs_tenant_created_at
  on linkautowork_audit.audit_runs (tenant_id, created_at desc);

alter table linkautowork_audit.audit_runs enable row level security;

-- Read policy for control-plane/reporting roles that include tenant claim.
do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'linkautowork_audit'
      and tablename = 'audit_runs'
      and policyname = 'audit_runs_tenant_read'
  ) then
    create policy audit_runs_tenant_read
      on linkautowork_audit.audit_runs
      for select
      using (
        tenant_id::text = coalesce(current_setting('request.jwt.claim.tenant_id', true), '')
      );
  end if;
end
$$;

-- RPC-only writes. Direct INSERT is not granted to app roles by default.
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
set search_path = public, linkautowork_audit
as $$
begin
  insert into linkautowork_audit.audit_runs (
    tenant_id,
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

create table if not exists linkautowork_control.lifecycle_transitions (
  id bigserial primary key,
  tenant_id uuid not null,
  workflow_id text not null,
  from_state text not null,
  to_state text not null,
  protected_action boolean not null default false,
  approvals jsonb not null,
  reason text not null,
  created_at timestamptz not null default now()
);

create table if not exists linkautowork_control.killswitch_events (
  id bigserial primary key,
  tenant_id uuid not null,
  scope text not null,
  action text not null,
  incident_id text not null,
  reason text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

comment on schema n8n_dev is 'n8n runtime schema for dev environment';
comment on schema n8n_prod is 'n8n runtime schema for prod environment';
comment on table linkautowork_audit.audit_runs is 'Canonical execution telemetry log for LiNKautowork';
