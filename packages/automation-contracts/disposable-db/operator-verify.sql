\set ON_ERROR_STOP on

select set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-000000000002', false);
select set_config('request.jwt.claim.role', 'service_role', false);
select set_config('request.jwt.claims', '{"role":"service_role","org_id":"00000000-0000-0000-0000-000000000002","sub":"operator-sql-verifier"}', false);
select set_config('request.headers', '{"x-link-org-id":"00000000-0000-0000-0000-000000000002"}', false);

do $$
declare resource text; page jsonb;
begin
  foreach resource in array array['packages','releases','certification','products','organisations','subscriptions','provisioning-jobs','instances','bindings','deployments','executions','health','incidents','maintenance','librarian-candidates','audit-evidence'] loop
    page := public.linkautowork_product_operator_records(resource, 25, null);
    if jsonb_array_length(page->'items') = 0 then raise exception 'operator resource % is an empty façade', resource; end if;
  end loop;
end $$;

-- The following actions exercise the existing bounded state machines and prove
-- reason, actor, expected-version, idempotency, history, and audit persistence.
select public.linkautowork_product_operator_action('instances','40000000-0000-0000-0000-000000000001','resume','Resume after durable operations verification','operator-instance-resume',1,'operator-sql-verifier');
select public.linkautowork_product_operator_action('instances','40000000-0000-0000-0000-000000000001','pause','Pause for operator verification','operator-instance-pause',2,'operator-sql-verifier');
select public.assert_true(exists(select 1 from lautowork.product_resource_transition_history where resource='instances' and actor_ref='operator-sql-verifier' and reason='Pause for operator verification'),'instance action history records actor and reason');
select public.assert_true(exists(select 1 from lautowork.automation_domain_audit_events where event_type='operator.instances.pause' and actor_ref='operator-sql-verifier'),'instance action writes domain audit');

select public.linkautowork_product_operator_action('incidents','91000000-0000-0000-0000-000000000001','acknowledge','Acknowledge verified incident','operator-incident-ack','1','operator-sql-verifier');
select public.linkautowork_product_operator_action('incidents','91000000-0000-0000-0000-000000000001','resolve','Resolve after recovery evidence','operator-incident-resolve','2','operator-sql-verifier');
select public.linkautowork_product_operator_action('provisioning-jobs','92000000-0000-0000-0000-000000000001','retry','Retry the failed provisioning state machine','operator-provisioning-retry','1','operator-sql-verifier');
select public.linkautowork_product_operator_action('maintenance','d0000000-0000-0000-0000-000000000001','retry','Run the approved bounded maintenance retry','operator-maintenance-retry','1','operator-sql-verifier');
select public.linkautowork_product_operator_action('librarian-candidates','a0000000-0000-0000-0000-000000000001','approve','Approve reviewed candidate evidence','operator-candidate-approve','1','operator-sql-verifier');
select public.linkautowork_product_operator_action('certification','30000000-0000-0000-0000-000000000002','approve','Approve independent evaluation receipt','operator-certification-approve','1','operator-sql-verifier');

select public.linkautowork_product_operator_action('deployments','50000000-0000-0000-0000-000000000011','canary','Start candidate canary with approved evidence','operator-deployment-canary','1','operator-sql-verifier');
select public.assert_true(
  (public.linkautowork_deployment_authority('00000000-0000-0000-0000-000000000002','50000000-0000-0000-0000-000000000011')->>'sampleCount')::integer >= 1,
  'operator canary has durable execution evidence before promotion'
);
select public.linkautowork_product_operator_action('deployments','50000000-0000-0000-0000-000000000011','promote','Promote after canary sample and health evidence','operator-deployment-promote','2','operator-sql-verifier');
select public.linkautowork_product_operator_action('deployments','50000000-0000-0000-0000-000000000011','rollback','Restore the certified baseline','operator-deployment-rollback','3','operator-sql-verifier');

do $$
begin
  begin
    perform public.linkautowork_product_operator_action('deployments','50000000-0000-0000-0000-000000000011','promote','stale version must fail','operator-stale-version',1,'operator-sql-verifier');
    raise exception 'stale operator action unexpectedly succeeded';
  exception when others then
    if position('concurrency_conflict' in sqlerrm) = 0 then raise; end if;
  end;
end $$;

select 'Wave 3 operator durable verification passed' as result;
