-- Disposable-only dedicated gateway role proof; no n8n or external calls.
insert into platform.organizations(id,slug) values ('00000000-0000-0000-0000-0000000000e1','gateway-scoped-a'),('00000000-0000-0000-0000-0000000000e2','gateway-scoped-b');
insert into lautowork.automation_definitions(id,org_id,automation_id,display_name,summary,owning_program,owner_kind,classification)
values ('10000000-0000-0000-0000-0000000000e1','00000000-0000-0000-0000-0000000000e1','gateway-private-check','Gateway Private Check','Disposable gateway role verification with no external effects.','linkautowork','commercial_product','commercial_capable');
insert into lautowork.automation_releases(id,org_id,definition_id,version,channel,lifecycle,package_digest,workflow_digest,source_git_sha,n8n_version,package_path)
values ('20000000-0000-0000-0000-0000000000e1','00000000-0000-0000-0000-0000000000e1','10000000-0000-0000-0000-0000000000e1','1.0.0','stable','certified','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','2.30.0','automations/catalog/gateway-private-check/1.0.0');
insert into lautowork.automation_instances(id,org_id,definition_id,release_id,instance_key,state,configuration,configuration_digest)
values ('40000000-0000-0000-0000-0000000000e1','00000000-0000-0000-0000-0000000000e1','10000000-0000-0000-0000-0000000000e1','20000000-0000-0000-0000-0000000000e1','gateway-private-check-01','ready','{}','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
insert into lautowork.automation_deployments(id,org_id,instance_id,release_id,environment,n8n_workflow_id,workflow_digest,configuration_digest,state)
values ('50000000-0000-0000-0000-0000000000e1','00000000-0000-0000-0000-0000000000e1','40000000-0000-0000-0000-0000000000e1','20000000-0000-0000-0000-0000000000e1','stage','disposable-private-check','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','active');
insert into lautowork.automation_bindings(org_id,instance_id,consumer_system,binding_operation)
values ('00000000-0000-0000-0000-0000000000e1','40000000-0000-0000-0000-0000000000e1','gateway','precheck');
set local lautowork.test_context='off';
do $$ begin
 if exists(select 1 from pg_roles where rolname='svc_lautowork_gateway' and (rolsuper or rolbypassrls or rolcreaterole))
   or has_function_privilege('svc_lautowork_gateway','public.linkautowork_active_killswitches()','execute')
   or has_function_privilege('svc_lautowork_gateway','public.linkautowork_write_killswitch_event(uuid,text,text,text,text,jsonb)','execute')
   or has_table_privilege('svc_lautowork_gateway','lautowork.automation_executions','insert')
   or has_function_privilege('svc_lautowork_gateway','public.linkautowork_begin_provisioning(uuid,text)','execute')
   or has_function_privilege('svc_lautowork_gateway','public.linkautowork_product_create_order_audited(text,text)','execute') then
   raise exception 'gateway role has excess authority';
 end if;
end $$;
set local role svc_lautowork_gateway;
select set_config('request.jwt.claims','{"role":"svc_lautowork_gateway","org_id":"00000000-0000-0000-0000-0000000000e1"}',true);
select set_config('request.headers','{"x-link-org-id":"00000000-0000-0000-0000-0000000000e1"}',true);
do $$ declare receipt jsonb; begin
 if public.linkautowork_resolve_bound_instance('00000000-0000-0000-0000-0000000000e1','gateway','precheck')->>'instanceId' is distinct from '40000000-0000-0000-0000-0000000000e1' then
   raise exception 'gateway durable resolution failed'; end if;
 if public.linkautowork_resolve_bound_instance('00000000-0000-0000-0000-0000000000e1','other-consumer','precheck') is not null then
   raise exception 'wrong consumer binding returned'; end if;
 begin
   perform public.linkautowork_resolve_bound_instance('00000000-0000-0000-0000-0000000000e2','gateway','precheck');
   raise exception 'cross org lookup accepted';
 exception when others then if sqlerrm <> 'command is not authorized for target organization' then raise; end if; end;
 perform public.linkautowork_active_pause('00000000-0000-0000-0000-0000000000e1','gateway-private-check','40000000-0000-0000-0000-0000000000e1');
 perform public.linkautowork_gateway_active_killswitches('00000000-0000-0000-0000-0000000000e1');
 receipt:=public.linkautowork_accept_execution('60000000-0000-0000-0000-0000000000e1','00000000-0000-0000-0000-0000000000e1','40000000-0000-0000-0000-0000000000e1','20000000-0000-0000-0000-0000000000e1','50000000-0000-0000-0000-0000000000e1','gateway-private-idempotency','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','linkautowork-n8n','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
 if (receipt->>'duplicate')::boolean then raise exception 'new execution marked duplicate'; end if;
 receipt:=public.linkautowork_accept_execution('60000000-0000-0000-0000-0000000000e1','00000000-0000-0000-0000-0000000000e1','40000000-0000-0000-0000-0000000000e1','20000000-0000-0000-0000-0000000000e1','50000000-0000-0000-0000-0000000000e1','gateway-private-idempotency','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','linkautowork-n8n','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
 if not (receipt->>'duplicate')::boolean then raise exception 'idempotent replay not durable'; end if;
end $$;
reset role;
do $$ begin
 if (select count(*) from lautowork.automation_executions where id='60000000-0000-0000-0000-0000000000e1') <> 1 then raise exception 'gateway acceptance did not persist exactly once'; end if;
end $$;
