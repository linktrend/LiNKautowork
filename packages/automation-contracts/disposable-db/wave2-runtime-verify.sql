\set ON_ERROR_STOP on

select set_config('request.jwt.claims','{"role":"service_role"}',false);
select set_config('request.headers','{"x-link-org-id":"00000000-0000-0000-0000-000000000002","x-link-request-claims":"{\"role\":\"service_role\",\"org_id\":\"00000000-0000-0000-0000-000000000002\"}"}',false);
select lautowork.assert_command_authorized('00000000-0000-0000-0000-000000000002');
do $$ begin
  begin
    perform lautowork.assert_command_authorized('00000000-0000-0000-0000-000000000003');
    raise exception 'delegated Product API organization mismatch unexpectedly succeeded';
  exception when others then
    if position('not authorized' in sqlerrm)=0 then raise; end if;
  end;
end $$;

select set_config('request.jwt.claims','{"role":"svc_lautowork_runtime","org_id":"00000000-0000-0000-0000-000000000002"}',false);
select set_config('request.headers','{"x-link-org-id":"00000000-0000-0000-0000-000000000002"}',false);
select set_config('request.jwt.claim.org_id','',false);
select set_config('request.jwt.claim.role','',false);

update lautowork.automation_instances set state='active', configuration='{"webhook_path":"client-a","webhook_method":"POST","criticality":"critical","timeout_ms":1000,"retry_count":1,"input_schema":{"type":"object","properties":{"customer":{"type":"string"}},"required":["customer"],"additionalProperties":false}}'::jsonb
where id='40000000-0000-0000-0000-000000000001';
update lautowork.automation_deployments set state='active' where id='50000000-0000-0000-0000-000000000001';
insert into lautowork.automation_bindings(org_id,instance_id,consumer_system,binding_operation)
values('00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','linksites','linksites.reminder.run');

select public.assert_true(
  (public.linkautowork_resolve_bound_instance('00000000-0000-0000-0000-000000000002','linksites','linksites.reminder.run')->>'instanceId')='40000000-0000-0000-0000-000000000001',
  'bound runtime resolution is org and service scoped');
do $$ begin
  begin perform public.linkautowork_resolve_bound_instance('00000000-0000-0000-0000-000000000003','linksites','linksites.reminder.run'); raise exception 'cross-org parameter unexpectedly succeeded'; exception when others then if position('not authorized' in sqlerrm)=0 then raise; end if; end;
end $$;
do $$ begin
  perform set_config('request.jwt.claims','{"role":"svc_lautowork_runtime","org_id":"00000000-0000-0000-0000-000000000003"}',true);
  perform set_config('request.headers','{"x-link-org-id":"00000000-0000-0000-0000-000000000003"}',true);
  begin perform public.linkautowork_resolve_bound_instance('00000000-0000-0000-0000-000000000002','linksites','linksites.reminder.run'); raise exception 'cross-org runtime claim unexpectedly succeeded'; exception when others then if position('not authorized' in sqlerrm)=0 then raise; end if; end;
end $$;

select public.assert_true((public.linkautowork_accept_execution(
  '60000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001',
  '20000000-0000-0000-0000-000000000001','50000000-0000-0000-0000-000000000001','wave2-idempotency','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'linkautowork-n8n','sha256:2bab857641ead2282344948fa6e48b34d6048089f1fd912e68c2f4fafb9c6a8f')->>'duplicate')::boolean=false,'first atomic acceptance is new');
select public.assert_true((public.linkautowork_accept_execution(
  '60000000-0000-0000-0000-000000000011','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001',
  '20000000-0000-0000-0000-000000000001','50000000-0000-0000-0000-000000000001','wave2-idempotency','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'linkautowork-n8n','sha256:2bab857641ead2282344948fa6e48b34d6048089f1fd912e68c2f4fafb9c6a8f')->>'duplicate')::boolean=true,'duplicate acceptance replays durable receipt');

-- The acceptance above stores only sha256("callback-token").
select public.assert_true((public.linkautowork_record_execution_callback('00000000-0000-0000-0000-000000000002','60000000-0000-0000-0000-000000000010','linkautowork-n8n','callback-token',2,'started','2026-08-04T00:00:02Z',null,'evidence://wave2/started')->>'disposition')='applied','bound callback applies atomically');
select public.assert_true((public.linkautowork_record_execution_callback('00000000-0000-0000-0000-000000000002','60000000-0000-0000-0000-000000000010','linkautowork-n8n','callback-token',2,'started','2026-08-04T00:00:02Z',null,'evidence://wave2/started')->>'disposition')='duplicate','exact callback retry is durable duplicate');
select public.assert_true((public.linkautowork_record_execution_callback('00000000-0000-0000-0000-000000000002','60000000-0000-0000-0000-000000000010','linkautowork-n8n','callback-token',4,'succeeded','2026-08-04T00:00:04Z',null,'evidence://wave2/done')->>'disposition')='out_of_order','out of order callback is durable evidence without projection mutation');
do $$ begin
  begin perform public.linkautowork_record_execution_callback('00000000-0000-0000-0000-000000000003','60000000-0000-0000-0000-000000000010','linkautowork-n8n','callback-token',3,'succeeded',now(),null,null); raise exception 'cross-org callback succeeded'; exception when others then if position('capability denied' in sqlerrm)=0 then raise; end if; end;
  begin perform public.linkautowork_record_execution_callback('00000000-0000-0000-0000-000000000002','60000000-0000-0000-0000-000000000010','linkautowork-n8n','wrong-token',3,'succeeded',now(),null,null); raise exception 'wrong-token callback succeeded'; exception when others then if position('capability denied' in sqlerrm)=0 then raise; end if; end;
end $$;

insert into lautowork.automation_instances(id,org_id,definition_id,release_id,instance_key,state,configuration,configuration_digest)
values('40000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','wave2-provision','draft','{"source_workflow_id":"source-1","environment":"stage"}','sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff');
insert into lautowork.provisioning_requests(id,org_id,instance_id,requested_release_id,status,request_ref)
values('80000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000010','20000000-0000-0000-0000-000000000001','requested','wave2-provision-ref');
select public.assert_true((public.linkautowork_begin_provisioning('00000000-0000-0000-0000-000000000002','wave2-provision-ref')->>'status')='provisioning','provisioning begins under row lock');
select public.linkautowork_create_provisioning_deployment('80000000-0000-0000-0000-000000000010','unique-copy-1') as deployment_id \gset
select public.linkautowork_mark_provisioning('80000000-0000-0000-0000-000000000010','completed',jsonb_build_object('deploymentId',:'deployment_id','workflowId','unique-copy-1','workflowDigest','sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
select public.assert_true((select count(*)=1 from lautowork.automation_deployments where instance_id='40000000-0000-0000-0000-000000000010' and state='active'),'exactly one active copy is recorded');
select public.assert_true((public.linkautowork_begin_provisioning('00000000-0000-0000-0000-000000000002','wave2-provision-ref')->>'status')='completed','completed provisioning replay is idempotent');

select 'Wave 2 runtime corrections disposable verification passed' as result;
