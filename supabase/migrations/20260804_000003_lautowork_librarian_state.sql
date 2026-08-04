begin;

create table if not exists lautowork.automation_librarian_candidates (
  id uuid not null,
  org_id uuid not null references platform.organizations(id) on delete restrict,
  deduplication_key text not null check (deduplication_key ~ '^sha256:[a-f0-9]{64}$'),
  automation_id text not null,
  status text not null check (status in ('proposed','validation_failed','ready_for_eval','eval_failed','awaiting_review','approved','rejected','superseded')),
  proposer_ref text not null,
  candidate jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (id, org_id),
  unique (org_id, deduplication_key)
);

create table if not exists lautowork.automation_librarian_controls (
  org_id uuid not null references platform.organizations(id) on delete restrict,
  automation_id text not null,
  enabled boolean not null,
  updated_at timestamptz not null default now(),
  primary key (org_id, automation_id)
);

create table if not exists lautowork.automation_librarian_evidence (
  evidence_ref text primary key check (evidence_ref ~ '^evidence://[A-Za-z0-9._~/-]+$'),
  org_id uuid references platform.organizations(id) on delete restrict,
  payload jsonb not null,
  payload_hash text not null check (payload_hash ~ '^sha256:[a-f0-9]{64}$'),
  aggregate_approval_issuer text,
  aggregate_approval_ref text,
  aggregate_deidentified boolean not null default false,
  verifier_key_id text,
  verifier_key_ref text,
  created_at timestamptz not null default now(),
  check ((org_id is not null and aggregate_approval_issuer is null and aggregate_approval_ref is null) or (org_id is null and aggregate_approval_issuer is not null and aggregate_approval_ref is not null and aggregate_deidentified))
);

alter table lautowork.automation_librarian_candidates enable row level security;
alter table lautowork.automation_librarian_controls enable row level security;
alter table lautowork.automation_librarian_evidence enable row level security;

create or replace function public.linkautowork_librarian_find_candidate(p_org_id uuid, p_deduplication_key text default null, p_candidate_id uuid default null)
returns setof jsonb language plpgsql security definer set search_path = lautowork, pg_temp as $$
declare v_org uuid;
begin select org_id into v_org from automation_librarian_candidates where (p_deduplication_key is not null and deduplication_key=p_deduplication_key) or (p_candidate_id is not null and id=p_candidate_id) limit 1; if v_org is null then perform lautowork.assert_command_authorized(p_org_id); return; end if; perform lautowork.assert_command_authorized(v_org); if v_org<>p_org_id then raise exception 'candidate organization consistency guard failed'; end if; return query select candidate from automation_librarian_candidates where org_id=v_org and ((p_deduplication_key is not null and deduplication_key=p_deduplication_key) or (p_candidate_id is not null and id=p_candidate_id)) limit 1; end;
$$;

create or replace function public.linkautowork_librarian_save_candidate(p_org_id uuid, p_candidate jsonb)
returns jsonb language plpgsql security definer set search_path = lautowork, pg_temp as $$
begin
  if p_candidate->>'orgId' <> p_org_id::text or p_candidate->>'domain' <> 'automation' then raise exception 'candidate organisation/domain mismatch'; end if;
  perform lautowork.assert_command_authorized((p_candidate->>'orgId')::uuid);
  insert into lautowork.automation_librarian_candidates(id, org_id, deduplication_key, automation_id, status, proposer_ref, candidate)
  values ((p_candidate->>'id')::uuid, p_org_id, p_candidate->>'deduplicationKey', p_candidate#>>'{source,automationId}', p_candidate->>'status', p_candidate->>'proposerId', p_candidate)
  on conflict (org_id, deduplication_key) do update set
    status = case when automation_librarian_candidates.id = excluded.id then excluded.status else automation_librarian_candidates.status end,
    candidate = case when automation_librarian_candidates.id = excluded.id then excluded.candidate else automation_librarian_candidates.candidate end,
    updated_at = case when automation_librarian_candidates.id = excluded.id then now() else automation_librarian_candidates.updated_at end;
  insert into lautowork.automation_domain_audit_events(org_id,event_type,subject_type,subject_id,actor_ref,evidence_ref)
  values (p_org_id,'librarian.' || (p_candidate->>'status'),'improvement_candidate',(p_candidate->>'id')::uuid,p_candidate->>'proposerId',p_candidate#>>'{audit,transitions,-1,reason}');
  return (select candidate from lautowork.automation_librarian_candidates where org_id=p_org_id and deduplication_key=p_candidate->>'deduplicationKey');
end $$;

create or replace function public.linkautowork_librarian_get_control(p_org_id uuid, p_automation_id text)
returns jsonb language plpgsql security definer set search_path = lautowork, pg_temp as $$
begin perform lautowork.assert_command_authorized(p_org_id); return (select jsonb_build_object('enabled',coalesce((select enabled from automation_librarian_controls where org_id=p_org_id and automation_id='*'),true),'paused',coalesce((select not enabled from automation_librarian_controls where org_id=p_org_id and automation_id=p_automation_id),false))); end;
$$;

create or replace function public.linkautowork_librarian_set_control(p_org_id uuid, p_automation_id text, p_enabled boolean)
returns void language plpgsql security definer set search_path = lautowork, pg_temp as $$
begin perform lautowork.assert_command_authorized(p_org_id); insert into lautowork.automation_librarian_controls(org_id,automation_id,enabled) values(p_org_id,p_automation_id,p_enabled) on conflict(org_id,automation_id) do update set enabled=excluded.enabled,updated_at=now(); end $$;

create or replace function public.linkautowork_librarian_resolve_evidence(p_org_id uuid,p_evidence_ref text)
returns setof jsonb language plpgsql security definer set search_path = lautowork, pg_temp as $$
declare v automation_librarian_evidence%rowtype;
begin select * into v from automation_librarian_evidence where evidence_ref=p_evidence_ref; if not found then perform lautowork.assert_command_authorized(p_org_id); return; end if; perform lautowork.assert_command_authorized(coalesce(v.org_id,p_org_id)); if v.org_id is not null and v.org_id<>p_org_id then raise exception 'evidence organization consistency guard failed'; end if; return next jsonb_build_object('ref',v.evidence_ref,'payload',v.payload,'hash',v.payload_hash,'orgId',v.org_id,'aggregateApproval',case when v.org_id is null then jsonb_build_object('issuer',v.aggregate_approval_issuer,'approvalRef',v.aggregate_approval_ref,'deidentified',v.aggregate_deidentified) else null end,'verifierKeyId',v.verifier_key_id,'verifierKeyRef',v.verifier_key_ref); end;
$$;

revoke all on function public.linkautowork_librarian_find_candidate(uuid,text,uuid) from public;
revoke all on function public.linkautowork_librarian_save_candidate(uuid,jsonb) from public;
revoke all on function public.linkautowork_librarian_get_control(uuid,text) from public;
revoke all on function public.linkautowork_librarian_set_control(uuid,text,boolean) from public;
revoke all on function public.linkautowork_librarian_resolve_evidence(uuid,text) from public;
grant execute on function public.linkautowork_librarian_find_candidate(uuid,text,uuid), public.linkautowork_librarian_save_candidate(uuid,jsonb), public.linkautowork_librarian_get_control(uuid,text), public.linkautowork_librarian_set_control(uuid,text,boolean), public.linkautowork_librarian_resolve_evidence(uuid,text) to svc_lautowork_runtime;

commit;

-- migrate:down
begin;
drop function if exists public.linkautowork_librarian_resolve_evidence(uuid,text);
drop function if exists public.linkautowork_librarian_set_control(uuid,text,boolean);
drop function if exists public.linkautowork_librarian_get_control(uuid,text);
drop function if exists public.linkautowork_librarian_save_candidate(uuid,jsonb);
drop function if exists public.linkautowork_librarian_find_candidate(uuid,text,uuid);
drop table if exists lautowork.automation_librarian_evidence;
drop table if exists lautowork.automation_librarian_controls;
drop table if exists lautowork.automation_librarian_candidates;
commit;
