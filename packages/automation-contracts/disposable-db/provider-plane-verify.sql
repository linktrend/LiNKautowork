\set ON_ERROR_STOP on
-- Source-level disposable verification targets invariants that do not require external providers.
select public.assert_true(exists(select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='lautowork' and c.relname='provider_requests'),'provider request table exists');
select public.assert_true(exists(select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='lautowork' and c.relname='provider_outbox'),'provider outbox table exists');
select public.assert_true((select relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='lautowork' and c.relname='provider_requests'),'provider requests enforce RLS');
select public.assert_true((select count(*) from pg_constraint where conrelid='lautowork.provider_requests'::regclass and contype='u') >= 1,'idempotency uniqueness exists');
select public.assert_true(to_regprocedure('lautowork.linkautowork_provider_accept(jsonb,text)') is not null,'atomic provider acceptance rpc exists');
select public.assert_true(to_regprocedure('lautowork.linkautowork_provider_transition(uuid,integer,text)') is not null,'provider CAS transition rpc exists');
select public.assert_true(to_regprocedure('lautowork.linkautowork_provider_append_event(jsonb)') is not null,'provider event append rpc exists');
select public.assert_true(to_regprocedure('lautowork.linkautowork_provider_set_kill_switch(text,boolean,text)') is not null,'provider kill-switch mutation rpc exists');
select public.assert_true(exists(select 1 from pg_attribute where attrelid='lautowork.provider_requests'::regclass and attname='request_json' and not attnotnull),'request JSON stays nullable for historical rows');
select public.assert_true(exists(select 1 from pg_attribute where attrelid='lautowork.provider_receipts'::regclass and attname='receipt_json' and not attnotnull),'receipt JSON stays nullable for historical rows');
select public.assert_true(exists(select 1 from pg_attribute where attrelid='lautowork.provider_kill_switches'::regclass and attname='mutation_sequence'),'kill-switch mutations have a monotonic ordering column');
select public.assert_true(not has_function_privilege('public','lautowork.linkautowork_provider_accept(jsonb,text)','execute'),'provider rpc is not public');
select public.assert_true(has_function_privilege('svc_lautowork_runtime','lautowork.linkautowork_provider_set_kill_switch(text,boolean,text)','execute'),'runtime role can invoke scoped kill-switch mutation');
do $$ begin
  if exists(select 1 from pg_roles where rolname='svc_lautowork_gateway') then
    perform public.assert_true(not has_function_privilege('svc_lautowork_gateway','lautowork.linkautowork_provider_set_kill_switch(text,boolean,text)','execute'),'gateway role does not inherit provider kill-switch mutation');
  end if;
end $$;
