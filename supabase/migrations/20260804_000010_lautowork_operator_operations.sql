-- Wave 3 blocker 2: durable operator read models and bounded actions.
--
-- The Product API keeps its finite operator routes and calls the two frozen
-- RPC names.  This migration replaces their empty-façade implementation with
-- explicit mappings to the existing control tables and state machines.  It
-- does not expose a table, SQL, workflow, or secret proxy.
-- migrate:up

create index if not exists idx_lautowork_product_resource_history_resource
  on lautowork.product_resource_transition_history(org_id, resource, resource_id, created_at desc);

create or replace function lautowork.operator_resource_version(p_org_id uuid, p_resource text, p_resource_id text)
returns integer
language sql
stable
set search_path = lautowork, pg_temp
as $$
  select 1 + count(*)::integer
  from lautowork.product_resource_transition_history
  where org_id = p_org_id and resource = p_resource and resource_id = p_resource_id;
$$;

create or replace function lautowork.operator_records_packages(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', d.id, 'orgId', d.org_id, 'state', coalesce(d.lifecycle, 'unreleased'),
    'status', d.classification, 'version', lautowork.operator_resource_version(d.org_id, 'packages', d.id::text),
    'summary', d.display_name || ' — ' || d.summary, 'updatedAt', d.created_at
  ) order by d.created_at desc), '[]'::jsonb)
  from (
    select d.id, d.org_id, d.display_name, d.summary, d.classification, d.created_at, r.lifecycle
    from lautowork.automation_definitions d
    left join lateral (select lifecycle from lautowork.automation_releases where org_id = d.org_id and definition_id = d.id order by created_at desc limit 1) r on true
    order by d.created_at desc offset p_offset limit p_limit
  ) d;
$$;

create or replace function lautowork.operator_records_releases(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', r.id, 'orgId', r.org_id, 'state', r.lifecycle, 'status', r.channel,
    'version', lautowork.operator_resource_version(r.org_id, 'releases', r.id::text),
    'summary', r.display_name || ' ' || r.version, 'evidenceRef', r.package_path, 'updatedAt', r.created_at
  ) order by r.created_at desc), '[]'::jsonb)
  from (
    select r.id, r.org_id, r.lifecycle, r.channel, r.version, r.package_path, r.created_at, d.display_name
    from lautowork.automation_releases r join lautowork.automation_definitions d on d.id = r.definition_id and d.org_id = r.org_id
    order by r.created_at desc offset p_offset limit p_limit
  ) r;
$$;

create or replace function lautowork.operator_records_certification(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', e.id, 'orgId', e.org_id, 'state', e.status, 'status', e.lifecycle,
    'version', lautowork.operator_resource_version(e.org_id, 'certification', e.id::text),
    'summary', 'Evaluation by ' || e.evaluator_ref, 'evidenceRef', e.receipt_ref, 'updatedAt', coalesce(e.completed_at, e.started_at)
  ) order by coalesce(e.completed_at, e.started_at) desc), '[]'::jsonb)
  from (
    select e.id, e.org_id, e.status, e.evaluator_ref, e.receipt_ref, e.completed_at, e.started_at, r.lifecycle
    from lautowork.automation_eval_runs e join lautowork.automation_releases r on r.id = e.release_id and r.org_id = e.org_id
    order by coalesce(e.completed_at, e.started_at) desc offset p_offset limit p_limit
  ) e;
$$;

create or replace function lautowork.operator_records_products(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', p.id, 'orgId', p.org_id, 'state', p.status, 'status', p.offering_key,
    'version', 1, 'summary', p.display_name, 'updatedAt', p.created_at
  ) order by p.created_at desc), '[]'::jsonb)
  from (select * from lautowork.automation_products order by created_at desc offset p_offset limit p_limit) p;
$$;

create or replace function lautowork.operator_records_organisations(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, platform, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', o.id, 'orgId', o.id, 'state', 'active', 'status', o.slug, 'version', 1,
    'summary', 'Organisation ' || o.slug
  ) order by o.slug), '[]'::jsonb)
  from (select * from platform.organizations order by slug offset p_offset limit p_limit) o;
$$;

create or replace function lautowork.operator_records_subscriptions(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', s.id, 'orgId', s.org_id, 'state', s.status, 'status', s.status, 'version', 1,
    'summary', 'Order ' || s.order_id::text, 'updatedAt', s.updated_at
  ) order by s.updated_at desc), '[]'::jsonb)
  from (select * from lautowork.product_subscriptions order by updated_at desc offset p_offset limit p_limit) s;
$$;

create or replace function lautowork.operator_records_provisioning_jobs(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', p.id, 'orgId', p.org_id, 'state', p.status, 'status', p.status,
    'version', lautowork.operator_resource_version(p.org_id, 'provisioning-jobs', p.id::text),
    'summary', 'Provision instance ' || p.instance_id::text, 'evidenceRef', s.evidence_ref, 'updatedAt', p.created_at
  ) order by p.created_at desc), '[]'::jsonb)
  from (select * from lautowork.provisioning_requests order by created_at desc offset p_offset limit p_limit) p
  left join lateral (
    select evidence_ref from lautowork.provisioning_steps where org_id = p.org_id and request_id = p.id
    order by created_at desc limit 1
  ) s on true;
$$;

create or replace function lautowork.operator_records_instances(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', i.id, 'orgId', i.org_id, 'state', i.state,
    'status', coalesce((select d.state from lautowork.automation_deployments d where d.org_id = i.org_id and d.instance_id = i.id order by d.created_at desc limit 1), 'not_deployed'),
    'version', lautowork.operator_resource_version(i.org_id, 'instances', i.id::text),
    'summary', i.instance_key, 'updatedAt', i.updated_at,
    'health', coalesce((select h.health_state from lautowork.automation_health_snapshots h where h.org_id = i.org_id and h.instance_id = i.id order by h.observed_at desc limit 1), 'unknown')
  ) order by i.updated_at desc), '[]'::jsonb)
  from (select * from lautowork.automation_instances order by updated_at desc offset p_offset limit p_limit) i;
$$;

create or replace function lautowork.operator_records_bindings(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', b.id, 'orgId', b.org_id, 'state', case when b.enabled then 'enabled' else 'paused' end,
    'status', b.consumer_system, 'version', lautowork.operator_resource_version(b.org_id, 'bindings', b.id::text),
    'summary', b.binding_operation, 'updatedAt', b.created_at
  ) order by b.created_at desc), '[]'::jsonb)
  from (select * from lautowork.automation_bindings order by created_at desc offset p_offset limit p_limit) b;
$$;

create or replace function lautowork.operator_records_deployments(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', d.id, 'orgId', d.org_id, 'state', d.state, 'status', d.environment,
    'version', lautowork.operator_resource_version(d.org_id, 'deployments', d.id::text),
    'summary', 'Release ' || d.release_id::text || ' / workflow ' || d.n8n_workflow_id,
    'updatedAt', d.created_at
  ) order by d.created_at desc), '[]'::jsonb)
  from (select * from lautowork.automation_deployments order by created_at desc offset p_offset limit p_limit) d;
$$;

create or replace function lautowork.operator_records_executions(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', e.id, 'orgId', e.org_id, 'state', e.status, 'status', e.failure_class,
    'version', 1, 'summary', 'Execution for instance ' || e.instance_id::text,
    'evidenceRef', e.evidence_ref, 'updatedAt', coalesce(e.completed_at, e.accepted_at),
    'retryCount', e.retry_count, 'latencyMs', e.latency_ms
  ) order by coalesce(e.completed_at, e.accepted_at) desc), '[]'::jsonb)
  from (select * from lautowork.automation_executions order by coalesce(completed_at, accepted_at) desc offset p_offset limit p_limit) e;
$$;

create or replace function lautowork.operator_records_health(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', h.id, 'orgId', h.org_id, 'state', h.health_state, 'status', h.health_state, 'version', 1,
    'summary', 'Health for instance ' || h.instance_id::text, 'evidenceRef', h.summary_ref, 'updatedAt', h.observed_at
  ) order by h.observed_at desc), '[]'::jsonb)
  from (select * from lautowork.automation_health_snapshots order by observed_at desc offset p_offset limit p_limit) h;
$$;

create or replace function lautowork.operator_records_incidents(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', i.id, 'orgId', i.org_id, 'state', i.status, 'status', i.severity,
    'version', lautowork.operator_resource_version(i.org_id, 'incidents', i.id::text),
    'summary', 'Incident ' || i.incident_key, 'updatedAt', i.opened_at
  ) order by i.opened_at desc), '[]'::jsonb)
  from (select * from lautowork.automation_incidents order by opened_at desc offset p_offset limit p_limit) i;
$$;

create or replace function lautowork.operator_records_maintenance(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', m.id, 'orgId', m.org_id, 'state', m.status, 'status', m.classification,
    'version', lautowork.operator_resource_version(m.org_id, 'maintenance', m.id::text),
    'summary', 'Maintenance for instance ' || m.instance_id::text, 'updatedAt', m.opened_at
  ) order by m.opened_at desc), '[]'::jsonb)
  from (select * from lautowork.maintenance_cases order by opened_at desc offset p_offset limit p_limit) m;
$$;

create or replace function lautowork.operator_records_librarian_candidates(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', c.id, 'orgId', c.org_id, 'state', c.status, 'status', c.automation_id,
    'version', lautowork.operator_resource_version(c.org_id, 'librarian-candidates', c.id::text),
    'summary', coalesce(nullif(c.candidate->>'summary', ''), 'Librarian candidate from ' || c.proposer_ref),
    'evidenceRef', c.candidate#>>'{audit,transitions,-1,evidenceRef}', 'updatedAt', c.updated_at,
    'proposerRef', c.proposer_ref
  ) order by c.updated_at desc), '[]'::jsonb)
  from (select * from lautowork.automation_librarian_candidates order by updated_at desc offset p_offset limit p_limit) c;
$$;

create or replace function lautowork.operator_records_audit_evidence(p_limit integer, p_offset integer)
returns jsonb language sql stable security definer set search_path = lautowork, pg_temp as $$
  select coalesce(jsonb_agg(x.item order by x.created_at desc), '[]'::jsonb)
  from (
    select jsonb_build_object('id', a.id::text, 'orgId', a.org_id, 'state', a.event_type, 'status', a.subject_type,
      'version', 1, 'summary', 'Domain audit: ' || a.event_type, 'evidenceRef', a.evidence_ref, 'updatedAt', a.created_at) item, a.created_at
    from lautowork.automation_domain_audit_events a
    union all
    select jsonb_build_object('id', p.id::text, 'orgId', p.org_id, 'state', p.outcome, 'status', p.resource,
      'version', 1, 'summary', 'Product API audit: ' || p.action, 'evidenceRef', p.correlation_id, 'updatedAt', p.created_at) item, p.created_at
    from lautowork.product_api_audit_events p
    order by created_at desc offset p_offset limit p_limit
  ) x;
$$;

drop function if exists public.linkautowork_product_operator_records(text, integer, text);
create or replace function public.linkautowork_product_operator_records(p_resource text, p_limit integer, p_cursor text)
returns jsonb language plpgsql security definer set search_path = lautowork, pg_temp as $$
declare v_offset integer := coalesce(nullif(p_cursor, '')::integer, 0); v_items jsonb;
begin
  if p_resource not in ('packages','releases','certification','products','organisations','subscriptions','provisioning-jobs','instances','bindings','deployments','executions','health','incidents','maintenance','librarian-candidates','audit-evidence') then raise exception 'unknown operator resource'; end if;
  if p_limit < 1 or p_limit > 100 or v_offset < 0 then raise exception 'invalid cursor'; end if;
  v_items := case p_resource
    when 'packages' then lautowork.operator_records_packages(p_limit, v_offset)
    when 'releases' then lautowork.operator_records_releases(p_limit, v_offset)
    when 'certification' then lautowork.operator_records_certification(p_limit, v_offset)
    when 'products' then lautowork.operator_records_products(p_limit, v_offset)
    when 'organisations' then lautowork.operator_records_organisations(p_limit, v_offset)
    when 'subscriptions' then lautowork.operator_records_subscriptions(p_limit, v_offset)
    when 'provisioning-jobs' then lautowork.operator_records_provisioning_jobs(p_limit, v_offset)
    when 'instances' then lautowork.operator_records_instances(p_limit, v_offset)
    when 'bindings' then lautowork.operator_records_bindings(p_limit, v_offset)
    when 'deployments' then lautowork.operator_records_deployments(p_limit, v_offset)
    when 'executions' then lautowork.operator_records_executions(p_limit, v_offset)
    when 'health' then lautowork.operator_records_health(p_limit, v_offset)
    when 'incidents' then lautowork.operator_records_incidents(p_limit, v_offset)
    when 'maintenance' then lautowork.operator_records_maintenance(p_limit, v_offset)
    when 'librarian-candidates' then lautowork.operator_records_librarian_candidates(p_limit, v_offset)
    when 'audit-evidence' then lautowork.operator_records_audit_evidence(p_limit, v_offset)
  end;
  return jsonb_build_object('items', coalesce(v_items, '[]'::jsonb));
end $$;

drop function if exists public.linkautowork_product_operator_action(text, uuid, text, text, text, integer);
create or replace function public.linkautowork_product_operator_action(
  p_resource text, p_id uuid, p_action text, p_reason text, p_idempotency_key text,
  p_expected_version integer, p_actor text
)
returns jsonb language plpgsql security definer set search_path = lautowork, pg_temp as $$
declare
  v_org uuid; v_from text; v_to text; v_current integer; v_result jsonb; v_evidence text := 'evidence://product-api/operator/' || p_idempotency_key;
  v_deployment_id uuid; v_transition jsonb; v_release_id uuid; v_approval_ref text; v_instance_id uuid; v_candidate jsonb;
begin
  if char_length(coalesce(p_reason, '')) < 3 or char_length(coalesce(p_idempotency_key, '')) < 8 then raise exception 'invalid operator action metadata'; end if;
  if p_resource = 'packages' or p_resource = 'products' or p_resource = 'executions' or p_resource = 'health' or p_resource = 'audit-evidence' then raise exception 'operator action is not supported for this read-only resource'; end if;
  if p_resource = 'certification' and p_action <> 'approve' then raise exception 'invalid transition'; end if;
  if p_resource = 'organisations' and p_action not in ('pause','resume') then raise exception 'invalid transition'; end if;
  if p_resource = 'subscriptions' and p_action <> 'compensate' then raise exception 'invalid transition'; end if;
  if p_resource = 'provisioning-jobs' and p_action <> 'retry' then raise exception 'invalid transition'; end if;
  if p_resource = 'instances' and p_action not in ('pause','resume') then raise exception 'invalid transition'; end if;
  if p_resource = 'bindings' and p_action not in ('pause','resume') then raise exception 'invalid transition'; end if;
  if p_resource = 'deployments' and p_action not in ('canary','promote','rollback') then raise exception 'invalid transition'; end if;
  if p_resource = 'incidents' and p_action not in ('acknowledge','resolve') then raise exception 'invalid transition'; end if;
  if p_resource = 'maintenance' and p_action not in ('retry','resolve') then raise exception 'invalid transition'; end if;
  if p_resource = 'librarian-candidates' and p_action not in ('approve','reject','supersede') then raise exception 'invalid transition'; end if;

  case p_resource
    when 'certification' then select org_id, release_id into v_org, v_release_id from automation_eval_runs where id = p_id;
    when 'organisations' then select id into v_org from platform.organizations where id = p_id;
    when 'subscriptions' then select org_id into v_org from product_subscriptions where id = p_id;
    when 'provisioning-jobs' then select org_id into v_org from provisioning_requests where id = p_id;
    when 'instances' then select org_id into v_org from automation_instances where id = p_id;
    when 'bindings' then select org_id into v_org from automation_bindings where id = p_id;
    when 'deployments' then select org_id, instance_id, release_id into v_org, v_instance_id, v_release_id from automation_deployments where id = p_id;
    when 'incidents' then select org_id into v_org from automation_incidents where id = p_id;
    when 'maintenance' then select org_id, instance_id into v_org, v_instance_id from maintenance_cases where id = p_id;
    when 'librarian-candidates' then select org_id, candidate into v_org, v_candidate from automation_librarian_candidates where id = p_id;
  end case;
  if v_org is null then raise exception 'not_found'; end if;

  perform set_config('request.headers', jsonb_build_object('x-link-org-id', v_org::text)::text, true);
  perform set_config('request.jwt.claims', jsonb_build_object('role','service_role','org_id',v_org::text,'sub',p_actor)::text, true);
  perform set_config('request.jwt.claim.org_id', v_org::text, true);
  perform set_config('request.jwt.claim.role', 'service_role', true);

  select to_state into v_to from product_resource_transition_history where org_id = v_org and resource = p_resource and idempotency_key = p_idempotency_key;
  if v_to is not null then
    return jsonb_build_object('id', p_id, 'orgId', v_org, 'state', v_to, 'status', v_to,
      'version', lautowork.operator_resource_version(v_org, p_resource, p_id::text), 'summary', 'Idempotent operator action replay', 'evidenceRef', v_evidence);
  end if;
  v_current := lautowork.operator_resource_version(v_org, p_resource, p_id::text);
  if p_expected_version is not null and p_expected_version <> v_current then raise exception 'concurrency_conflict'; end if;

  if p_resource = 'certification' then
    perform public.linkautowork_certify_automation_release(v_org, v_release_id, p_actor, p_reason);
    v_from := 'eval_pending'; v_to := 'certified';
  elsif p_resource = 'organisations' then
    insert into automation_pause_controls(org_id, scope, active, actor_ref, reason, evidence_ref)
      values (v_org, 'organisation', p_action = 'pause', p_actor, p_reason, v_evidence);
    v_from := case when p_action = 'pause' then 'active' else 'paused' end; v_to := case when p_action = 'pause' then 'paused' else 'active' end;
  elsif p_resource = 'subscriptions' then
    v_result := public.linkautowork_product_compensate_provisioning(p_id, p_reason, p_idempotency_key);
    v_from := 'provisioning'; v_to := coalesce(v_result->>'status', 'compensation_pending');
  elsif p_resource = 'provisioning-jobs' then
    select status, request_ref into v_from, v_evidence from provisioning_requests where id = p_id for update;
    if v_from not in ('requested','failed','awaiting_configuration') then raise exception 'invalid_transition'; end if;
    v_result := public.linkautowork_begin_provisioning(v_org, v_evidence);
    v_to := coalesce(v_result->>'status', 'provisioning'); v_evidence := 'evidence://product-api/operator/' || p_idempotency_key;
  elsif p_resource = 'instances' then
    select state into v_from from automation_instances where id = p_id and org_id = v_org for update;
    if (p_action = 'pause' and v_from not in ('ready','active')) or (p_action = 'resume' and v_from <> 'paused') then raise exception 'invalid_transition'; end if;
    v_to := case when p_action = 'pause' then 'paused' else 'active' end;
    update automation_instances set state = v_to, updated_at = now() where id = p_id and org_id = v_org;
  elsif p_resource = 'bindings' then
    select case when enabled then 'enabled' else 'paused' end into v_from from automation_bindings where id = p_id and org_id = v_org for update;
    v_to := case when p_action = 'pause' then 'paused' else 'enabled' end;
    update automation_bindings set enabled = p_action = 'resume' where id = p_id and org_id = v_org;
  elsif p_resource = 'deployments' then
    select state into v_from from automation_deployments where id = p_id and org_id = v_org for update;
    if (p_action = 'canary' and v_from <> 'planned') or (p_action = 'promote' and v_from <> 'canary') or (p_action = 'rollback' and v_from not in ('active','canary')) then raise exception 'invalid_transition'; end if;
    v_transition := public.linkautowork_prepare_deployment_transition(jsonb_build_object('orgId',v_org,'deploymentId',p_id,'action',p_action,'idempotencyKey',p_idempotency_key,'actor',p_actor,'reason',p_reason));
    if v_transition->>'disposition' = 'prepared' then
      perform public.linkautowork_commit_deployment_transition(v_org, (v_transition->>'transitionId')::uuid,
        jsonb_build_object('id',gen_random_uuid(),'evidenceDigest','sha256:' || encode(extensions.digest(convert_to(v_evidence,'UTF8'),'sha256'),'hex')));
    end if;
    select state into v_to from automation_deployments where id = p_id and org_id = v_org;
  elsif p_resource = 'incidents' then
    select status into v_from from automation_incidents where id = p_id and org_id = v_org for update;
    if (p_action = 'acknowledge' and v_from <> 'open') or (p_action = 'resolve' and v_from not in ('open','acknowledged','investigating','mitigated')) then raise exception 'invalid_transition'; end if;
    v_to := case when p_action = 'acknowledge' then 'acknowledged' else 'resolved' end;
    perform public.linkautowork_transition_incident(jsonb_build_object('orgId',v_org,'incidentId',p_id,'status',v_to,'actor',p_actor,'evidenceRef',v_evidence));
  elsif p_resource = 'maintenance' then
    select status into v_from from maintenance_cases where id = p_id and org_id = v_org for update;
    if p_action = 'retry' then
      select ad.evidence_ref into v_approval_ref from approval_requests ar join approval_decisions ad on ad.approval_request_id = ar.id and ad.org_id = ar.org_id where ar.org_id = v_org and ar.subject_type = 'maintenance' and ar.subject_id = v_instance_id and ar.status = 'approved' and ad.decision = 'approved' order by ad.created_at desc limit 1;
      if v_approval_ref is null then raise exception 'maintenance action requires approved evidence'; end if;
      perform public.linkautowork_execute_retry(v_org, v_instance_id, v_approval_ref); v_to := 'investigating';
      insert into maintenance_case_events(org_id, maintenance_case_id, action, actor_ref, before_state_ref, after_state_ref, evidence_ref) values(v_org,p_id,'retry',p_actor,v_from,v_to,v_evidence);
      update maintenance_cases set status = v_to where id = p_id and org_id = v_org;
    else
      if v_from not in ('open','investigating','mitigated','awaiting_approval') then raise exception 'invalid_transition'; end if;
      v_to := 'resolved'; update maintenance_cases set status = v_to, closed_at = now() where id = p_id and org_id = v_org;
      insert into maintenance_case_events(org_id, maintenance_case_id, action, actor_ref, before_state_ref, after_state_ref, evidence_ref) values(v_org,p_id,'resolved',p_actor,v_from,v_to,v_evidence);
    end if;
  elsif p_resource = 'librarian-candidates' then
    select status into v_from from automation_librarian_candidates where id = p_id and org_id = v_org for update;
    if p_action = 'approve' and v_from <> 'awaiting_review' then raise exception 'invalid_transition'; end if;
    if p_action = 'reject' and v_from not in ('proposed','validation_failed','ready_for_eval','eval_failed','awaiting_review') then raise exception 'invalid_transition'; end if;
    if p_action = 'supersede' and v_from <> 'approved' then raise exception 'invalid_transition'; end if;
    v_to := case p_action when 'approve' then 'approved' when 'reject' then 'rejected' else 'superseded' end;
    update automation_librarian_candidates set status = v_to, updated_at = now() where id = p_id and org_id = v_org;
  end if;

  insert into product_resource_transition_history(org_id, resource, resource_id, action, actor_ref, reason, idempotency_key, expected_version, from_state, to_state, correlation_ref)
    values(v_org, p_resource, p_id::text, p_action, p_actor, p_reason, p_idempotency_key, p_expected_version, v_from, v_to, v_evidence);
  insert into automation_domain_audit_events(org_id, event_type, subject_type, subject_id, actor_ref, evidence_ref)
    values(v_org, 'operator.' || p_resource || '.' || p_action, p_resource, p_id, p_actor, v_evidence);
  return jsonb_build_object('id',p_id,'orgId',v_org,'state',v_to,'status',v_to,'version',v_current + 1,
    'summary','Operator action completed: ' || p_action,'evidenceRef',v_evidence);
end $$;

do $$ declare f record; begin
  for f in select p.oid::regprocedure sig from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and (p.proname = 'linkautowork_product_operator_records' or p.proname = 'linkautowork_product_operator_action')
  loop execute format('revoke all on function %s from public', f.sig); end loop;
  grant execute on function public.linkautowork_product_operator_records(text,integer,text) to service_role, svc_lautowork_runtime;
  grant execute on function public.linkautowork_product_operator_action(text,uuid,text,text,text,integer,text) to service_role, svc_lautowork_runtime;
  for f in select p.oid::regprocedure sig from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'lautowork' and (p.proname = 'operator_resource_version' or p.proname like 'operator_records_%') loop
    execute format('revoke all on function %s from public', f.sig);
  end loop;
end $$;

-- migrate:down
drop function if exists public.linkautowork_product_operator_action(text,uuid,text,text,text,integer,text);
drop function if exists lautowork.operator_records_audit_evidence(integer,integer);
drop function if exists lautowork.operator_records_librarian_candidates(integer,integer);
drop function if exists lautowork.operator_records_maintenance(integer,integer);
drop function if exists lautowork.operator_records_incidents(integer,integer);
drop function if exists lautowork.operator_records_health(integer,integer);
drop function if exists lautowork.operator_records_executions(integer,integer);
drop function if exists lautowork.operator_records_deployments(integer,integer);
drop function if exists lautowork.operator_records_bindings(integer,integer);
drop function if exists lautowork.operator_records_instances(integer,integer);
drop function if exists lautowork.operator_records_provisioning_jobs(integer,integer);
drop function if exists lautowork.operator_records_subscriptions(integer,integer);
drop function if exists lautowork.operator_records_organisations(integer,integer);
drop function if exists lautowork.operator_records_products(integer,integer);
drop function if exists lautowork.operator_records_certification(integer,integer);
drop function if exists lautowork.operator_records_releases(integer,integer);
drop function if exists lautowork.operator_records_packages(integer,integer);
drop function if exists lautowork.operator_resource_version(uuid,text,text);
drop function if exists public.linkautowork_product_operator_records(text,integer,text);
drop index if exists lautowork.idx_lautowork_product_resource_history_resource;

-- Restore the exact 000006 public RPC contracts after removing the operator
-- replacements.  These grants are intentionally private server-only grants.
create or replace function public.linkautowork_product_operator_records(p_resource text,p_limit integer,p_cursor text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_offset integer:=coalesce(nullif(p_cursor,'')::integer,0); v_items jsonb; begin if p_limit<1 or p_limit>100 or v_offset<0 then raise exception 'invalid cursor'; end if;
 if p_resource='incidents' then select coalesce(jsonb_agg(jsonb_build_object('id',id,'orgId',org_id,'state',status,'version',1,'summary','[redacted]') order by opened_at),'[]'::jsonb) into v_items from (select * from automation_incidents order by opened_at offset v_offset limit p_limit) q;
 elsif p_resource='deployments' then select coalesce(jsonb_agg(jsonb_build_object('id',id,'orgId',org_id,'state',state,'version',1,'summary','deployment state') order by created_at),'[]'::jsonb) into v_items from (select * from automation_deployments order by created_at offset v_offset limit p_limit) q;
 else v_items:='[]'::jsonb; end if; return jsonb_build_object('items',v_items); end $$;

create or replace function public.linkautowork_product_operator_action(p_resource text,p_id uuid,p_action text,p_reason text,p_idempotency_key text,p_expected_version integer) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare i automation_incidents%rowtype; begin if p_resource='incidents' and p_action='acknowledge' then select * into strict i from automation_incidents where id=p_id for update; if i.status<>'open' then raise exception 'invalid transition'; end if; update automation_incidents set status='acknowledged' where id=i.id; insert into automation_incident_events(org_id,incident_id,event_type,actor_ref,evidence_ref) values(i.org_id,i.id,'acknowledged','product-api','evidence://product-api/operator-action'); return jsonb_build_object('id',i.id,'orgId',i.org_id,'state','acknowledged','version',2,'summary','[redacted]'); end if; raise exception 'invalid transition'; end $$;

revoke all on function public.linkautowork_product_operator_records(text,integer,text) from public;
grant execute on function public.linkautowork_product_operator_records(text,integer,text) to service_role,svc_lautowork_runtime;
revoke all on function public.linkautowork_product_operator_action(text,uuid,text,text,text,integer) from public;
grant execute on function public.linkautowork_product_operator_action(text,uuid,text,text,text,integer) to service_role,svc_lautowork_runtime;
