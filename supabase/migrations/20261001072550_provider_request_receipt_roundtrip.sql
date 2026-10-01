-- AW-01 additive persistence contract for the existing AW-02 invoker RPCs.
-- Full provider contracts contain bounded metadata and opaque references only;
-- they do not contain task bodies or credentials.
-- migrate:up
alter table lautowork.provider_requests
  add column request_json jsonb,
  add constraint provider_requests_request_json_object
    check (request_json is null or jsonb_typeof(request_json) = 'object');

alter table lautowork.provider_receipts
  add column receipt_json jsonb,
  add constraint provider_receipts_receipt_json_object
    check (receipt_json is null or jsonb_typeof(receipt_json) = 'object');

create or replace function lautowork.linkautowork_provider_accept(p_request jsonb, p_request_fingerprint text)
returns jsonb language plpgsql security invoker set search_path = lautowork, pg_temp as $$
declare
  v_org uuid;
  v_existing lautowork.provider_requests%rowtype;
  v_request lautowork.provider_requests%rowtype;
  v_record jsonb;
  v_receipt jsonb;
  v_callback_timestamp timestamptz;
begin
  if jsonb_typeof(p_request) is distinct from 'object'
     or p_request_fingerprint !~ '^sha256:[a-f0-9]{64}$' then
    raise exception 'invalid provider request envelope' using errcode = '22023';
  end if;
  v_org := (p_request->'platform'->>'org_id')::uuid;
  if v_org::text is distinct from current_setting('request.jwt.claim.org_id', true) then
    raise exception 'provider organisation context mismatch' using errcode = '42501';
  end if;
  if lautowork.linkautowork_provider_kill_switch_active(p_request->'automation'->>'automation_id') then
    raise exception 'provider kill switch active' using errcode = '55000';
  end if;

  select * into v_existing
  from lautowork.provider_requests
  where org_id = v_org and idempotency_key = p_request->>'idempotency_key'
  for update;
  if found then
    if v_existing.request_fingerprint <> p_request_fingerprint then
      raise exception 'provider idempotency conflict' using errcode = '23505';
    end if;
    if v_existing.request_json is null then
      raise exception 'provider legacy request payload unavailable' using errcode = '55000';
    end if;
    if v_existing.request_json <> p_request then
      raise exception 'provider idempotency content mismatch' using errcode = '23505';
    end if;
    v_request := v_existing;
    select receipt_json into v_receipt from lautowork.provider_receipts where request_id = v_request.id;
    if exists(select 1 from lautowork.provider_receipts where request_id = v_request.id) and v_receipt is null then
      raise exception 'provider legacy receipt payload unavailable' using errcode = '55000';
    end if;
    select source_timestamp into v_callback_timestamp from lautowork.provider_callbacks where request_id = v_request.id;
    v_record := jsonb_build_object(
      'orgId', v_request.org_id,
      'request', v_request.request_json,
      'fingerprint', v_request.request_fingerprint,
      'state', v_request.state,
      'version', v_request.expected_version,
      'attempts', coalesce((select max(attempt_number) from lautowork.provider_attempts where request_id = v_request.id), 0)
    );
    if v_receipt is not null then v_record := v_record || jsonb_build_object('receipt', v_receipt); end if;
    if v_callback_timestamp is not null then v_record := v_record || jsonb_build_object('callbackTimestamp', v_callback_timestamp); end if;
    return jsonb_build_object('record', v_record, 'replay', true);
  end if;

  insert into lautowork.provider_requests
    (id, org_id, contract_version, automation_id, automation_version, definition_digest,
     configuration_digest, configuration_ref, idempotency_key, request_fingerprint,
     operation_kind, state, expires_at, correlation_ref, handoff_ref, request_json)
  values
    ((p_request->>'request_id')::uuid, v_org, p_request->>'contract_version',
     p_request->'automation'->>'automation_id', p_request->'automation'->>'version',
     p_request->'automation'->>'definition_digest', p_request->'automation'->'configuration_ref'->>'digest',
     p_request->'automation'->'configuration_ref'->>'ref', p_request->>'idempotency_key',
     p_request_fingerprint, p_request->>'operation_kind', 'accepted',
     (p_request->>'expires_at')::timestamptz, p_request->'correlation_refs'->0->>'ref',
     p_request->'brain_handoff_ref'->>'ref', p_request)
  returning * into v_request;

  v_record := jsonb_build_object(
    'orgId', v_request.org_id,
    'request', v_request.request_json,
    'fingerprint', v_request.request_fingerprint,
    'state', v_request.state,
    'version', v_request.expected_version,
    'attempts', 0
  );
  return jsonb_build_object('record', v_record, 'replay', false);
end $$;

create or replace function lautowork.linkautowork_provider_get_request(p_request_id uuid)
returns jsonb language plpgsql security invoker set search_path = lautowork, pg_temp as $$
declare
  v_request lautowork.provider_requests%rowtype;
  v_receipt jsonb;
  v_callback_timestamp timestamptz;
  v_record jsonb;
begin
  select * into v_request from lautowork.provider_requests where id = p_request_id;
  if not found then raise exception 'provider request not found' using errcode = 'P0002'; end if;
  if v_request.org_id::text is distinct from current_setting('request.jwt.claim.org_id', true) then
    raise exception 'provider request not found for organisation' using errcode = '42501';
  end if;
  if v_request.request_json is null then
    raise exception 'provider legacy request payload unavailable' using errcode = '55000';
  end if;
  select receipt_json into v_receipt from lautowork.provider_receipts where request_id = v_request.id;
  if exists(select 1 from lautowork.provider_receipts where request_id = v_request.id) and v_receipt is null then
    raise exception 'provider legacy receipt payload unavailable' using errcode = '55000';
  end if;
  select source_timestamp into v_callback_timestamp from lautowork.provider_callbacks where request_id = v_request.id;
  v_record := jsonb_build_object(
    'orgId', v_request.org_id,
    'request', v_request.request_json,
    'fingerprint', v_request.request_fingerprint,
    'state', v_request.state,
    'version', v_request.expected_version,
    'attempts', coalesce((select max(attempt_number) from lautowork.provider_attempts where request_id = v_request.id), 0)
  );
  if v_receipt is not null then v_record := v_record || jsonb_build_object('receipt', v_receipt); end if;
  if v_callback_timestamp is not null then v_record := v_record || jsonb_build_object('callbackTimestamp', v_callback_timestamp); end if;
  return v_record;
end $$;

create or replace function lautowork.linkautowork_provider_transition(p_request_id uuid, p_expected_version integer, p_next_state text)
returns jsonb language plpgsql security invoker set search_path = lautowork, pg_temp as $$
declare
  v_request lautowork.provider_requests%rowtype;
  v_receipt jsonb;
  v_callback_timestamp timestamptz;
  v_record jsonb;
begin
  select * into v_request from lautowork.provider_requests where id = p_request_id for update;
  if not found then raise exception 'provider request not found' using errcode = 'P0002'; end if;
  if v_request.org_id::text is distinct from current_setting('request.jwt.claim.org_id', true) then
    raise exception 'provider request not found for organisation' using errcode = '42501';
  end if;
  if v_request.request_json is null then
    raise exception 'provider legacy request payload unavailable' using errcode = '55000';
  end if;
  if v_request.expected_version <> p_expected_version then
    raise exception 'provider expected version mismatch' using errcode = '40001';
  end if;
  if v_request.state in ('succeeded','failed','expired','cancelled','timed_out','rejected','quarantined','unavailable','contract_incompatible') then
    raise exception 'provider terminal transition denied' using errcode = '55000';
  end if;
  if p_next_state not in ('queued','running','succeeded','failed','expired','cancelled','timed_out','blocked','unavailable') then
    raise exception 'provider transition denied' using errcode = '22023';
  end if;
  if p_next_state in ('queued','running') and lautowork.linkautowork_provider_kill_switch_active(v_request.automation_id) then
    raise exception 'provider kill switch active' using errcode = '55000';
  end if;
  select receipt_json into v_receipt from lautowork.provider_receipts where request_id = v_request.id;
  if exists(select 1 from lautowork.provider_receipts where request_id = v_request.id) and v_receipt is null then
    raise exception 'provider legacy receipt payload unavailable' using errcode = '55000';
  end if;
  update lautowork.provider_requests
  set state = p_next_state, expected_version = expected_version + 1, updated_at = now()
  where id = p_request_id returning * into v_request;
  if p_next_state = 'running' then
    insert into lautowork.provider_attempts(request_id, attempt_number, state)
    values (v_request.id, (select coalesce(max(attempt_number), 0) + 1 from lautowork.provider_attempts where request_id = v_request.id), 'running');
  end if;
  select receipt_json into v_receipt from lautowork.provider_receipts where request_id = v_request.id;
  select source_timestamp into v_callback_timestamp from lautowork.provider_callbacks where request_id = v_request.id;
  v_record := jsonb_build_object(
    'orgId', v_request.org_id,
    'request', v_request.request_json,
    'fingerprint', v_request.request_fingerprint,
    'state', v_request.state,
    'version', v_request.expected_version,
    'attempts', coalesce((select max(attempt_number) from lautowork.provider_attempts where request_id = v_request.id), 0)
  );
  if v_receipt is not null then v_record := v_record || jsonb_build_object('receipt', v_receipt); end if;
  if v_callback_timestamp is not null then v_record := v_record || jsonb_build_object('callbackTimestamp', v_callback_timestamp); end if;
  return v_record;
end $$;

create or replace function lautowork.linkautowork_provider_write_receipt(p_receipt jsonb)
returns jsonb language plpgsql security invoker set search_path = lautowork, pg_temp as $$
declare
  v_request lautowork.provider_requests%rowtype;
  v_receipt lautowork.provider_receipts%rowtype;
begin
  if jsonb_typeof(p_receipt) is distinct from 'object' then
    raise exception 'invalid provider receipt envelope' using errcode = '22023';
  end if;
  select * into v_request from lautowork.provider_requests where id = (p_receipt->>'request_id')::uuid for update;
  if not found or v_request.org_id::text is distinct from current_setting('request.jwt.claim.org_id', true) then
    raise exception 'provider request not found for organisation' using errcode = '42501';
  end if;
  if v_request.request_json is null then
    raise exception 'provider legacy request payload unavailable' using errcode = '55000';
  end if;
  if v_request.automation_id <> p_receipt->'automation'->>'automation_id'
     or v_request.automation_version <> p_receipt->'automation'->>'version'
     or v_request.configuration_digest <> p_receipt->'automation'->'configuration_ref'->>'digest' then
    raise exception 'provider receipt binding mismatch' using errcode = '42501';
  end if;
  select * into v_receipt from lautowork.provider_receipts where request_id = v_request.id for update;
  if found then
    if v_receipt.receipt_json is null then
      raise exception 'provider legacy receipt payload unavailable' using errcode = '55000';
    end if;
    if v_receipt.id <> (p_receipt->>'receipt_id')::uuid or v_receipt.receipt_json <> p_receipt then
      raise exception 'provider receipt immutable conflict' using errcode = '23505';
    end if;
    return v_receipt.receipt_json;
  end if;
  insert into lautowork.provider_receipts
    (id, request_id, org_id, state, attempt_count, evidence_ref, result_ref, receipt_json)
  values
    ((p_receipt->>'receipt_id')::uuid, v_request.id, v_request.org_id, p_receipt->>'state',
     (p_receipt->>'attempt_count')::integer, p_receipt->'evidence_refs'->0->>'ref',
     p_receipt->'result_refs'->0->>'ref', p_receipt)
  returning * into v_receipt;
  update lautowork.provider_requests set state = v_receipt.state, updated_at = now() where id = v_request.id;
  return v_receipt.receipt_json;
end $$;

create or replace function lautowork.linkautowork_provider_admit_callback(p_callback jsonb)
returns jsonb language plpgsql security invoker set search_path = lautowork, pg_temp as $$
declare
  v_receipt jsonb;
  v_request lautowork.provider_requests%rowtype;
begin
  if p_callback->>'org_id' is distinct from current_setting('request.jwt.claim.org_id', true) then
    raise exception 'provider callback organisation mismatch' using errcode = '42501';
  end if;
  select * into v_request from lautowork.provider_requests where id = (p_callback->>'request_id')::uuid for update;
  if not found or v_request.org_id::text is distinct from current_setting('request.jwt.claim.org_id', true)
     or v_request.configuration_ref <> p_callback->>'callback_binding_ref' then
    raise exception 'provider callback binding mismatch' using errcode = '42501';
  end if;
  if v_request.request_json is null then
    raise exception 'provider legacy request payload unavailable' using errcode = '55000';
  end if;
  v_receipt := lautowork.linkautowork_provider_write_receipt(p_callback->'receipt');
  insert into lautowork.provider_callbacks
    (request_id, org_id, receipt_id, callback_binding_ref, source_timestamp)
  values
    ((p_callback->>'request_id')::uuid, (p_callback->>'org_id')::uuid,
     (p_callback->>'receipt_id')::uuid, p_callback->>'callback_binding_ref',
     (p_callback->>'source_timestamp')::timestamptz);
  return v_receipt;
exception when unique_violation then
  raise exception 'provider callback replay or out-of-order' using errcode = '23505';
end $$;

create or replace function lautowork.linkautowork_provider_kill_switch_active(p_automation_id text)
returns boolean language plpgsql security invoker set search_path = lautowork, pg_temp as $$
declare
  v_org_text text := nullif(current_setting('request.jwt.claim.org_id', true), '');
  v_org uuid;
  v_scope_key text;
begin
  if v_org_text is null then raise exception 'provider organisation context missing' using errcode = '42501'; end if;
  v_org := v_org_text::uuid;
  v_scope_key := 'automation:' || coalesce(p_automation_id, '');
  -- Share both locks with the mutator so admission and kill-switch changes have one order.
  perform pg_advisory_xact_lock(hashtextextended(v_org::text || ':global:', 0));
  if p_automation_id is not null then
    perform pg_advisory_xact_lock(hashtextextended(v_org::text || ':' || v_scope_key, 0));
  end if;
  return exists (
    select 1
    from (
      select distinct on (automation_id) automation_id, active
      from lautowork.provider_kill_switches
      where org_id = v_org
      order by automation_id, created_at desc, id desc
    ) current_switch
    where current_switch.active
      and (current_switch.automation_id is null or current_switch.automation_id = p_automation_id)
  );
end $$;

create or replace function lautowork.linkautowork_provider_set_kill_switch(
  p_automation_id text,
  p_active boolean,
  p_reason_ref text
)
returns void language plpgsql security invoker set search_path = lautowork, pg_temp as $$
declare
  v_org_text text := nullif(current_setting('request.jwt.claim.org_id', true), '');
  v_org uuid;
  v_scope_key text;
begin
  if v_org_text is null then raise exception 'provider organisation context missing' using errcode = '42501'; end if;
  if p_reason_ref is null or char_length(p_reason_ref) > 512
     or p_reason_ref !~ '^[a-z][a-z0-9+.-]*://[A-Za-z0-9._~/%:-]+$' then
    raise exception 'provider kill-switch reason must be an opaque reference' using errcode = '22023';
  end if;
  v_org := v_org_text::uuid;
  v_scope_key := case when p_automation_id is null then 'global:' else 'automation:' || p_automation_id end;
  perform pg_advisory_xact_lock(hashtextextended(v_org::text || ':global:', 0));
  if p_automation_id is not null then
    perform pg_advisory_xact_lock(hashtextextended(v_org::text || ':' || v_scope_key, 0));
  end if;
  insert into lautowork.provider_kill_switches(org_id, automation_id, active, reason_ref)
  values (v_org, p_automation_id, p_active, p_reason_ref);
end $$;

revoke all on function lautowork.linkautowork_provider_accept(jsonb,text),
  lautowork.linkautowork_provider_transition(uuid,integer,text),
  lautowork.linkautowork_provider_get_request(uuid),
  lautowork.linkautowork_provider_write_receipt(jsonb),
  lautowork.linkautowork_provider_admit_callback(jsonb),
  lautowork.linkautowork_provider_kill_switch_active(text),
  lautowork.linkautowork_provider_append_event(jsonb),
  lautowork.linkautowork_provider_list_events(text,integer),
  lautowork.linkautowork_provider_set_kill_switch(text,boolean,text) from public;
grant execute on function lautowork.linkautowork_provider_accept(jsonb,text),
  lautowork.linkautowork_provider_transition(uuid,integer,text),
  lautowork.linkautowork_provider_get_request(uuid),
  lautowork.linkautowork_provider_write_receipt(jsonb),
  lautowork.linkautowork_provider_admit_callback(jsonb),
  lautowork.linkautowork_provider_kill_switch_active(text),
  lautowork.linkautowork_provider_append_event(jsonb),
  lautowork.linkautowork_provider_list_events(text,integer),
  lautowork.linkautowork_provider_set_kill_switch(text,boolean,text) to svc_lautowork_runtime;

-- migrate:down
-- Disposable verification only: dropping these columns discards JSON written by the up migration.
drop function if exists lautowork.linkautowork_provider_set_kill_switch(text,boolean,text);
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
revoke all on function lautowork.linkautowork_provider_accept(jsonb,text),lautowork.linkautowork_provider_transition(uuid,integer,text),lautowork.linkautowork_provider_get_request(uuid),lautowork.linkautowork_provider_write_receipt(jsonb),lautowork.linkautowork_provider_admit_callback(jsonb),lautowork.linkautowork_provider_kill_switch_active(text),lautowork.linkautowork_provider_append_event(jsonb),lautowork.linkautowork_provider_list_events(text,integer) from public;
grant execute on function lautowork.linkautowork_provider_accept(jsonb,text),lautowork.linkautowork_provider_transition(uuid,integer,text),lautowork.linkautowork_provider_get_request(uuid),lautowork.linkautowork_provider_write_receipt(jsonb),lautowork.linkautowork_provider_admit_callback(jsonb),lautowork.linkautowork_provider_kill_switch_active(text),lautowork.linkautowork_provider_append_event(jsonb),lautowork.linkautowork_provider_list_events(text,integer) to svc_lautowork_runtime;
alter table lautowork.provider_requests drop constraint provider_requests_request_json_object, drop column request_json;
alter table lautowork.provider_receipts drop constraint provider_receipts_receipt_json_object, drop column receipt_json;
