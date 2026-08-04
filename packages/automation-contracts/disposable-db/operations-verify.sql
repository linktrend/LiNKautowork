\set ON_ERROR_STOP on

select set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-000000000002', false);
select set_config('request.jwt.claim.role', 'service_role', false);

select public.assert_true(jsonb_array_length(public.linkautowork_monitor_targets('00000000-0000-0000-0000-000000000002')) >= 1, 'monitor targets survive durable query');
select public.linkautowork_write_health('{"orgId":"00000000-0000-0000-0000-000000000002","instanceId":"40000000-0000-0000-0000-000000000001","state":"critical","observedAt":"2026-08-04T00:02:00.000Z"}'::jsonb);
select public.assert_true(jsonb_array_length(public.linkautowork_health_view('00000000-0000-0000-0000-000000000002')) = 1, 'health view is durable and org scoped');

do $$ declare opened jsonb; repeated jsonb; begin
  opened := public.linkautowork_open_alert_incident('{"orgId":"00000000-0000-0000-0000-000000000002","instanceId":"40000000-0000-0000-0000-000000000001","routingKey":"missing-schedule","severity":"critical","evidenceRef":"evidence://monitor/missing","repeatAfter":"2099-01-01T00:00:00Z"}'::jsonb);
  repeated := public.linkautowork_open_alert_incident('{"orgId":"00000000-0000-0000-0000-000000000002","instanceId":"40000000-0000-0000-0000-000000000001","routingKey":"missing-schedule","severity":"critical","evidenceRef":"evidence://monitor/missing","repeatAfter":"2099-01-01T00:00:00Z"}'::jsonb);
  if not (opened->>'deliver')::boolean or (repeated->>'deliver')::boolean then raise exception 'alert deduplication failed'; end if;
  perform public.linkautowork_record_alert_delivery(jsonb_build_object('orgId','00000000-0000-0000-0000-000000000002','alertId',opened->>'alertId','routingKey','missing-schedule','severity','critical','recovered',false));
end $$;

do $$ begin
  begin perform public.linkautowork_health_view('00000000-0000-0000-0000-000000000003'); raise exception 'cross-org health read unexpectedly succeeded';
  exception when others then if position('not authorized' in sqlerrm)=0 then raise; end if; end;
end $$;

select public.linkautowork_write_pause('{"orgId":"00000000-0000-0000-0000-000000000002","scope":"organisation","active":true,"actor":"disposable-operator","reason":"disposable incident","evidenceRef":"evidence://incident/disposable"}'::jsonb);
select public.assert_true((select count(*)=1 from lautowork.automation_pause_controls where org_id='00000000-0000-0000-0000-000000000002'), 'organisation pause is durable');
select public.assert_true((public.linkautowork_active_pause('00000000-0000-0000-0000-000000000002','client-a-reminder','40000000-0000-0000-0000-000000000001')->>'scope')='organisation', 'PauseReader RPC returns the active org-bound scope');
set role service_role;
select set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-000000000002', false);
select set_config('request.jwt.claim.role', 'service_role', false);
select public.assert_true((public.linkautowork_active_pause('00000000-0000-0000-0000-000000000002','client-a-reminder','40000000-0000-0000-0000-000000000001')->>'scope')='organisation', 'gateway service-role credential can execute the narrow operations RPC');
reset role;
select set_config('request.jwt.claim.org_id', '00000000-0000-0000-0000-000000000002', false);
select set_config('request.jwt.claim.role', 'service_role', false);
update lautowork.automation_instances set configuration=configuration||'{"remediation_allowlist":["retry","pause_instance"],"supports_failover":false,"canary_min_samples":1,"canary_min_window_ms":0}'::jsonb where id='40000000-0000-0000-0000-000000000001';
insert into lautowork.approval_requests(id,org_id,subject_type,subject_id,required_role,status) values('71000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','maintenance','40000000-0000-0000-0000-000000000001','operator','approved');
insert into lautowork.approval_decisions(org_id,approval_request_id,decision,decided_by_ref,evidence_ref) values('00000000-0000-0000-0000-000000000002','71000000-0000-0000-0000-000000000001','approved','disposable-approver','evidence://approval/retry');
select public.assert_true(not (public.linkautowork_authorize_operation_action('00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','retry','evidence://forged')->>'allowed')::boolean, 'forged caller evidence cannot grant action authority');
select public.assert_true((public.linkautowork_execute_retry('00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','evidence://approval/retry')->>'queued')::boolean, 'approved retry enters durable outbox');
select public.linkautowork_execute_retry('00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','evidence://approval/retry');
select public.assert_true((select count(*)=1 from lautowork.operation_retry_outbox), 'retry enqueue is idempotent across restart');
select public.linkautowork_complete_retry('00000000-0000-0000-0000-000000000002',(public.linkautowork_claim_retry('00000000-0000-0000-0000-000000000002')->>'id')::uuid,true,null);
select public.assert_true((select status='delivered' from lautowork.operation_retry_outbox), 'retry delivery completion is durable');
select public.assert_true((public.linkautowork_execute_instance_pause('00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','evidence://approval/retry')->>'state')='paused', 'allowlisted approved pause changes instance state');
select public.assert_true(jsonb_array_length(public.linkautowork_run_maintenance_checks('00000000-0000-0000-0000-000000000002')) >= 1, 'maintenance checks are durable and org scoped');
select public.assert_true(not exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace cross join lateral aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a where n.nspname='public' and p.proname in ('linkautowork_active_pause','linkautowork_authorize_operation_action','linkautowork_deployment_authority','linkautowork_execute_retry','linkautowork_claim_retry','linkautowork_complete_retry') and a.grantee=0 and a.privilege_type='EXECUTE'), 'operations RPCs are not executable by PUBLIC');

update lautowork.automation_deployments set state='planned' where id='50000000-0000-0000-0000-000000000001';
insert into lautowork.automation_deployments(id,org_id,instance_id,release_id,environment,n8n_workflow_id,workflow_digest,configuration_digest,state)
values('50000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','development','n8n-disposable-baseline','sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff','active');
insert into lautowork.automation_deployments(id,org_id,instance_id,release_id,environment,n8n_workflow_id,workflow_digest,configuration_digest,state)
values('50000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','development','n8n-disposable-candidate-2','sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff','planned');
insert into lautowork.approval_requests(id,org_id,subject_type,subject_id,required_role,status) values('72000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','deployment','50000000-0000-0000-0000-000000000001','operator','approved');
insert into lautowork.approval_decisions(org_id,approval_request_id,decision,decided_by_ref,evidence_ref) values('00000000-0000-0000-0000-000000000002','72000000-0000-0000-0000-000000000001','approved','disposable-approver','evidence://approval/deployment');
insert into lautowork.automation_health_snapshots(org_id,instance_id,health_state,summary_ref,details) values('00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','healthy','evidence://health/canary','{"orgId":"00000000-0000-0000-0000-000000000002","instanceId":"40000000-0000-0000-0000-000000000001","state":"healthy"}');
insert into lautowork.automation_executions(id,org_id,instance_id,release_id,deployment_id,idempotency_key,status,completed_at)
values('60000000-0000-0000-0000-000000000030','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','50000000-0000-0000-0000-000000000001','operations-canary-success','succeeded',now());
do $$ declare canary jsonb; promote jsonb; rollback jsonb; replay jsonb; failure jsonb; resolved jsonb; begin
  canary:=public.linkautowork_prepare_deployment_transition('{"orgId":"00000000-0000-0000-0000-000000000002","deploymentId":"50000000-0000-0000-0000-000000000001","action":"canary","idempotencyKey":"canary-disposable-1","actor":"operator","reason":"canary proof"}'::jsonb);
  perform public.linkautowork_commit_deployment_transition('00000000-0000-0000-0000-000000000002',(canary->>'transitionId')::uuid,'{"id":"83000000-0000-0000-0000-000000000001","evidenceDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'::jsonb);
  if (select state from lautowork.automation_deployments where id='50000000-0000-0000-0000-000000000003')<>'active' or (select state from lautowork.automation_deployments where id='50000000-0000-0000-0000-000000000001')<>'canary' then raise exception 'active baseline and canary do not coexist'; end if;
  resolved:=public.linkautowork_resolve_bound_instance('00000000-0000-0000-0000-000000000002','linksites','linksites.reminder.run');
  if resolved->>'deploymentId'<>'50000000-0000-0000-0000-000000000003' or resolved->>'canaryDeploymentId'<>'50000000-0000-0000-0000-000000000001' then raise exception 'resolver did not expose authoritative baseline and canary'; end if;
  promote:=public.linkautowork_prepare_deployment_transition('{"orgId":"00000000-0000-0000-0000-000000000002","deploymentId":"50000000-0000-0000-0000-000000000001","action":"promote","idempotencyKey":"promote-disposable-1","actor":"operator","reason":"promotion proof"}'::jsonb);
  perform public.linkautowork_commit_deployment_transition('00000000-0000-0000-0000-000000000002',(promote->>'transitionId')::uuid,'{"id":"83000000-0000-0000-0000-000000000002","evidenceDigest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}'::jsonb);
  resolved:=public.linkautowork_resolve_bound_instance('00000000-0000-0000-0000-000000000002','linksites','linksites.reminder.run');
  if resolved->>'deploymentId'<>'50000000-0000-0000-0000-000000000001' or resolved->>'canaryDeploymentId' is not null then raise exception 'promotion did not atomically replace the active baseline'; end if;
  replay:=public.linkautowork_prepare_deployment_transition('{"orgId":"00000000-0000-0000-0000-000000000002","deploymentId":"50000000-0000-0000-0000-000000000001","action":"promote","idempotencyKey":"promote-disposable-1","actor":"operator","reason":"replay"}'::jsonb);
  if replay->>'disposition'<>'replay' then raise exception 'committed promotion did not replay'; end if;
  rollback:=public.linkautowork_prepare_deployment_transition('{"orgId":"00000000-0000-0000-0000-000000000002","deploymentId":"50000000-0000-0000-0000-000000000001","action":"rollback","idempotencyKey":"rollback-disposable-1","actor":"operator","reason":"rollback proof"}'::jsonb);
  perform public.linkautowork_commit_deployment_transition('00000000-0000-0000-0000-000000000002',(rollback->>'transitionId')::uuid,'{"id":"83000000-0000-0000-0000-000000000003","evidenceDigest":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}'::jsonb);
  if (select state from lautowork.automation_deployments where id='50000000-0000-0000-0000-000000000003')<>'active' or (select state from lautowork.automation_deployments where id='50000000-0000-0000-0000-000000000001')<>'rolled_back' then raise exception 'rollback did not restore the prior certified baseline'; end if;
  failure:=public.linkautowork_prepare_deployment_transition('{"orgId":"00000000-0000-0000-0000-000000000002","deploymentId":"50000000-0000-0000-0000-000000000001","action":"rollback","idempotencyKey":"rollback-compensation-failed","actor":"operator","reason":"failure"}'::jsonb);
  perform public.linkautowork_fail_deployment_transition('00000000-0000-0000-0000-000000000002',(failure->>'transitionId')::uuid,'database commit and compensation failed',true);
end $$;
select public.assert_true(exists(select 1 from lautowork.automation_incidents where incident_key like 'deployment-compensation-%' and status='open'),'failed compensation opens durable unresolved incident');

select 'WP-08 durable operations verification passed' as result;
