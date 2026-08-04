insert into lautowork.automation_librarian_evidence(evidence_ref,org_id,payload,payload_hash)
values ('evidence://disposable/wp07/1','00000000-0000-0000-0000-000000000002','{"verdict":"failed"}'::jsonb,'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');

select set_config('request.jwt.claim.org_id','00000000-0000-0000-0000-000000000002',false);
select set_config('request.jwt.claim.role','service_role',false);
set role svc_lautowork_runtime;

select public.assert_true((select count(*)=1 from public.linkautowork_librarian_resolve_evidence('00000000-0000-0000-0000-000000000002','evidence://disposable/wp07/1')),'gateway runtime credential resolves authorised durable evidence');
select public.linkautowork_librarian_set_control('00000000-0000-0000-0000-000000000002','client-a-reminder',false);
select public.assert_true((public.linkautowork_librarian_get_control('00000000-0000-0000-0000-000000000002','client-a-reminder')->>'paused')::boolean,'pause survives durable RPC round trip');

select public.linkautowork_librarian_save_candidate('00000000-0000-0000-0000-000000000002',jsonb_build_object(
  'id','70000000-0000-0000-0000-000000000001','orgId','00000000-0000-0000-0000-000000000002','domain','automation',
  'deduplicationKey','sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','status','proposed','proposerId','librarian:disposable',
  'source',jsonb_build_object('automationId','client-a-reminder'),'audit',jsonb_build_object('transitions',jsonb_build_array(jsonb_build_object('reason','disposable verified evidence')))
));
select public.assert_true((select count(*)=1 from public.linkautowork_librarian_find_candidate('00000000-0000-0000-0000-000000000002','sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',null)),'candidate persists by org and dedupe key');
do $$ begin
  perform public.linkautowork_librarian_find_candidate('00000000-0000-0000-0000-000000000001','sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',null);
  raise exception 'cross-org candidate guard was accepted';
exception when others then if sqlerrm='cross-org candidate guard was accepted' then raise; end if; end $$;
do $$ begin
  perform public.linkautowork_librarian_get_control('00000000-0000-0000-0000-000000000001','client-a-reminder');
  raise exception 'wrong-org gateway claim was accepted';
exception when others then
  if sqlerrm='wrong-org gateway claim was accepted' then raise; end if;
end $$;
reset role;
