-- AW-01: additive Server01 live-interface, identity, role and fingerprint package.
-- Platform-consumable. Does not alter platform.*, lautowork_n8n, or existing
-- provider-plane RPCs. Stores references and digests only: no task bodies,
-- raw prompts, or secret values.
--
-- Prerequisites: platform.organizations / platform.has_org_access();
-- 20260715 through 20260813 Autowork migrations including provider plane.
--
-- migrate:up

create or replace function lautowork.server01_text_is_secret_shaped(value text)
returns boolean
language sql
immutable
set search_path = lautowork, pg_temp
as $$
  select coalesce(
    value ~* '(postgres(ql)?|mysql|mongodb(\+srv)?|redis|amqp)://[^[:space:]]+:[^[:space:]@]+@'
    or value ~* '(^|[^[:alnum:]])bearer[[:space:]]+[a-z0-9._~+/-]{8,}'
    or value ~* '-----begin[[:space:]][a-z ]*private[[:space:]]key-----'
    or value ~* '(^|[^[:alnum:]_])(sk|pk|ghp|xox[baprs])[_-][a-z0-9-]{12,}'
    or value ~* '(password|passwd|api[_-]?key|private[_-]?key|connection[_-]?string)\s*[:=]',
    false
  );
$$;

create table if not exists lautowork.server01_package_control (
  package_id text primary key check (package_id = 'lautowork.server01.migration-identity/1.0.0'),
  apply_state text not null check (apply_state in ('started', 'complete')),
  expected_relation_count integer not null check (expected_relation_count = 7),
  live_fingerprint text check (live_fingerprint is null or live_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  started_at timestamptz not null default now(),
  completed_at timestamptz
);

insert into lautowork.server01_package_control (package_id, apply_state, expected_relation_count)
values ('lautowork.server01.migration-identity/1.0.0', 'started', 7)
on conflict (package_id) do update
  set apply_state = 'started', live_fingerprint = null, completed_at = null, started_at = now();

create table if not exists lautowork.server01_credential_bindings (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  binding_id text not null check (char_length(binding_id) between 1 and 128 and binding_id ~ '^[A-Za-z0-9._:-]+$'),
  secret_ref text not null check (secret_ref ~ '^LINKTREND_[A-Z0-9_]{3,120}$'),
  purpose text not null check (char_length(purpose) between 3 and 240),
  scope text not null check (scope in ('gateway', 'product_api', 'runtime_dispatch', 'n8n', 'observer', 'migration_backup')),
  health_state text not null default 'unknown' check (health_state in ('unknown', 'healthy', 'expiring', 'invalid', 'revoked')),
  created_at timestamptz not null default now(),
  unique (org_id, binding_id),
  unique (id, org_id),
  constraint server01_credential_bindings_no_secret_shaped check (
    not lautowork.server01_text_is_secret_shaped(secret_ref)
    and not lautowork.server01_text_is_secret_shaped(purpose)
    and not lautowork.server01_text_is_secret_shaped(binding_id)
  )
);

comment on table lautowork.server01_credential_bindings is
  'GSM secret names and Platform credential/binding identifiers only. No secret values.';

create table if not exists lautowork.server01_invocation_requests (
  id uuid primary key,
  org_id uuid not null references platform.organizations(id) on delete restrict,
  work_ref text not null check (work_ref ~ '^[a-z][a-z0-9+.-]*://[A-Za-z0-9._~/%:-]+$' and char_length(work_ref) <= 512),
  authority_ref text not null check (authority_ref ~ '^[a-z][a-z0-9+.-]*://[A-Za-z0-9._~/%:-]+$' and char_length(authority_ref) <= 512),
  actor_id text not null check (char_length(actor_id) between 1 and 256),
  audience text not null check (char_length(audience) between 1 and 256),
  capability text not null check (char_length(capability) between 1 and 256),
  credential_id text not null check (char_length(credential_id) between 1 and 256),
  credential_binding_ref text not null check (credential_binding_ref ~ '^[a-z][a-z0-9+.-]*://[A-Za-z0-9._~/%:-]+$' and char_length(credential_binding_ref) <= 512),
  binding_id text not null check (char_length(binding_id) between 1 and 128),
  automation_id text not null check (automation_id !~ '(issue|ledger|gate|order|filing|service|privilege)'),
  automation_version text not null,
  definition_digest text not null check (definition_digest ~ '^sha256:[a-f0-9]{64}$'),
  configuration_digest text not null check (configuration_digest ~ '^sha256:[a-f0-9]{64}$'),
  configuration_ref text not null check (char_length(configuration_ref) <= 512),
  allowed_operation text not null check (char_length(allowed_operation) between 3 and 128),
  operation_kind text not null check (operation_kind in (
    'status_collection','precheck','evidence_collection','notification_delivery',
    'external_assistance','artifact_transform','media_package','outreach_adapter'
  )),
  input_ref text not null check (input_ref ~ '^[a-z][a-z0-9+.-]*://[A-Za-z0-9._~/%:-]+$' and char_length(input_ref) <= 512),
  input_digest text not null check (input_digest ~ '^sha256:[a-f0-9]{64}$'),
  idempotency_key text not null check (char_length(idempotency_key) between 16 and 160),
  request_fingerprint text not null check (request_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  callback_binding_ref text not null check (callback_binding_ref ~ '^[a-z][a-z0-9+.-]*://[A-Za-z0-9._~/%:-]+$' and char_length(callback_binding_ref) <= 512),
  budget_ceiling_ref text not null check (budget_ceiling_ref ~ '^[a-z][a-z0-9+.-]*://[A-Za-z0-9._~/%:-]+$' and char_length(budget_ceiling_ref) <= 512),
  expires_at timestamptz not null,
  state text not null check (state in (
    'accepted','prepared','dispatched','succeeded','failed','expired','cancelled','timed_out','rejected'
  )),
  expected_version integer not null default 1 check (expected_version > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (org_id, idempotency_key),
  unique (id, org_id),
  constraint server01_invocation_no_secret_shaped check (
    not lautowork.server01_text_is_secret_shaped(work_ref)
    and not lautowork.server01_text_is_secret_shaped(authority_ref)
    and not lautowork.server01_text_is_secret_shaped(input_ref)
    and not lautowork.server01_text_is_secret_shaped(callback_binding_ref)
  )
);

comment on column lautowork.server01_invocation_requests.work_ref is
  'Opaque Program-owned work reference. Task bodies are forbidden.';

create table if not exists lautowork.server01_prepared_intents (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null,
  org_id uuid not null references platform.organizations(id) on delete restrict,
  intent_fingerprint text not null check (intent_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  state text not null check (state in ('PREPARED', 'dispatched', 'cancelled', 'terminal')),
  expected_version integer not null default 1 check (expected_version > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (request_id),
  unique (id, org_id),
  foreign key (request_id, org_id) references lautowork.server01_invocation_requests(id, org_id) on delete restrict
);

create table if not exists lautowork.server01_intent_outbox (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  request_id uuid not null,
  kind text not null check (kind in ('prepared_intent', 'callback_ack', 'receipt_committed')),
  payload_ref text not null check (payload_ref ~ '^[a-z][a-z0-9+.-]*://[A-Za-z0-9._~/%:-]+$' and char_length(payload_ref) <= 512),
  payload_digest text not null check (payload_digest ~ '^sha256:[a-f0-9]{64}$'),
  state text not null default 'pending' check (state in ('pending', 'delivered', 'failed', 'dlq')),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  available_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  foreign key (request_id, org_id) references lautowork.server01_invocation_requests(id, org_id) on delete restrict,
  constraint server01_outbox_no_payload_body check (payload_ref !~* 'task.body|prompt|secret')
);

create table if not exists lautowork.server01_receipts (
  id uuid primary key,
  request_id uuid not null unique,
  org_id uuid not null references platform.organizations(id) on delete restrict,
  state text not null,
  request_fingerprint text not null check (request_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  evidence_ref text check (evidence_ref is null or (evidence_ref ~ '^[a-z][a-z0-9+.-]*://[A-Za-z0-9._~/%:-]+$' and char_length(evidence_ref) <= 512)),
  result_ref text check (result_ref is null or (result_ref ~ '^[a-z][a-z0-9+.-]*://[A-Za-z0-9._~/%:-]+$' and char_length(result_ref) <= 512)),
  does_not_complete_consumer boolean not null default true check (does_not_complete_consumer),
  created_at timestamptz not null default now(),
  immutable_at timestamptz not null default now(),
  foreign key (request_id, org_id) references lautowork.server01_invocation_requests(id, org_id) on delete restrict
);

comment on table lautowork.server01_receipts is
  'Immutable Autowork receipts. They never mark a Program Issue, gate, PR, release or deployment complete.';

create table if not exists lautowork.server01_callbacks (
  request_id uuid primary key,
  org_id uuid not null references platform.organizations(id) on delete restrict,
  receipt_id uuid not null references lautowork.server01_receipts(id) on delete restrict,
  callback_binding_ref text not null,
  callback_fingerprint text not null check (callback_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  source_timestamp timestamptz not null,
  created_at timestamptz not null default now(),
  foreign key (request_id, org_id) references lautowork.server01_invocation_requests(id, org_id) on delete restrict
);

create or replace function lautowork.server01_reject_mutation()
returns trigger
language plpgsql
set search_path = lautowork, pg_temp
as $$
begin
  raise exception 'server01 % records are append-only', tg_table_name using errcode = '55000';
end;
$$;

drop trigger if exists server01_credential_bindings_append_only on lautowork.server01_credential_bindings;
create trigger server01_credential_bindings_append_only
  before update or delete on lautowork.server01_credential_bindings
  for each row execute function lautowork.server01_reject_mutation();

drop trigger if exists server01_receipts_append_only on lautowork.server01_receipts;
create trigger server01_receipts_append_only
  before update or delete on lautowork.server01_receipts
  for each row execute function lautowork.server01_reject_mutation();

drop trigger if exists server01_callbacks_append_only on lautowork.server01_callbacks;
create trigger server01_callbacks_append_only
  before update or delete on lautowork.server01_callbacks
  for each row execute function lautowork.server01_reject_mutation();

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'svc_lautowork_gateway') then
    create role svc_lautowork_gateway nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'svc_lautowork_product_api') then
    create role svc_lautowork_product_api nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'svc_lautowork_runtime_dispatch') then
    create role svc_lautowork_runtime_dispatch nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'svc_lautowork_migration_backup') then
    create role svc_lautowork_migration_backup nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'svc_lautowork_n8n') then
    create role svc_lautowork_n8n nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'svc_observer') then
    create role svc_observer nologin;
  end if;
end $$;

create or replace function lautowork.server01_require_org(p_org uuid)
returns void
language plpgsql
stable
set search_path = lautowork, pg_temp
as $$
begin
  if p_org::text is distinct from current_setting('request.jwt.claim.org_id', true) then
    raise exception 'server01 organisation context mismatch' using errcode = '42501';
  end if;
end;
$$;

create or replace function lautowork.server01_accept_invocation(p_request jsonb, p_request_fingerprint text)
returns jsonb
language plpgsql
security invoker
set search_path = lautowork, pg_temp
as $$
declare
  v_org uuid;
  v_existing lautowork.server01_invocation_requests%rowtype;
  v_request lautowork.server01_invocation_requests%rowtype;
  v_intent lautowork.server01_prepared_intents%rowtype;
begin
  if lautowork.server01_text_is_secret_shaped(p_request::text) then
    raise exception 'server01 request contains secret-shaped content' using errcode = '22023';
  end if;
  if p_request ? 'task_body' or p_request ? 'raw_payload' or p_request ? 'prompt' then
    raise exception 'server01 request must not store task bodies' using errcode = '22023';
  end if;
  v_org := (p_request->>'org_id')::uuid;
  perform lautowork.server01_require_org(v_org);
  if p_request_fingerprint !~ '^sha256:[a-f0-9]{64}$' then
    raise exception 'server01 request fingerprint invalid' using errcode = '22023';
  end if;

  perform pg_advisory_xact_lock(
    hashtext(v_org::text),
    hashtext(coalesce(p_request->>'idempotency_key', ''))
  );

  select * into v_existing
    from lautowork.server01_invocation_requests
    where org_id = v_org and idempotency_key = p_request->>'idempotency_key'
    for update;
  if found then
    if v_existing.request_fingerprint is distinct from p_request_fingerprint then
      raise exception 'server01 idempotency conflict' using errcode = '23505';
    end if;
    select * into v_intent from lautowork.server01_prepared_intents where request_id = v_existing.id;
    return jsonb_build_object('record', to_jsonb(v_existing), 'intent', to_jsonb(v_intent), 'replay', true);
  end if;

  begin
    insert into lautowork.server01_invocation_requests (
      id, org_id, work_ref, authority_ref, actor_id, audience, capability, credential_id,
      credential_binding_ref, binding_id, automation_id, automation_version, definition_digest,
      configuration_digest, configuration_ref, allowed_operation, operation_kind, input_ref,
      input_digest, idempotency_key, request_fingerprint, callback_binding_ref, budget_ceiling_ref,
      expires_at, state
    ) values (
      (p_request->>'request_id')::uuid,
      v_org,
      p_request->>'work_ref',
      p_request->>'authority_ref',
      p_request->>'actor_id',
      p_request->>'audience',
      p_request->>'capability',
      p_request->>'credential_id',
      p_request->>'credential_binding_ref',
      p_request->>'binding_id',
      p_request->>'automation_id',
      p_request->>'automation_version',
      p_request->>'definition_digest',
      p_request->>'configuration_digest',
      p_request->>'configuration_ref',
      p_request->>'allowed_operation',
      p_request->>'operation_kind',
      p_request->>'input_ref',
      p_request->>'input_digest',
      p_request->>'idempotency_key',
      p_request_fingerprint,
      p_request->>'callback_binding_ref',
      p_request->>'budget_ceiling_ref',
      (p_request->>'expires_at')::timestamptz,
      'prepared'
    ) returning * into v_request;
  exception
    when unique_violation then
      select * into v_existing
        from lautowork.server01_invocation_requests
        where org_id = v_org and idempotency_key = p_request->>'idempotency_key'
        for update;
      if not found then
        raise exception 'server01 accept race unresolved' using errcode = 'P0001';
      end if;
      if v_existing.request_fingerprint is distinct from p_request_fingerprint then
        raise exception 'server01 idempotency conflict' using errcode = '23505';
      end if;
      select * into v_intent from lautowork.server01_prepared_intents where request_id = v_existing.id;
      return jsonb_build_object('record', to_jsonb(v_existing), 'intent', to_jsonb(v_intent), 'replay', true);
  end;

  insert into lautowork.server01_prepared_intents (request_id, org_id, intent_fingerprint, state)
  values (v_request.id, v_org, p_request_fingerprint, 'PREPARED')
  returning * into v_intent;

  insert into lautowork.server01_intent_outbox (org_id, request_id, kind, payload_ref, payload_digest)
  values (
    v_org,
    v_request.id,
    'prepared_intent',
    'autowork://intents/' || v_request.id::text,
    p_request_fingerprint
  );

  return jsonb_build_object('record', to_jsonb(v_request), 'intent', to_jsonb(v_intent), 'replay', false);
end;
$$;

create or replace function lautowork.server01_write_receipt(p_receipt jsonb)
returns jsonb
language plpgsql
security invoker
set search_path = lautowork, pg_temp
as $$
declare
  v_request lautowork.server01_invocation_requests%rowtype;
  v_receipt lautowork.server01_receipts%rowtype;
begin
  select * into v_request
    from lautowork.server01_invocation_requests
    where id = (p_receipt->>'request_id')::uuid
    for update;
  if not found then
    raise exception 'server01 request not found' using errcode = 'P0002';
  end if;
  perform lautowork.server01_require_org(v_request.org_id);
  if v_request.request_fingerprint is distinct from p_receipt->>'request_fingerprint' then
    raise exception 'server01 receipt fingerprint mismatch' using errcode = '42501';
  end if;
  select * into v_receipt from lautowork.server01_receipts where request_id = v_request.id;
  if found then
    if v_receipt.id is distinct from (p_receipt->>'receipt_id')::uuid then
      raise exception 'server01 receipt immutable conflict' using errcode = '23505';
    end if;
    return to_jsonb(v_receipt);
  end if;
  insert into lautowork.server01_receipts (
    id, request_id, org_id, state, request_fingerprint, evidence_ref, result_ref, does_not_complete_consumer
  ) values (
    (p_receipt->>'receipt_id')::uuid,
    v_request.id,
    v_request.org_id,
    p_receipt->>'state',
    p_receipt->>'request_fingerprint',
    p_receipt->>'evidence_ref',
    p_receipt->>'result_ref',
    true
  ) returning * into v_receipt;
  update lautowork.server01_invocation_requests
    set state = v_receipt.state, expected_version = expected_version + 1, updated_at = now()
    where id = v_request.id;
  update lautowork.server01_prepared_intents
    set state = 'terminal', expected_version = expected_version + 1, updated_at = now()
    where request_id = v_request.id and state in ('PREPARED', 'dispatched');
  insert into lautowork.server01_intent_outbox (org_id, request_id, kind, payload_ref, payload_digest)
  values (v_request.org_id, v_request.id, 'receipt_committed', 'autowork://receipts/' || v_receipt.id::text, v_receipt.request_fingerprint);
  return to_jsonb(v_receipt);
end;
$$;

create or replace function lautowork.server01_admit_callback(p_callback jsonb)
returns jsonb
language plpgsql
security invoker
set search_path = lautowork, pg_temp
as $$
declare
  v_request lautowork.server01_invocation_requests%rowtype;
  v_receipt jsonb;
  v_existing lautowork.server01_callbacks%rowtype;
begin
  if (p_callback->>'org_id') is distinct from current_setting('request.jwt.claim.org_id', true) then
    raise exception 'server01 callback organisation mismatch' using errcode = '42501';
  end if;
  if (p_callback->>'request_id') is distinct from (p_callback#>>'{receipt,request_id}') then
    raise exception 'server01 callback request mismatch' using errcode = '22023';
  end if;
  select * into v_request
    from lautowork.server01_invocation_requests
    where id = (p_callback->>'request_id')::uuid
    for update;
  if not found or v_request.callback_binding_ref is distinct from p_callback->>'callback_binding_ref' then
    raise exception 'server01 callback binding mismatch' using errcode = '42501';
  end if;
  select * into v_existing from lautowork.server01_callbacks where request_id = v_request.id;
  if found then
    if v_existing.callback_fingerprint is distinct from p_callback->>'callback_fingerprint' then
      raise exception 'server01 callback replay conflict' using errcode = '23505';
    end if;
    select to_jsonb(r) into v_receipt from lautowork.server01_receipts r where r.id = v_existing.receipt_id;
    return jsonb_build_object('receipt', v_receipt, 'replay', true);
  end if;
  v_receipt := lautowork.server01_write_receipt(p_callback->'receipt');
  insert into lautowork.server01_callbacks (
    request_id, org_id, receipt_id, callback_binding_ref, callback_fingerprint, source_timestamp
  ) values (
    v_request.id,
    v_request.org_id,
    (v_receipt->>'id')::uuid,
    p_callback->>'callback_binding_ref',
    p_callback->>'callback_fingerprint',
    (p_callback->>'source_timestamp')::timestamptz
  );
  insert into lautowork.server01_intent_outbox (org_id, request_id, kind, payload_ref, payload_digest)
  values (v_request.org_id, v_request.id, 'callback_ack', 'autowork://callbacks/' || v_request.id::text, p_callback->>'callback_fingerprint');
  return jsonb_build_object('receipt', v_receipt, 'replay', false);
end;
$$;

create or replace function lautowork.server01_live_fingerprint()
returns text
language plpgsql
stable
set search_path = pg_catalog, lautowork, pg_temp
as $$
declare
  payload text;
begin
  select string_agg(line, E'\n' order by line) into payload
  from (
    select format('col:%s.%s:%s', c.relname, a.attname, t.typname) as line
      from pg_attribute a
      join pg_class c on c.oid = a.attrelid
      join pg_namespace n on n.oid = c.relnamespace
      join pg_type t on t.oid = a.atttypid
     where n.nspname = 'lautowork'
       and c.relkind = 'r'
       and c.relname like 'server01_%'
       and a.attnum > 0
       and not a.attisdropped
    union all
    select format(
             'grant:%s:%s:%s',
             case when ae.grantee = 0 then 'PUBLIC' else pg_get_userbyid(ae.grantee) end,
             c.relname,
             ae.privilege_type
           )
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
      cross join lateral aclexplode(
        coalesce(c.relacl, acldefault('r'::"char", c.relowner))
      ) as ae
     where n.nspname = 'lautowork'
       and c.relkind = 'r'
       and c.relname like 'server01_%'
    union all
    select format('role:%s', r.rolname)
      from pg_roles r
     where r.rolname in (
       'svc_lautowork_gateway', 'svc_lautowork_product_api', 'svc_lautowork_runtime_dispatch',
       'svc_lautowork_n8n', 'svc_observer', 'svc_lautowork_migration_backup'
     )
  ) s;
  return 'sha256:' || encode(sha256(convert_to(coalesce(payload, ''), 'UTF8')), 'hex');
end;
$$;

-- SECURITY DEFINER is required so EXECUTE grantees can read package status
-- without a direct SELECT grant on server01_package_control. The function
-- returns only a status token, runs as the owner, and pins search_path.
create or replace function lautowork.server01_package_status()
returns text
language plpgsql
stable
security definer
set search_path = pg_catalog, lautowork, pg_temp
as $$
declare
  v_control lautowork.server01_package_control%rowtype;
  v_count integer;
begin
  select * into v_control from lautowork.server01_package_control
    where package_id = 'lautowork.server01.migration-identity/1.0.0';
  if not found then
    return 'absent';
  end if;
  select count(*) into v_count
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'lautowork' and c.relkind = 'r' and c.relname like 'server01_%';
  if v_control.apply_state is distinct from 'complete' or v_count <> v_control.expected_relation_count then
    return 'partial';
  end if;
  if v_control.live_fingerprint is distinct from lautowork.server01_live_fingerprint() then
    return 'drift';
  end if;
  return 'complete';
end;
$$;

create or replace function lautowork.server01_assert_package_ready()
returns void
language plpgsql
stable
set search_path = lautowork, pg_temp
as $$
begin
  if lautowork.server01_package_status() is distinct from 'complete' then
    raise exception 'server01 migration package is not complete (status=%)', lautowork.server01_package_status()
      using errcode = 'P0001';
  end if;
end;
$$;

revoke all on schema lautowork from public;
grant usage on schema lautowork to
  svc_lautowork_gateway, svc_lautowork_product_api, svc_lautowork_runtime_dispatch,
  svc_observer, svc_lautowork_migration_backup, svc_lautowork_runtime;

grant select on all tables in schema lautowork to svc_lautowork_migration_backup, svc_observer;
grant usage, select on all sequences in schema lautowork to svc_lautowork_migration_backup;

grant select, insert, update on
  lautowork.server01_invocation_requests,
  lautowork.server01_prepared_intents,
  lautowork.server01_intent_outbox
  to svc_lautowork_gateway;

grant select, insert on
  lautowork.server01_credential_bindings
  to svc_lautowork_gateway;

grant select, insert, update on
  lautowork.server01_invocation_requests,
  lautowork.server01_prepared_intents,
  lautowork.server01_intent_outbox
  to svc_lautowork_runtime_dispatch;

grant select, insert on
  lautowork.server01_receipts,
  lautowork.server01_callbacks
  to svc_lautowork_runtime_dispatch;

grant select on
  lautowork.server01_invocation_requests,
  lautowork.server01_prepared_intents,
  lautowork.server01_intent_outbox,
  lautowork.server01_receipts,
  lautowork.server01_callbacks,
  lautowork.server01_credential_bindings,
  lautowork.server01_package_control
  to svc_lautowork_product_api, svc_observer, svc_lautowork_migration_backup;

revoke all on
  lautowork.server01_invocation_requests,
  lautowork.server01_prepared_intents,
  lautowork.server01_intent_outbox,
  lautowork.server01_receipts,
  lautowork.server01_callbacks,
  lautowork.server01_credential_bindings,
  lautowork.server01_package_control
  from public;

do $$
declare
  t text;
  server01_tables text[] := array[
    'server01_package_control',
    'server01_credential_bindings',
    'server01_invocation_requests',
    'server01_prepared_intents',
    'server01_intent_outbox',
    'server01_receipts',
    'server01_callbacks'
  ];
begin
  foreach t in array server01_tables loop
    execute format('alter table lautowork.%I enable row level security', t);
    if t <> 'server01_package_control' then
      execute format('alter table lautowork.%I force row level security', t);
    end if;
    execute format('drop policy if exists server01_%s_org on lautowork.%I', t, t);
    if t = 'server01_package_control' then
      execute format(
        'create policy server01_%s_org on lautowork.%I for select to svc_lautowork_gateway, svc_lautowork_product_api, svc_lautowork_runtime_dispatch, svc_observer, svc_lautowork_migration_backup, svc_lautowork_runtime using (true)',
        t, t
      );
    else
      execute format(
        'create policy server01_%s_org on lautowork.%I for all to svc_lautowork_gateway, svc_lautowork_product_api, svc_lautowork_runtime_dispatch, svc_observer, svc_lautowork_migration_backup, svc_lautowork_runtime using (org_id::text = current_setting(''request.jwt.claim.org_id'', true)) with check (org_id::text = current_setting(''request.jwt.claim.org_id'', true))',
        t, t
      );
    end if;
  end loop;
end $$;

revoke all on function lautowork.server01_accept_invocation(jsonb, text) from public;
revoke all on function lautowork.server01_write_receipt(jsonb) from public;
revoke all on function lautowork.server01_admit_callback(jsonb) from public;
revoke all on function lautowork.server01_live_fingerprint() from public;
revoke all on function lautowork.server01_package_status() from public;
revoke all on function lautowork.server01_assert_package_ready() from public;

grant execute on function lautowork.server01_accept_invocation(jsonb, text)
  to svc_lautowork_gateway, svc_lautowork_runtime;
grant execute on function lautowork.server01_write_receipt(jsonb)
  to svc_lautowork_runtime_dispatch, svc_lautowork_runtime;
grant execute on function lautowork.server01_admit_callback(jsonb)
  to svc_lautowork_runtime_dispatch, svc_lautowork_runtime;
grant execute on function lautowork.server01_live_fingerprint()
  to svc_lautowork_gateway, svc_lautowork_product_api, svc_lautowork_runtime_dispatch,
     svc_observer, svc_lautowork_migration_backup, svc_lautowork_runtime;
grant execute on function lautowork.server01_package_status()
  to svc_lautowork_gateway, svc_lautowork_product_api, svc_lautowork_runtime_dispatch,
     svc_observer, svc_lautowork_migration_backup, svc_lautowork_runtime;
grant execute on function lautowork.server01_assert_package_ready()
  to svc_lautowork_migration_backup, svc_lautowork_runtime;

revoke all on function lautowork.server01_accept_invocation(jsonb, text) from svc_lautowork_n8n, svc_lautowork_product_api, svc_observer, svc_lautowork_migration_backup;
revoke all on function lautowork.server01_write_receipt(jsonb) from svc_lautowork_n8n, svc_lautowork_gateway, svc_lautowork_product_api, svc_observer, svc_lautowork_migration_backup;
revoke all on function lautowork.server01_admit_callback(jsonb) from svc_lautowork_n8n, svc_lautowork_gateway, svc_lautowork_product_api, svc_observer, svc_lautowork_migration_backup;

update lautowork.server01_package_control
   set apply_state = 'complete',
       live_fingerprint = lautowork.server01_live_fingerprint(),
       completed_at = now()
 where package_id = 'lautowork.server01.migration-identity/1.0.0';

select lautowork.server01_assert_package_ready();

-- migrate:down
revoke all on schema lautowork from svc_lautowork_gateway, svc_lautowork_product_api, svc_lautowork_runtime_dispatch, svc_lautowork_migration_backup;
revoke all on all tables in schema lautowork from svc_lautowork_gateway, svc_lautowork_product_api, svc_lautowork_runtime_dispatch, svc_lautowork_migration_backup;
revoke all on all sequences in schema lautowork from svc_lautowork_gateway, svc_lautowork_product_api, svc_lautowork_runtime_dispatch, svc_lautowork_migration_backup;
revoke all on all functions in schema lautowork from svc_lautowork_gateway, svc_lautowork_product_api, svc_lautowork_runtime_dispatch, svc_lautowork_migration_backup;
drop function if exists lautowork.server01_assert_package_ready();
drop function if exists lautowork.server01_package_status();
drop function if exists lautowork.server01_live_fingerprint();
drop function if exists lautowork.server01_admit_callback(jsonb);
drop function if exists lautowork.server01_write_receipt(jsonb);
drop function if exists lautowork.server01_accept_invocation(jsonb, text);
drop function if exists lautowork.server01_require_org(uuid);
drop table if exists lautowork.server01_callbacks;
drop table if exists lautowork.server01_receipts;
drop table if exists lautowork.server01_intent_outbox;
drop table if exists lautowork.server01_prepared_intents;
drop table if exists lautowork.server01_invocation_requests;
drop table if exists lautowork.server01_credential_bindings;
drop table if exists lautowork.server01_package_control;
drop function if exists lautowork.server01_reject_mutation();
drop function if exists lautowork.server01_text_is_secret_shaped(text);
drop role if exists svc_lautowork_gateway;
drop role if exists svc_lautowork_product_api;
drop role if exists svc_lautowork_runtime_dispatch;
drop role if exists svc_lautowork_migration_backup;
