-- Runs only in the disposable PostgreSQL conformance transaction.
insert into platform.organizations(id,name) values
 ('00000000-0000-0000-0000-0000000000d1','scoped-product-a'),
 ('00000000-0000-0000-0000-0000000000d2','scoped-product-b');
set local lautowork.test_context = 'off';
do $$ begin
 if exists(select 1 from pg_roles where rolname='svc_lautowork_product_api'
   and (rolsuper or rolbypassrls or rolcreaterole or rolcreatedb)) then
   raise exception 'Product API role is overprivileged';
 end if;
 if has_function_privilege('svc_lautowork_product_api','public.linkautowork_product_client_instances(integer,text)','execute')
   or has_table_privilege('svc_lautowork_product_api','lautowork.product_api_audit_outbox','insert') then
   raise exception 'Product API bypasses audited RPCs';
 end if;
end $$;
do $$ declare old_role text; begin
 foreach old_role in array array['service_role','svc_lautowork_runtime'] loop
   if exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
     where n.nspname='public' and p.proname like 'linkautowork\_product\_%' escape '\'
       and has_function_privilege(old_role,p.oid,'execute')) then
     raise exception 'legacy role retains Product API transport';
   end if;
   perform set_config('request.jwt.claims',jsonb_build_object('role',old_role)::text,true);
   perform set_config('request.headers','{"x-link-org-id":"00000000-0000-0000-0000-0000000000d1"}',true);
   begin
     perform lautowork.assert_product_api_transport_authorized('00000000-0000-0000-0000-0000000000d1');
     raise exception 'legacy JWT role remains authorized';
   exception when others then
     if sqlerrm <> 'Product API organization authorization denied' then raise; end if;
   end;
 end loop;
end $$;
set local role svc_lautowork_product_api;
select set_config('request.jwt.claims','{}',true);
select set_config('request.headers','{"x-link-org-id":"00000000-0000-0000-0000-0000000000d1","x-link-request-claims":"{\"role\":\"svc_lautowork_product_api\"}"}',true);
do $$ begin
 begin
   perform public.linkautowork_product_reserve_audit('operator-test','instances','operator.instances.read','private canary','scoped-audit-159');
   raise exception 'forged header unexpectedly authorized';
 exception when others then
   if sqlerrm <> 'Product API organization authorization denied' then raise; end if;
 end;
end $$;
select set_config('request.jwt.claims','{"role":"svc_lautowork_product_api"}',true);
select set_config('request.headers','{"x-link-org-id":"00000000-0000-0000-0000-0000000000d1","x-link-audit-actor":"operator-test","x-link-audit-resource":"instances","x-link-audit-action":"operator.instances.read","x-link-audit-reason":"private canary","x-link-audit-correlation":"scoped-audit-159"}',true);
do $$ begin
 begin
   perform public.linkautowork_product_client_instances_audited(10,null);
   raise exception 'missing audit unexpectedly authorized';
 exception when others then
   if sqlerrm <> 'Product API audit reservation is required' then raise; end if;
 end;
 begin
   perform lautowork.assert_product_api_transport_authorized('00000000-0000-0000-0000-0000000000d2');
   raise exception 'cross-org request unexpectedly authorized';
 exception when others then
   if sqlerrm <> 'Product API organization authorization denied' then raise; end if;
 end;
end $$;
select public.linkautowork_product_reserve_audit('operator-test','instances','operator.instances.read','private canary','scoped-audit-159');
select public.linkautowork_product_client_instances_audited(10,null);
select public.linkautowork_product_finalize_audit('operator-test','instances','operator.instances.read','private canary','scoped-audit-159','allowed');
reset role;
do $$ begin
 if not exists(select 1 from lautowork.product_api_audit_outbox
   where correlation_id='scoped-audit-159' and status='completed' and outcome='allowed') then
   raise exception 'scoped Product API audit did not persist';
 end if;
end $$;
