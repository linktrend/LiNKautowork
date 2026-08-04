\set ON_ERROR_STOP on

-- Durable operator-console fixtures. These rows use the existing control
-- tables and state machines; there is no façade or arbitrary test table.
insert into lautowork.automation_products(id,org_id,definition_id,offering_key,display_name,status)
values ('90000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001','browser-managed','Browser Managed Automation','active') on conflict (id) do nothing;
insert into lautowork.automation_incidents(id,org_id,instance_id,severity,status,incident_key)
values ('91000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','warning','open','browser-proof-incident') on conflict (id) do nothing;

insert into lautowork.automation_definitions(id,org_id,automation_id,display_name,summary,owning_program,owner_kind,classification)
values ('10000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000002','operator-certification-fixture','Operator Certification Fixture','A durable evaluation-backed release used to prove separated operator certification.','linkautowork','shared_internal','internal_only') on conflict (id) do nothing;
insert into lautowork.automation_releases(id,org_id,definition_id,version,channel,lifecycle,package_digest,workflow_digest,source_git_sha,n8n_version,package_path)
values ('20000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000004','1.0.0','stable','eval_pending','sha256:4444444444444444444444444444444444444444444444444444444444444444','sha256:5555555555555555555555555555555555555555555555555555555555555555','4444444444444444444444444444444444444444','2.30.0','automations/catalog/operator-certification-fixture/1.0.0') on conflict (id) do nothing;
insert into lautowork.automation_eval_runs(id,org_id,release_id,suite_digest,package_digest,workflow_digest,n8n_version,status,independent_verdict,evaluator_ref,completed_at,receipt_ref)
values ('30000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000002','20000000-0000-0000-0000-000000000004','sha256:6666666666666666666666666666666666666666666666666666666666666666','sha256:4444444444444444444444444444444444444444444444444444444444444444','sha256:5555555555555555555555555555555555555555555555555555555555555555','2.30.0','passed',true,'operator-fixture-evaluator',now(),'evidence://operator/eval/certification') on conflict (id) do nothing;
insert into lautowork.automation_librarian_candidates(id,org_id,deduplication_key,automation_id,status,proposer_ref,candidate)
values ('a0000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','sha256:7777777777777777777777777777777777777777777777777777777777777777','client-a-reminder','awaiting_review','librarian-proposer','{"summary":"Durable candidate awaiting independent operator review","audit":{"transitions":[{"evidenceRef":"evidence://operator/candidate/review"}]}}'::jsonb) on conflict (id,org_id) do nothing;

update lautowork.automation_instances set configuration = configuration || '{"remediation_allowlist":["retry","pause_instance"],"canary_min_samples":1,"canary_min_window_ms":0}'::jsonb where id='40000000-0000-0000-0000-000000000001';
insert into lautowork.automation_bindings(org_id,instance_id,consumer_system,binding_operation)
values ('00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','operator-fixture','operator-fixture.run') on conflict (org_id,consumer_system,binding_operation) do nothing;
insert into lautowork.automation_deployments(id,org_id,instance_id,release_id,environment,n8n_workflow_id,workflow_digest,configuration_digest,state)
select '50000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','stage','operator-fixture-baseline','sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff','active'
where not exists (select 1 from lautowork.automation_deployments where org_id='00000000-0000-0000-0000-000000000002' and instance_id='40000000-0000-0000-0000-000000000001' and state='active');
insert into lautowork.automation_deployments(id,org_id,instance_id,release_id,environment,n8n_workflow_id,workflow_digest,configuration_digest,state)
values
 ('50000000-0000-0000-0000-000000000011','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','stage','operator-fixture-candidate','sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff','planned') on conflict (id) do nothing;
insert into lautowork.automation_health_snapshots(org_id,instance_id,health_state,summary_ref,details)
values ('00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','healthy','evidence://operator/health/canary','{"state":"healthy","source":"operator-fixture"}'::jsonb);
insert into lautowork.automation_executions(id,org_id,instance_id,release_id,deployment_id,idempotency_key,status,completed_at,evidence_ref)
values ('60000000-0000-0000-0000-000000000012','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','50000000-0000-0000-0000-000000000011','operator-canary-success','succeeded',now(),'evidence://operator/execution/canary') on conflict (id) do nothing;
insert into lautowork.approval_requests(id,org_id,subject_type,subject_id,required_role,status)
values ('72000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000002','deployment','50000000-0000-0000-0000-000000000011','approver','approved') on conflict (id,org_id) do nothing;
insert into lautowork.approval_decisions(org_id,approval_request_id,decision,decided_by_ref,evidence_ref)
select '00000000-0000-0000-0000-000000000002','72000000-0000-0000-0000-000000000010','approved','operator-fixture-approver','evidence://operator/approval/deployment' where not exists (select 1 from lautowork.approval_decisions where approval_request_id='72000000-0000-0000-0000-000000000010');

insert into lautowork.provisioning_requests(id,org_id,instance_id,requested_release_id,status,request_ref)
values ('92000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','failed','operator-retry-fixture') on conflict (id) do nothing;
insert into lautowork.provisioning_steps(org_id,request_id,step_key,status,evidence_ref)
values ('00000000-0000-0000-0000-000000000002','92000000-0000-0000-0000-000000000001','workflow-copy','failed','evidence://operator/provisioning/failed') on conflict (request_id,step_key) do nothing;
insert into lautowork.product_orders(id,org_id,product_ref,idempotency_key)
values ('b0000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','browser-managed','operator-fixture-order') on conflict (id) do nothing;
insert into lautowork.product_subscriptions(id,org_id,order_id,status,automation_instance_id,requested_release_id,idempotency_key)
values ('c0000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','b0000000-0000-0000-0000-000000000001','failed','40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','operator-fixture-subscription') on conflict (id) do nothing;

insert into lautowork.maintenance_cases(id,org_id,instance_id,status,classification)
values ('d0000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000001','open','release') on conflict (id) do nothing;
insert into lautowork.approval_requests(id,org_id,subject_type,subject_id,required_role,status)
values ('72000000-0000-0000-0000-000000000011','00000000-0000-0000-0000-000000000002','maintenance','40000000-0000-0000-0000-000000000001','operator','approved') on conflict (id,org_id) do nothing;
insert into lautowork.approval_decisions(org_id,approval_request_id,decision,decided_by_ref,evidence_ref)
select '00000000-0000-0000-0000-000000000002','72000000-0000-0000-0000-000000000011','approved','operator-fixture-approver','evidence://operator/approval/maintenance-retry' where not exists (select 1 from lautowork.approval_decisions where approval_request_id='72000000-0000-0000-0000-000000000011');
