-- ============================================================================
-- Persist kill-switch and lifecycle transitions to lautowork (Principal
-- decision 8A, 2026-07-18). Tables already exist from
-- 20260715_000001_lautowork_control_core.sql; this migration adds the
-- write + hydrate RPCs the gateway needs so emergency brakes survive
-- process restarts.
-- ============================================================================

-- migrate:up

create or replace function public.linkautowork_write_killswitch_event(
  tenant_id uuid,
  scope text,
  action text,
  incident_id text,
  reason text,
  metadata jsonb default '{}'::jsonb
)
returns void
language plpgsql
security definer
set search_path = lautowork, public
as $$
begin
  if scope not in ('global', 'scoped') then
    raise exception 'invalid killswitch scope: %', scope;
  end if;
  if action not in ('activate', 'release') then
    raise exception 'invalid killswitch action: %', action;
  end if;

  insert into lautowork.killswitch_events (
    org_id,
    scope,
    action,
    incident_id,
    reason,
    metadata
  ) values (
    tenant_id,
    scope,
    action,
    incident_id,
    reason,
    coalesce(metadata, '{}'::jsonb)
  );
end;
$$;

create or replace function public.linkautowork_write_lifecycle_transition(
  tenant_id uuid,
  workflow_id text,
  from_state text,
  to_state text,
  protected_action boolean,
  approvals jsonb,
  reason text
)
returns void
language plpgsql
security definer
set search_path = lautowork, public
as $$
begin
  insert into lautowork.lifecycle_transitions (
    org_id,
    workflow_id,
    from_state,
    to_state,
    protected_action,
    approvals,
    reason
  ) values (
    tenant_id,
    workflow_id,
    from_state,
    to_state,
    coalesce(protected_action, false),
    coalesce(approvals, '{}'::jsonb),
    reason
  );
end;
$$;

-- Reconstruct currently-active kill switches from the append-only event log.
-- Latest event per scope key wins; only 'activate' rows are returned.
create or replace function public.linkautowork_active_killswitches()
returns jsonb
language plpgsql
security definer
set search_path = lautowork, public
as $$
declare
  result jsonb := '[]'::jsonb;
  global_row lautowork.killswitch_events%rowtype;
  r record;
begin
  select *
  into global_row
  from lautowork.killswitch_events
  where scope = 'global'
  order by created_at desc, id desc
  limit 1;

  if found and global_row.action = 'activate' then
    result := result || jsonb_build_array(
      jsonb_build_object(
        'scope', 'global',
        'reason', global_row.reason,
        'incident_id', global_row.incident_id,
        'org_id', global_row.org_id,
        'activated_at', global_row.created_at,
        'metadata', global_row.metadata
      )
    );
  end if;

  for r in
    select distinct on ((metadata->>'workflow_id'))
      *
    from lautowork.killswitch_events
    where scope = 'scoped'
      and coalesce(metadata->>'workflow_id', '') <> ''
    order by (metadata->>'workflow_id'), created_at desc, id desc
  loop
    if r.action = 'activate' then
      result := result || jsonb_build_array(
        jsonb_build_object(
          'scope', 'scoped',
          'workflow_id', r.metadata->>'workflow_id',
          'reason', r.reason,
          'incident_id', r.incident_id,
          'org_id', r.org_id,
          'activated_at', r.created_at,
          'metadata', r.metadata
        )
      );
    end if;
  end loop;

  return result;
end;
$$;

grant execute on function public.linkautowork_write_killswitch_event(uuid, text, text, text, text, jsonb)
  to svc_lautowork_runtime;
grant execute on function public.linkautowork_write_lifecycle_transition(uuid, text, text, text, boolean, jsonb, text)
  to svc_lautowork_runtime;
grant execute on function public.linkautowork_active_killswitches()
  to svc_lautowork_runtime;

comment on function public.linkautowork_write_killswitch_event(uuid, text, text, text, text, jsonb) is
  'Append-only kill-switch event writer. Wire param tenant_id maps to org_id.';
comment on function public.linkautowork_write_lifecycle_transition(uuid, text, text, text, boolean, jsonb, text) is
  'Append-only lifecycle transition writer. Wire param tenant_id maps to org_id.';
comment on function public.linkautowork_active_killswitches() is
  'Returns JSON array of currently active kill switches reconstructed from the event log.';
