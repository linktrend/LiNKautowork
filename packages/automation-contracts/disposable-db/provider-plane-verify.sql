\set ON_ERROR_STOP on
-- Source-level disposable verification targets invariants that do not require external providers.
select public.assert_true(exists(select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='lautowork' and c.relname='provider_requests'),'provider request table exists');
select public.assert_true(exists(select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='lautowork' and c.relname='provider_outbox'),'provider outbox table exists');
select public.assert_true((select relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='lautowork' and c.relname='provider_requests'),'provider requests enforce RLS');
select public.assert_true((select count(*) from pg_constraint where conrelid='lautowork.provider_requests'::regclass and contype='u') >= 1,'idempotency uniqueness exists');
select public.assert_true(to_regprocedure('lautowork.linkautowork_provider_accept(jsonb,text)') is not null,'atomic provider acceptance rpc exists');
select public.assert_true(to_regprocedure('lautowork.linkautowork_provider_transition(uuid,integer,text)') is not null,'provider CAS transition rpc exists');
select public.assert_true(to_regprocedure('lautowork.linkautowork_provider_append_event(jsonb)') is not null,'provider event append rpc exists');
select public.assert_true(not has_function_privilege('public','lautowork.linkautowork_provider_accept(jsonb,text)','execute'),'provider rpc is not public');
