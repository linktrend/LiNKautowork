-- Wave 2 runtime corrections: narrow RPCs, atomic execution acceptance,
-- callback capability binding, and transactional event projections.
-- migrate:up

create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

alter table lautowork.automation_executions
  add column if not exists callback_service text,
  add column if not exists callback_token_digest text check (callback_token_digest is null or callback_token_digest ~ '^sha256:[a-f0-9]{64}$');

create unique index if not exists uq_lautowork_one_active_deployment_per_instance
  on lautowork.automation_deployments (org_id, instance_id)
  where state in ('active', 'canary');
create unique index if not exists uq_lautowork_provisioning_request_ref
  on lautowork.provisioning_requests(org_id, request_ref);

create or replace function public.linkautowork_resolve_bound_instance(
  p_org_id uuid, p_consumer_system text, p_operation text
) returns jsonb language plpgsql security definer set search_path = lautowork, pg_temp as $$
declare result jsonb; target_org uuid;
begin
  perform lautowork.assert_command_authorized(p_org_id);
  select jsonb_build_object(
    'bindingId', b.id, 'orgId', b.org_id, 'automationId', def.automation_id, 'instanceId', i.id,
    'consumerSystem', b.consumer_system, 'operation', b.binding_operation, 'enabled', b.enabled,
    'instanceState', i.state, 'releaseId', r.id, 'releaseLifecycle', r.lifecycle,
    'deploymentId', d.id, 'workflowId', d.n8n_workflow_id,
    'workflowDigest', r.workflow_digest, 'deployedDigest', d.workflow_digest,
    'configurationDigest', i.configuration_digest, 'deployedConfigurationDigest', d.configuration_digest,
    'webhookPath', coalesce(i.configuration->>'webhook_path', '/instance/' || i.id::text),
    'method', coalesce(i.configuration->>'webhook_method', 'POST'),
    'criticality', coalesce(i.configuration->>'criticality', 'non_critical'),
    'timeoutMs', coalesce((i.configuration->>'timeout_ms')::integer, 30000),
    'retryCount', coalesce((i.configuration->>'retry_count')::integer, 0),
    'inputSchema', coalesce(i.configuration->'input_schema', '{"type":"object","additionalProperties":false}'::jsonb),
    'secretRefs', coalesce((select jsonb_agg(s.secret_ref order by s.secret_ref) from lautowork.automation_secret_bindings s where s.org_id=i.org_id and s.instance_id=i.id and s.required), '[]'::jsonb)
  ) into result
  from lautowork.automation_bindings b
  join lautowork.automation_instances i on i.id=b.instance_id and i.org_id=b.org_id
  join lautowork.automation_releases r on r.id=i.release_id and r.org_id=i.org_id
  join lautowork.automation_definitions def on def.id=i.definition_id and def.org_id=i.org_id
  join lautowork.automation_deployments d on d.instance_id=i.id and d.org_id=i.org_id and d.state in ('active','canary')
  where b.org_id=p_org_id and b.consumer_system=p_consumer_system and b.binding_operation=p_operation and b.enabled;
  target_org:=(result->>'orgId')::uuid;
  if target_org is not null then perform lautowork.assert_command_authorized(target_org); end if;
  return result;
end $$;

create or replace function public.linkautowork_accept_execution(
  p_execution_id uuid, p_org_id uuid, p_instance_id uuid, p_release_id uuid,
  p_deployment_id uuid, p_idempotency_key text, p_input_digest text,
  p_callback_service text, p_callback_token_digest text
) returns jsonb language plpgsql security definer set search_path = lautowork, pg_temp as $$
declare existing_id uuid; existing_digest text; target_org uuid; inserted boolean := false;
begin
  select org_id into strict target_org from lautowork.automation_instances where id=p_instance_id;
  if target_org<>p_org_id then raise exception 'requested organization does not match instance organization'; end if;
  perform lautowork.assert_command_authorized(target_org);
  insert into lautowork.automation_executions
      (id,org_id,instance_id,release_id,deployment_id,idempotency_key,status,input_digest,callback_service,callback_token_digest)
    values (p_execution_id,p_org_id,p_instance_id,p_release_id,p_deployment_id,p_idempotency_key,'accepted',p_input_digest,p_callback_service,p_callback_token_digest)
    on conflict(org_id,instance_id,idempotency_key) do nothing returning id,input_digest into existing_id,existing_digest;
  if existing_id is not null then
    insert into lautowork.automation_execution_events(org_id,execution_id,sequence,event_type,occurred_at,payload_digest)
      values(p_org_id,p_execution_id,1,'accepted',now(),p_input_digest);
    inserted := true;
  else
    select id,input_digest into strict existing_id,existing_digest from lautowork.automation_executions where org_id=p_org_id and instance_id=p_instance_id and idempotency_key=p_idempotency_key;
    if existing_digest is distinct from p_input_digest then raise exception 'idempotency key was reused with different input'; end if;
  end if;
  return jsonb_build_object('executionId',existing_id,'status','accepted','correlationId',existing_id,'duplicate',not inserted);
end $$;

create or replace function public.linkautowork_record_execution_callback(
  p_org_id uuid, p_execution_id uuid, p_callback_service text, p_callback_token text,
  p_sequence integer, p_event_type text, p_occurred_at timestamptz,
  p_payload_digest text default null, p_evidence_ref text default null
) returns jsonb language plpgsql security definer set search_path = lautowork, extensions, pg_temp as $$
declare ex lautowork.automation_executions%rowtype; prior lautowork.automation_execution_events%rowtype; last_seq integer; disposition text := 'applied';
begin
  select * into strict ex from lautowork.automation_executions where id=p_execution_id for update;
  perform lautowork.assert_command_authorized(ex.org_id);
  if ex.org_id<>p_org_id or ex.callback_service<>p_callback_service or ex.callback_token_digest<>('sha256:'||encode(digest(convert_to(p_callback_token,'UTF8'),'sha256'),'hex')) then
    raise exception 'execution callback capability denied';
  end if;
  select * into prior from lautowork.automation_execution_events where execution_id=p_execution_id and sequence=p_sequence;
  if found then
    if prior.event_type=p_event_type and prior.occurred_at=p_occurred_at and prior.payload_digest is not distinct from p_payload_digest and prior.evidence_ref is not distinct from p_evidence_ref then disposition:='duplicate';
    else raise exception 'conflicting execution callback sequence'; end if;
  else
    select coalesce(max(sequence),0) into last_seq from lautowork.automation_execution_events where execution_id=p_execution_id;
    if p_sequence<>last_seq+1 then
      disposition:='out_of_order';
      insert into lautowork.automation_domain_audit_events(org_id,event_type,subject_type,subject_id,actor_ref,evidence_ref)
        values(p_org_id,'execution.callback_out_of_order','automation_execution',p_execution_id,p_callback_service,p_evidence_ref);
    else
      if ex.status='accepted' and p_event_type<>'started' then raise exception 'accepted execution must start first'; end if;
      if ex.status in ('succeeded','failed','cancelled','timed_out') then raise exception 'execution is already terminal'; end if;
      insert into lautowork.automation_execution_events(org_id,execution_id,sequence,event_type,occurred_at,payload_digest,evidence_ref)
        values(p_org_id,p_execution_id,p_sequence,p_event_type,p_occurred_at,p_payload_digest,p_evidence_ref);
      update lautowork.automation_executions set status=case when p_event_type='checkpoint' then status else p_event_type end,
        completed_at=case when p_event_type in ('succeeded','failed','cancelled','timed_out') then p_occurred_at else completed_at end,
        output_digest=case when p_event_type='succeeded' then p_payload_digest else output_digest end,
        evidence_ref=coalesce(p_evidence_ref,evidence_ref)
      where id=p_execution_id;
    end if;
  end if;
  select coalesce(max(sequence),0) into last_seq from lautowork.automation_execution_events where execution_id=p_execution_id;
  select * into ex from lautowork.automation_executions where id=p_execution_id;
  return jsonb_build_object('disposition',disposition,'projection',jsonb_build_object('orgId',ex.org_id,'executionId',ex.id,'status',ex.status,'lastSequence',last_seq,'acceptedAt',ex.accepted_at,'completedAt',ex.completed_at,'evidenceRef',ex.evidence_ref));
end $$;

create or replace function public.linkautowork_begin_provisioning(p_org_id uuid, p_request_ref text)
returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare pr lautowork.provisioning_requests%rowtype; inst lautowork.automation_instances%rowtype; rel lautowork.automation_releases%rowtype; dep lautowork.automation_deployments%rowtype;
begin
  perform lautowork.assert_command_authorized(p_org_id);
  select * into pr from lautowork.provisioning_requests where org_id=p_org_id and request_ref=p_request_ref for update;
  if not found then return null; end if;
  perform lautowork.assert_command_authorized(pr.org_id);
  select * into strict inst from lautowork.automation_instances where id=pr.instance_id and org_id=pr.org_id;
  select * into strict rel from lautowork.automation_releases where id=pr.requested_release_id and org_id=pr.org_id;
  if rel.lifecycle<>'certified' then raise exception 'only certified releases may be provisioned'; end if;
  if pr.status='completed' then select * into dep from lautowork.automation_deployments where org_id=pr.org_id and instance_id=pr.instance_id and state='active';
  elsif pr.status in ('requested','failed','awaiting_configuration') then
    update lautowork.provisioning_requests set status='provisioning' where id=pr.id; pr.status:='provisioning';
    insert into lautowork.provisioning_steps(org_id,request_id,step_key,status) values(pr.org_id,pr.id,'workflow-copy','running') on conflict(request_id,step_key) do update set status='running',completed_at=null;
  else raise exception 'provisioning request is already locked in state %',pr.status; end if;
  return jsonb_build_object('requestId',pr.id,'orgId',pr.org_id,'instanceId',pr.instance_id,'releaseId',pr.requested_release_id,'requestRef',pr.request_ref,
    'sourceWorkflowId',inst.configuration->>'source_workflow_id','workflowDigest',rel.workflow_digest,'configurationDigest',inst.configuration_digest,'status',pr.status,
    'environment',coalesce(inst.configuration->>'environment','production'),
    'deploymentId',dep.id,'workflowId',dep.n8n_workflow_id);
end $$;

create or replace function public.linkautowork_create_provisioning_deployment(p_request_id uuid,p_workflow_id text)
returns uuid language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare pr lautowork.provisioning_requests%rowtype; inst lautowork.automation_instances%rowtype; rel lautowork.automation_releases%rowtype; result uuid;
begin
  select * into strict pr from lautowork.provisioning_requests where id=p_request_id and status='provisioning' for update;
  perform lautowork.assert_command_authorized(pr.org_id);
  select * into strict inst from lautowork.automation_instances where id=pr.instance_id and org_id=pr.org_id;
  select * into strict rel from lautowork.automation_releases where id=pr.requested_release_id and org_id=pr.org_id;
  if exists(select 1 from lautowork.automation_deployments where org_id=pr.org_id and instance_id=pr.instance_id and state in ('active','canary')) then raise exception 'instance already has an active deployment'; end if;
  insert into lautowork.automation_deployments(org_id,instance_id,release_id,environment,n8n_workflow_id,workflow_digest,configuration_digest,state)
    values(pr.org_id,pr.instance_id,pr.requested_release_id,coalesce(inst.configuration->>'environment','production'),p_workflow_id,rel.workflow_digest,inst.configuration_digest,'provisioning') returning id into result;
  update lautowork.provisioning_steps set status='completed',completed_at=now(),evidence_ref='evidence://provisioning/workflow-copy/'||result where request_id=pr.id and step_key='workflow-copy';
  insert into lautowork.provisioning_steps(org_id,request_id,step_key,status) values(pr.org_id,pr.id,'pre-activation-smoke','running') on conflict(request_id,step_key) do update set status='running',completed_at=null;
  return result;
end $$;

create or replace function public.linkautowork_mark_provisioning(p_request_id uuid,p_status text,p_fields jsonb default '{}'::jsonb)
returns void language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare pr lautowork.provisioning_requests%rowtype; dep_id uuid;
begin
  if p_status not in ('provisioning','completed','failed') then raise exception 'unsupported provisioning state'; end if;
  if exists(select 1 from jsonb_object_keys(p_fields) as k(key) where key not in ('deploymentId','workflowId','workflowDigest')) then raise exception 'unsupported provisioning evidence field'; end if;
  select * into strict pr from lautowork.provisioning_requests where id=p_request_id for update;
  perform lautowork.assert_command_authorized(pr.org_id);
  dep_id:=nullif(p_fields->>'deploymentId','')::uuid;
  if p_status='completed' then
    update lautowork.automation_deployments set state='active',deployed_at=now() where id=dep_id and org_id=pr.org_id and instance_id=pr.instance_id and state='provisioning';
    if not found then raise exception 'provisioning deployment is missing or not activatable'; end if;
    update lautowork.automation_instances set state='active',updated_at=now() where id=pr.instance_id and org_id=pr.org_id;
    update lautowork.provisioning_steps set status='completed',completed_at=now(),evidence_ref='evidence://provisioning/smoke/'||dep_id where request_id=pr.id and step_key='pre-activation-smoke';
    update lautowork.provisioning_requests set status='completed',completed_at=now() where id=pr.id;
  elsif p_status='failed' then
    update lautowork.automation_deployments set state='failed' where org_id=pr.org_id and instance_id=pr.instance_id and state='provisioning';
    update lautowork.automation_instances set state='failed',updated_at=now() where id=pr.instance_id and org_id=pr.org_id;
    update lautowork.provisioning_steps set status='failed',completed_at=now() where request_id=pr.id and status='running';
    update lautowork.provisioning_requests set status='failed' where id=pr.id;
  end if;
end $$;

revoke all on function public.linkautowork_resolve_bound_instance(uuid,text,text) from public;
revoke all on function public.linkautowork_accept_execution(uuid,uuid,uuid,uuid,uuid,text,text,text,text) from public;
revoke all on function public.linkautowork_record_execution_callback(uuid,uuid,text,text,integer,text,timestamptz,text,text) from public;
revoke all on function public.linkautowork_begin_provisioning(uuid,text) from public;
revoke all on function public.linkautowork_create_provisioning_deployment(uuid,text) from public;
revoke all on function public.linkautowork_mark_provisioning(uuid,text,jsonb) from public;
do $$ declare role_name text; begin
  foreach role_name in array array['service_role','svc_lautowork_runtime'] loop
    if exists(select 1 from pg_roles where rolname=role_name) then
      execute format('grant execute on function public.linkautowork_resolve_bound_instance(uuid,text,text) to %I',role_name);
      execute format('grant execute on function public.linkautowork_accept_execution(uuid,uuid,uuid,uuid,uuid,text,text,text,text) to %I',role_name);
      execute format('grant execute on function public.linkautowork_record_execution_callback(uuid,uuid,text,text,integer,text,timestamptz,text,text) to %I',role_name);
      execute format('grant execute on function public.linkautowork_begin_provisioning(uuid,text) to %I',role_name);
      execute format('grant execute on function public.linkautowork_create_provisioning_deployment(uuid,text) to %I',role_name);
      execute format('grant execute on function public.linkautowork_mark_provisioning(uuid,text,jsonb) to %I',role_name);
    end if;
  end loop;
end $$;

-- migrate:down
drop function if exists public.linkautowork_record_execution_callback(uuid,uuid,text,text,integer,text,timestamptz,text,text);
drop function if exists public.linkautowork_accept_execution(uuid,uuid,uuid,uuid,uuid,text,text,text,text);
drop function if exists public.linkautowork_resolve_bound_instance(uuid,text,text);
drop function if exists public.linkautowork_mark_provisioning(uuid,text,jsonb);
drop function if exists public.linkautowork_create_provisioning_deployment(uuid,text);
drop function if exists public.linkautowork_begin_provisioning(uuid,text);
drop index if exists lautowork.uq_lautowork_provisioning_request_ref;
drop index if exists lautowork.uq_lautowork_one_active_deployment_per_instance;
alter table lautowork.automation_executions drop column if exists callback_token_digest, drop column if exists callback_service;
