-- AW-02: additive durable provider plane. Source-only; no live application is implied.
-- migrate:up
create table if not exists lautowork.provider_requests (
  id uuid primary key, org_id uuid not null references platform.organizations(id) on delete restrict,
  contract_version text not null check (char_length(contract_version) between 1 and 64),
  automation_id text not null check (automation_id !~ '(issue|ledger|gate|order|filing|service|privilege)'),
  automation_version text not null, definition_digest text not null check (definition_digest ~ '^sha256:[a-f0-9]{64}$'),
  configuration_digest text not null check (configuration_digest ~ '^sha256:[a-f0-9]{64}$'), configuration_ref text not null check (char_length(configuration_ref) <= 512),
  idempotency_key text not null check (char_length(idempotency_key) between 16 and 160),
  request_fingerprint text not null check (request_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  operation_kind text not null check (operation_kind in ('status_collection','precheck','evidence_collection','notification_delivery','external_assistance','artifact_transform','media_package','outreach_adapter')),
  state text not null check (state in ('accepted','queued','running','succeeded','failed','expired','cancelled','timed_out','rejected','blocked','quarantined','unavailable','contract_incompatible')),
  expected_version integer not null default 1 check (expected_version > 0), expires_at timestamptz not null,
  correlation_ref text not null check (char_length(correlation_ref) <= 512), handoff_ref text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique (org_id, idempotency_key)
);
create table if not exists lautowork.provider_attempts (
  id uuid primary key default gen_random_uuid(), request_id uuid not null references lautowork.provider_requests(id) on delete restrict,
  attempt_number integer not null check (attempt_number > 0), state text not null, job_retry boolean not null default false,
  outbox_retry boolean not null default false, dlq_at timestamptz, uncertain_outcome boolean not null default false,
  safe_error_category text, created_at timestamptz not null default now(), unique(request_id, attempt_number)
);
create table if not exists lautowork.provider_receipts (
  id uuid primary key, request_id uuid not null unique references lautowork.provider_requests(id) on delete restrict,
  org_id uuid not null references platform.organizations(id), state text not null, attempt_count integer not null default 0,
  evidence_ref text, result_ref text, created_at timestamptz not null default now(), immutable_at timestamptz not null default now()
);
create table if not exists lautowork.provider_events (
  event_id uuid primary key, org_id uuid not null references platform.organizations(id), source_ref text not null,
  cursor text not null, event_type text not null check (event_type in ('request','attempt','receipt','notification')), correlation_refs jsonb not null default '[]'::jsonb, payload_ref text not null, payload_digest text not null check (payload_digest ~ '^sha256:[a-f0-9]{64}$'), occurred_at timestamptz not null, unique(org_id, source_ref, cursor)
);
create table if not exists lautowork.provider_callbacks (
  request_id uuid primary key references lautowork.provider_requests(id) on delete restrict,
  org_id uuid not null references platform.organizations(id) on delete restrict,
  receipt_id uuid not null references lautowork.provider_receipts(id) on delete restrict,
  callback_binding_ref text not null, source_timestamp timestamptz not null, created_at timestamptz not null default now()
);
create table if not exists lautowork.provider_outbox (
  id uuid primary key default gen_random_uuid(), org_id uuid not null references platform.organizations(id), request_id uuid references lautowork.provider_requests(id),
  kind text not null check (kind in ('event_delivery','notification_delivery')), state text not null default 'pending' check (state in ('pending','delivered','failed','dlq')),
  payload_ref text not null, attempt_count integer not null default 0, available_at timestamptz not null default now(), created_at timestamptz not null default now()
);
create table if not exists lautowork.provider_kill_switches (
  id uuid primary key default gen_random_uuid(), org_id uuid not null references platform.organizations(id), automation_id text,
  active boolean not null, reason_ref text not null, created_at timestamptz not null default now()
);
create index if not exists idx_provider_requests_org_state on lautowork.provider_requests(org_id, state, created_at);
create index if not exists idx_provider_outbox_pending on lautowork.provider_outbox(org_id, available_at) where state='pending';
alter table lautowork.provider_requests enable row level security;
alter table lautowork.provider_attempts enable row level security;
alter table lautowork.provider_receipts enable row level security;
alter table lautowork.provider_events enable row level security;
alter table lautowork.provider_outbox enable row level security;
alter table lautowork.provider_kill_switches enable row level security;
alter table lautowork.provider_callbacks enable row level security;
do $$ declare t text; begin foreach t in array array['provider_requests','provider_receipts','provider_events','provider_outbox','provider_kill_switches'] loop
 execute format('create policy %I on lautowork.%I for all to svc_lautowork_runtime using (org_id::text=current_setting(''request.jwt.claim.org_id'',true)) with check (org_id::text=current_setting(''request.jwt.claim.org_id'',true))', 'provider_'||t||'_org',t); end loop;
create policy provider_attempts_org on lautowork.provider_attempts for all to svc_lautowork_runtime using (exists(select 1 from lautowork.provider_requests r where r.id=request_id and r.org_id::text=current_setting('request.jwt.claim.org_id',true))) with check (exists(select 1 from lautowork.provider_requests r where r.id=request_id and r.org_id::text=current_setting('request.jwt.claim.org_id',true)));
create policy provider_callbacks_org on lautowork.provider_callbacks for all to svc_lautowork_runtime using (org_id::text=current_setting('request.jwt.claim.org_id',true)) with check (org_id::text=current_setting('request.jwt.claim.org_id',true));
end $$;
-- Provider-plane RPCs preserve the runtime JWT/RLS authority; they never use SECURITY DEFINER.
create or replace function lautowork.linkautowork_provider_accept(p_request jsonb,p_request_fingerprint text)
returns jsonb language plpgsql security invoker set search_path = lautowork, pg_temp as $$
declare v_org uuid; v_existing lautowork.provider_requests%rowtype; v_request lautowork.provider_requests%rowtype;
begin
  v_org := (p_request->'platform'->>'org_id')::uuid;
  if v_org::text is distinct from current_setting('request.jwt.claim.org_id', true) then raise exception 'provider organisation context mismatch' using errcode='42501'; end if;
  if exists(select 1 from lautowork.provider_kill_switches k where k.org_id=v_org and k.active and (k.automation_id is null or k.automation_id=p_request->'automation'->>'automation_id')) then raise exception 'provider kill switch active' using errcode='55000'; end if;
  select * into v_existing from lautowork.provider_requests where org_id=v_org and idempotency_key=p_request->>'idempotency_key' for update;
  if found then
    if v_existing.request_fingerprint <> p_request_fingerprint then raise exception 'provider idempotency conflict' using errcode='23505'; end if;
    return jsonb_build_object('record',to_jsonb(v_existing),'replay',true);
  end if;
  insert into lautowork.provider_requests(id,org_id,contract_version,automation_id,automation_version,definition_digest,configuration_digest,configuration_ref,idempotency_key,request_fingerprint,operation_kind,state,expires_at,correlation_ref,handoff_ref)
  values ((p_request->>'request_id')::uuid,v_org,p_request->>'contract_version',p_request->'automation'->>'automation_id',p_request->'automation'->>'version',p_request->'automation'->>'definition_digest',p_request->'automation'->'configuration_ref'->>'digest',p_request->'automation'->'configuration_ref'->>'ref',p_request->>'idempotency_key',p_request_fingerprint,p_request->>'operation_kind','accepted',(p_request->>'expires_at')::timestamptz,p_request->'correlation_refs'->0->>'ref',p_request->'brain_handoff_ref'->>'ref') returning * into v_request;
  return jsonb_build_object('record',to_jsonb(v_request),'replay',false);
end $$;
create or replace function lautowork.linkautowork_provider_transition(p_request_id uuid,p_expected_version integer,p_next_state text)
returns jsonb language plpgsql security invoker set search_path = lautowork, pg_temp as $$
declare v_request lautowork.provider_requests%rowtype;
begin
  select * into v_request from lautowork.provider_requests where id=p_request_id for update;
  if not found then raise exception 'provider request not found' using errcode='P0002'; end if;
  if v_request.org_id::text is distinct from current_setting('request.jwt.claim.org_id', true) then raise exception 'provider organisation context mismatch' using errcode='42501'; end if;
  if v_request.expected_version <> p_expected_version then raise exception 'provider expected version mismatch' using errcode='40001'; end if;
  if v_request.state in ('succeeded','failed','expired','cancelled','timed_out','rejected','quarantined','unavailable','contract_incompatible') then raise exception 'provider terminal transition denied' using errcode='55000'; end if;
  if p_next_state not in ('queued','running','succeeded','failed','expired','cancelled','timed_out','blocked','unavailable') then raise exception 'provider transition denied' using errcode='22023'; end if;
  if p_next_state in ('queued','running') and exists(select 1 from lautowork.provider_kill_switches k where k.org_id=v_request.org_id and k.active and (k.automation_id is null or k.automation_id=v_request.automation_id)) then raise exception 'provider kill switch active' using errcode='55000'; end if;
  update lautowork.provider_requests set state=p_next_state,expected_version=expected_version+1,updated_at=now() where id=p_request_id returning * into v_request;
  if p_next_state='running' then insert into lautowork.provider_attempts(request_id,attempt_number,state) values(v_request.id,(select coalesce(max(attempt_number),0)+1 from lautowork.provider_attempts where request_id=v_request.id),'running'); end if;
  return to_jsonb(v_request);
end $$;
create or replace function lautowork.linkautowork_provider_get_request(p_request_id uuid)
returns jsonb language sql security invoker set search_path = lautowork, pg_temp as $$
  select to_jsonb(r) from lautowork.provider_requests r where r.id=p_request_id and r.org_id::text=current_setting('request.jwt.claim.org_id',true)
$$;
create or replace function lautowork.linkautowork_provider_write_receipt(p_receipt jsonb)
returns jsonb language plpgsql security invoker set search_path = lautowork, pg_temp as $$
declare v_request lautowork.provider_requests%rowtype; v_receipt lautowork.provider_receipts%rowtype;
begin
  select * into v_request from lautowork.provider_requests where id=(p_receipt->>'request_id')::uuid for update;
  if not found or v_request.org_id::text is distinct from current_setting('request.jwt.claim.org_id',true) then raise exception 'provider request not found for organisation' using errcode='42501'; end if;
  if v_request.automation_id <> p_receipt->'automation'->>'automation_id' or v_request.automation_version <> p_receipt->'automation'->>'version' or v_request.configuration_digest <> p_receipt->'automation'->'configuration_ref'->>'digest' then raise exception 'provider receipt binding mismatch' using errcode='42501'; end if;
  select * into v_receipt from lautowork.provider_receipts where request_id=v_request.id for update;
  if found then if v_receipt.id <> (p_receipt->>'receipt_id')::uuid then raise exception 'provider receipt immutable conflict' using errcode='23505'; end if; return to_jsonb(v_receipt); end if;
  insert into lautowork.provider_receipts(id,request_id,org_id,state,attempt_count,evidence_ref,result_ref) values((p_receipt->>'receipt_id')::uuid,v_request.id,v_request.org_id,p_receipt->>'state',(p_receipt->>'attempt_count')::integer,p_receipt->'evidence_refs'->0->>'ref',p_receipt->'result_refs'->0->>'ref') returning * into v_receipt;
  update lautowork.provider_requests set state=v_receipt.state,updated_at=now() where id=v_request.id;
  return to_jsonb(v_receipt);
end $$;
create or replace function lautowork.linkautowork_provider_admit_callback(p_callback jsonb)
returns jsonb language plpgsql security invoker set search_path = lautowork, pg_temp as $$
declare v_receipt jsonb; v_request lautowork.provider_requests%rowtype;
begin
  if p_callback->>'org_id' is distinct from current_setting('request.jwt.claim.org_id',true) then raise exception 'provider callback organisation mismatch' using errcode='42501'; end if;
  select * into v_request from lautowork.provider_requests where id=(p_callback->>'request_id')::uuid for update;
  if not found or v_request.org_id::text is distinct from current_setting('request.jwt.claim.org_id',true) or v_request.configuration_ref <> p_callback->>'callback_binding_ref' then raise exception 'provider callback binding mismatch' using errcode='42501'; end if;
  v_receipt := lautowork.linkautowork_provider_write_receipt(p_callback->'receipt');
  insert into lautowork.provider_callbacks(request_id,org_id,receipt_id,callback_binding_ref,source_timestamp) values((p_callback->>'request_id')::uuid,(p_callback->>'org_id')::uuid,(p_callback->>'receipt_id')::uuid,p_callback->>'callback_binding_ref',(p_callback->>'source_timestamp')::timestamptz);
  return v_receipt;
exception when unique_violation then raise exception 'provider callback replay or out-of-order' using errcode='23505';
end $$;
create or replace function lautowork.linkautowork_provider_kill_switch_active(p_automation_id text)
returns boolean language sql security invoker set search_path = lautowork, pg_temp as $$
 select exists(select 1 from lautowork.provider_kill_switches k where k.org_id::text=current_setting('request.jwt.claim.org_id',true) and k.active and (k.automation_id is null or k.automation_id=p_automation_id))
$$;
create or replace function lautowork.linkautowork_provider_append_event(p_event jsonb)
returns void language plpgsql security invoker set search_path = lautowork, pg_temp as $$
declare v_org uuid := current_setting('request.jwt.claim.org_id',true)::uuid;
begin
  if v_org is null then raise exception 'provider organisation context missing' using errcode='42501'; end if;
  insert into lautowork.provider_events(event_id,org_id,source_ref,cursor,event_type,correlation_refs,payload_ref,payload_digest,occurred_at) values((p_event->>'event_id')::uuid,v_org,p_event->>'source_ref',p_event->>'cursor',p_event->>'type',coalesce(p_event->'correlation_refs','[]'::jsonb),p_event->'payload_ref'->>'ref',p_event->'payload_ref'->>'digest',(p_event->>'occurred_at')::timestamptz) on conflict(org_id,source_ref,cursor) do nothing;
end $$;
create or replace function lautowork.linkautowork_provider_list_events(p_after_cursor text,p_limit integer)
returns jsonb language sql security invoker set search_path = lautowork, pg_temp as $$
 with scoped as (select e.*,row_number() over(order by e.occurred_at,e.event_id) as n from lautowork.provider_events e where e.org_id::text=current_setting('request.jwt.claim.org_id',true)), after_row as (select coalesce((select n from scoped where cursor=p_after_cursor),0) as n), page as (select * from scoped where n>(select n from after_row) order by n limit greatest(1,least(p_limit,100)))
 select jsonb_build_object('events',coalesce((select jsonb_agg(jsonb_build_object('event_id',event_id,'source_ref',source_ref,'cursor',cursor,'correlation_refs',correlation_refs,'occurred_at',occurred_at,'type',event_type,'payload_ref',jsonb_build_object('ref',payload_ref,'digest',payload_digest,'observed_at',occurred_at)) order by n) from page),'[]'::jsonb),'next_cursor',(select cursor from scoped where n=(select max(n)+1 from page)),'acknowledged_cursor',p_after_cursor)
$$;
revoke all on function lautowork.linkautowork_provider_accept(jsonb,text),lautowork.linkautowork_provider_transition(uuid,integer,text),lautowork.linkautowork_provider_get_request(uuid),lautowork.linkautowork_provider_write_receipt(jsonb),lautowork.linkautowork_provider_admit_callback(jsonb),lautowork.linkautowork_provider_kill_switch_active(text),lautowork.linkautowork_provider_append_event(jsonb),lautowork.linkautowork_provider_list_events(text,integer) from public;
grant execute on function lautowork.linkautowork_provider_accept(jsonb,text),lautowork.linkautowork_provider_transition(uuid,integer,text),lautowork.linkautowork_provider_get_request(uuid),lautowork.linkautowork_provider_write_receipt(jsonb),lautowork.linkautowork_provider_admit_callback(jsonb),lautowork.linkautowork_provider_kill_switch_active(text),lautowork.linkautowork_provider_append_event(jsonb),lautowork.linkautowork_provider_list_events(text,integer) to svc_lautowork_runtime;
-- migrate:down
drop function if exists lautowork.linkautowork_provider_kill_switch_active(text);
drop function if exists lautowork.linkautowork_provider_list_events(text,integer);
drop function if exists lautowork.linkautowork_provider_append_event(jsonb);
drop function if exists lautowork.linkautowork_provider_admit_callback(jsonb);
drop function if exists lautowork.linkautowork_provider_write_receipt(jsonb);
drop function if exists lautowork.linkautowork_provider_get_request(uuid);
drop function if exists lautowork.linkautowork_provider_transition(uuid,integer,text);
drop function if exists lautowork.linkautowork_provider_accept(jsonb,text);
drop table if exists lautowork.provider_kill_switches;
drop table if exists lautowork.provider_outbox;
drop table if exists lautowork.provider_events;
drop table if exists lautowork.provider_callbacks;
drop table if exists lautowork.provider_receipts;
drop table if exists lautowork.provider_attempts;
drop table if exists lautowork.provider_requests;
