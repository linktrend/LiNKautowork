\set ON_ERROR_STOP on

create or replace function public.assert_true(condition boolean, message text)
returns void language plpgsql as $$
begin
  if not condition then raise exception 'assertion failed: %', message; end if;
end;
$$;

insert into platform.organizations (id, slug) values
  ('00000000-0000-0000-0000-000000000001', 'linktrend-internal'),
  ('00000000-0000-0000-0000-000000000002', 'client-a'),
  ('00000000-0000-0000-0000-000000000003', 'client-b');

insert into lautowork.automation_definitions
  (id, org_id, automation_id, display_name, summary, owning_program, owner_kind, classification)
values
  ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002', 'client-a-reminder', 'Client A Reminder', 'A disposable verification definition for client A.', 'linkautowork', 'commercial_product', 'commercial_capable'),
  ('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000003', 'client-b-reminder', 'Client B Reminder', 'A disposable verification definition for client B.', 'linkautowork', 'commercial_product', 'commercial_capable');

insert into lautowork.automation_releases
  (id, org_id, definition_id, version, channel, lifecycle, package_digest, workflow_digest, source_git_sha, n8n_version, package_path)
values
  ('20000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '1.0.0', 'stable', 'eval_pending', 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', '2.30.0', 'automations/catalog/client-a-reminder/1.0.0'),
  ('20000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000002', '1.0.0', 'stable', 'retired', 'sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', 'sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', '2.30.0', 'automations/catalog/client-b-reminder/1.0.0');

insert into lautowork.automation_definitions
  (id, org_id, automation_id, display_name, summary, owning_program, owner_kind, classification)
values
  ('10000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', 'client-a-secondary', 'Client A Secondary', 'A second disposable definition for lineage adversarial checks.', 'linkautowork', 'commercial_product', 'commercial_capable');
insert into lautowork.automation_releases
  (id, org_id, definition_id, version, channel, lifecycle, package_digest, workflow_digest, source_git_sha, n8n_version, package_path)
values
  ('20000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000003', '1.0.0', 'stable', 'certified', 'sha256:1111111111111111111111111111111111111111111111111111111111111111', 'sha256:2222222222222222222222222222222222222222222222222222222222222222', 'cccccccccccccccccccccccccccccccccccccccc', '2.30.0', 'automations/catalog/client-a-secondary/1.0.0');

insert into lautowork.automation_eval_runs
  (id, org_id, release_id, suite_digest, package_digest, workflow_digest, n8n_version, status, independent_verdict, evaluator_ref, completed_at, receipt_ref)
values
  ('30000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000001', 'sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee', 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', '2.30.0', 'passed', true, 'disposable-independent-evaluator', now(), 'evidence://disposable/eval/1');

select set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-000000000002', false);
select set_config('request.jwt.claim.role', 'service_role', false);

select public.linkautowork_certify_automation_release(
  '00000000-0000-0000-0000-000000000002',
  '20000000-0000-0000-0000-000000000001',
  'disposable-independent-evaluator',
  'evidence://disposable/eval/1'
);
select public.assert_true((select lifecycle = 'certified' from lautowork.automation_releases where id = '20000000-0000-0000-0000-000000000001'), 'passed independent eval certifies release');

insert into lautowork.automation_instances
  (id, org_id, definition_id, release_id, instance_key, state, configuration, configuration_digest)
values
  ('40000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 'client-a-reminder-01', 'ready', '{"timezone":"Asia/Taipei"}', 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff');

insert into lautowork.automation_instances
  (id, org_id, definition_id, release_id, instance_key, state, configuration, configuration_digest)
values
  ('40000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000002', 'client-b-reminder-01', 'draft', '{"timezone":"Asia/Taipei"}', 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff');

insert into lautowork.approval_requests
  (id, org_id, subject_type, subject_id, required_role, status)
values
  ('70000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000003', 'release', '20000000-0000-0000-0000-000000000002', 'operator', 'pending');

do $$
begin
  begin
    insert into lautowork.automation_bindings (org_id, instance_id, consumer_system, binding_operation)
    values ('00000000-0000-0000-0000-000000000003', '40000000-0000-0000-0000-000000000001', 'linksites', 'linksites.client-a.reminder');
    raise exception 'cross-org binding unexpectedly succeeded';
  exception when foreign_key_violation then null;
  end;
  begin
    insert into lautowork.automation_instances (org_id, definition_id, release_id, instance_key, state, configuration, configuration_digest)
    values ('00000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 'client-a-secret', 'draft', '{"api_key":"not-allowed"}', 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff');
    raise exception 'secret-shaped configuration unexpectedly succeeded';
  exception when check_violation then null;
  end;
  begin
    insert into lautowork.automation_instances (org_id, definition_id, release_id, instance_key, state, configuration, configuration_digest)
    values ('00000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000003', 'incoherent-instance', 'draft', '{"timezone":"Asia/Taipei"}', 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff');
    raise exception 'incoherent instance lineage unexpectedly succeeded';
  exception when others then
    if position('lineage' in sqlerrm) = 0 and position('definition' in sqlerrm) = 0 then raise; end if;
  end;
  begin
    update lautowork.automation_releases set version = '1.0.1' where id = '20000000-0000-0000-0000-000000000001';
    raise exception 'immutable release mutation unexpectedly succeeded';
  exception when others then
    if position('immutable' in sqlerrm) = 0 then raise; end if;
  end;
  begin
    insert into lautowork.provisioning_requests (org_id, instance_id, requested_release_id, status, request_ref)
    values ('00000000-0000-0000-0000-000000000003', '40000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000002', 'requested', 'disposable-retired');
    raise exception 'retired release provisioning unexpectedly succeeded';
  exception when others then
    if position('certified releases' in sqlerrm) = 0 then raise; end if;
  end;
  begin
    insert into lautowork.provisioning_requests (org_id, instance_id, requested_release_id, status, request_ref)
    values ('00000000-0000-0000-0000-000000000002', '40000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000003', 'requested', 'disposable-incoherent');
    raise exception 'incoherent provisioning unexpectedly succeeded';
  exception when others then
    if position('lineage' in sqlerrm) = 0 then raise; end if;
  end;
  begin
    perform public.linkautowork_certify_automation_release(
      '00000000-0000-0000-0000-000000000003',
      '20000000-0000-0000-0000-000000000002',
      'adversarial-org-a-caller',
      'evidence://disposable/adversarial'
    );
    raise exception 'cross-org SECURITY DEFINER certification unexpectedly succeeded';
  exception when others then
    if position('not authorized' in sqlerrm) = 0 then raise; end if;
  end;
  begin
    perform public.linkautowork_transition_automation_release(
      '00000000-0000-0000-0000-000000000003',
      '20000000-0000-0000-0000-000000000002',
      'retired',
      'adversarial-org-a-caller',
      'evidence://disposable/adversarial'
    );
    raise exception 'cross-org SECURITY DEFINER lifecycle transition unexpectedly succeeded';
  exception when others then
    if position('not authorized' in sqlerrm) = 0 then raise; end if;
  end;
  begin
    perform public.linkautowork_append_approval_decision(
      '00000000-0000-0000-0000-000000000003',
      '70000000-0000-0000-0000-000000000001',
      'approved',
      'adversarial-org-a-caller',
      'evidence://disposable/adversarial'
    );
    raise exception 'cross-org SECURITY DEFINER approval unexpectedly succeeded';
  exception when others then
    if position('not authorized' in sqlerrm) = 0 then raise; end if;
  end;
end $$;

set role svc_lautowork_runtime;
select set_config('request.jwt.claim.org_id', '', false);
select set_config('request.jwt.claim.tenant_id', '00000000-0000-0000-0000-000000000003', false);
select set_config('request.jwt.claim.role', 'service_role', false);
select public.assert_true(
  (select count(*) = 0 from lautowork.automation_definitions),
  'legacy tenant claim alone grants no read authority'
);
select set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-000000000002', false);
select set_config('request.jwt.claim.role', 'service_role', false);
select public.assert_true(
  (select count(*) = 2 from lautowork.automation_definitions),
  'RLS permits only the current organization read scope'
);
do $$
begin
  begin
    insert into lautowork.automation_definitions (org_id, automation_id, display_name, summary, owning_program, owner_kind, classification)
    values ('00000000-0000-0000-0000-000000000002', 'forbidden-direct-write', 'Forbidden direct write', 'The runtime role must use controlled commands instead.', 'linkautowork', 'shared_internal', 'internal_only');
    raise exception 'runtime direct write unexpectedly succeeded';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;

insert into lautowork.automation_deployments
  (id, org_id, instance_id, release_id, environment, n8n_workflow_id, workflow_digest, configuration_digest, state)
values
  ('50000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002', '40000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 'stage', 'n8n-disposable-client-a', 'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff', 'planned');
insert into lautowork.automation_executions
  (id, org_id, instance_id, release_id, deployment_id, idempotency_key, status)
values
  ('60000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002', '40000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', '50000000-0000-0000-0000-000000000001', 'disposable-execution-1', 'accepted');
insert into lautowork.automation_deployments
  (id, org_id, instance_id, release_id, environment, n8n_workflow_id, workflow_digest, configuration_digest, state)
values
  ('50000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000003', '40000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000002', 'stage', 'n8n-disposable-client-b', 'sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd', 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff', 'planned');
insert into lautowork.automation_executions
  (id, org_id, instance_id, release_id, deployment_id, idempotency_key, status)
values
  ('60000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000003', '40000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000002', '50000000-0000-0000-0000-000000000002', 'disposable-execution-2', 'accepted');
select public.linkautowork_append_execution_event('00000000-0000-0000-0000-000000000002', '60000000-0000-0000-0000-000000000001', 1, 'accepted', now(), null, 'evidence://disposable/execution/1');

do $$
begin
  begin
    perform public.linkautowork_append_execution_event(
      '00000000-0000-0000-0000-000000000003',
      '60000000-0000-0000-0000-000000000002',
      1,
      'accepted',
      now(),
      null,
      'evidence://disposable/adversarial'
    );
    raise exception 'cross-org SECURITY DEFINER execution event unexpectedly succeeded';
  exception when others then
    if position('not authorized' in sqlerrm) = 0 then raise; end if;
  end;
  begin
    insert into lautowork.automation_deployments
      (org_id, instance_id, release_id, environment, n8n_workflow_id, workflow_digest, configuration_digest, state)
    values
      ('00000000-0000-0000-0000-000000000002', '40000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000003', 'development', 'n8n-incoherent-release', 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff', 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff', 'planned');
    raise exception 'incoherent deployment unexpectedly succeeded';
  exception when others then
    if position('lineage' in sqlerrm) = 0 then raise; end if;
  end;
  begin
    insert into lautowork.automation_executions
      (org_id, instance_id, release_id, deployment_id, idempotency_key, status)
    values
      ('00000000-0000-0000-0000-000000000002', '40000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000003', '50000000-0000-0000-0000-000000000001', 'incoherent-execution', 'accepted');
    raise exception 'incoherent execution unexpectedly succeeded';
  exception when others then
    if position('lineage' in sqlerrm) = 0 then raise; end if;
  end;
  begin
    insert into lautowork.automation_instances (org_id, definition_id, release_id, instance_key, state, configuration, configuration_digest)
    values ('00000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 'client-a-url-secret', 'draft', '{"callback_url":"postgres://admin:pw123@db.internal:5432/app"}', 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff');
    raise exception 'connection-string configuration unexpectedly succeeded';
  exception when check_violation then null;
  end;
  begin
    insert into lautowork.automation_instances (org_id, definition_id, release_id, instance_key, state, configuration, configuration_digest)
    values ('00000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 'client-a-bearer-secret', 'draft', '{"authorization":"Bearer abcdefghijklmnop"}', 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff');
    raise exception 'bearer configuration unexpectedly succeeded';
  exception when check_violation then null;
  end;
end $$;

do $$
begin
  begin
    update lautowork.automation_execution_events set event_type = 'failed' where execution_id = '60000000-0000-0000-0000-000000000001';
    raise exception 'append-only evidence update unexpectedly succeeded';
  exception when others then
    if position('append-only' in sqlerrm) = 0 then raise; end if;
  end;
end $$;

select public.assert_true(not exists (
  select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
  cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
  where n.nspname = 'public' and p.proname in ('linkautowork_certify_automation_release', 'linkautowork_transition_automation_release', 'linkautowork_append_execution_event', 'linkautowork_append_approval_decision')
    and a.grantee = 0 and a.privilege_type = 'EXECUTE'
), 'privileged functions do not grant EXECUTE to PUBLIC');

select 'WP-04 disposable database verification passed' as result;
