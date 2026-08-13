-- AW-02: additive durable provider plane. Source-only; no live application is implied.
-- migrate:up
create table if not exists lautowork.provider_requests (
  id uuid primary key, org_id uuid not null references platform.organizations(id) on delete restrict,
  contract_version text not null check (char_length(contract_version) between 1 and 64),
  automation_id text not null check (automation_id !~ '(issue|ledger|gate|order|filing|service|privilege)'),
  automation_version text not null, definition_digest text not null check (definition_digest ~ '^sha256:[a-f0-9]{64}$'),
  configuration_digest text not null check (configuration_digest ~ '^sha256:[a-f0-9]{64}$'),
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
  cursor text not null, payload_digest text not null check (payload_digest ~ '^sha256:[a-f0-9]{64}$'), occurred_at timestamptz not null, unique(org_id, source_ref, cursor)
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
do $$ declare t text; begin foreach t in array array['provider_requests','provider_receipts','provider_events','provider_outbox','provider_kill_switches'] loop
 execute format('create policy %I on lautowork.%I for all to svc_lautowork_runtime using (org_id::text=current_setting(''request.jwt.claim.org_id'',true)) with check (org_id::text=current_setting(''request.jwt.claim.org_id'',true))', 'provider_'||t||'_org',t); end loop;
create policy provider_attempts_org on lautowork.provider_attempts for all to svc_lautowork_runtime using (exists(select 1 from lautowork.provider_requests r where r.id=request_id and r.org_id::text=current_setting('request.jwt.claim.org_id',true))) with check (exists(select 1 from lautowork.provider_requests r where r.id=request_id and r.org_id::text=current_setting('request.jwt.claim.org_id',true)));
end $$;
-- migrate:down
drop table if exists lautowork.provider_kill_switches;
drop table if exists lautowork.provider_outbox;
drop table if exists lautowork.provider_events;
drop table if exists lautowork.provider_receipts;
drop table if exists lautowork.provider_attempts;
drop table if exists lautowork.provider_requests;
