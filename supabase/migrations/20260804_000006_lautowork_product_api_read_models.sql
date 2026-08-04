-- Durable, finite read/action RPCs used exclusively by the Product API.
-- They deliberately expose safe projections, never table access, SQL, credentials, or workflows.
-- migrate:up

create or replace function public.linkautowork_product_published_products(p_limit integer,p_cursor text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_offset integer:=coalesce(nullif(p_cursor,'')::integer,0); begin
  if p_limit < 1 or p_limit > 100 or v_offset < 0 then raise exception 'invalid cursor'; end if;
  return jsonb_build_object('items',coalesce((select jsonb_agg(jsonb_build_object('id',p.id,'name',p.display_name,'summary',d.summary,'signupPrerequisites',jsonb_build_array('operator-assisted configuration'),'version',1) order by p.created_at desc)
    from (select * from automation_products where status='active' order by created_at desc offset v_offset limit p_limit) p join automation_definitions d on d.id=p.definition_id and d.org_id=p.org_id),'[]'::jsonb));
end $$;

-- A subscription may be created only after durable terms acceptance. For a published
-- offering, its pre-approved same-org instance/release is the only eligible target.
create or replace function public.linkautowork_product_create_subscription(p_order_id uuid,p_idempotency_key text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare s product_subscriptions%rowtype; v_org uuid:=lautowork.product_api_org(); v_instance automation_instances%rowtype; begin
 perform lautowork.assert_product_api_authorized(v_org); perform 1 from product_orders where id=p_order_id and org_id=v_org; if not found then raise exception 'order not found in organization'; end if;
 perform 1 from product_terms_acceptances where order_id=p_order_id; if not found then raise exception 'terms acceptance is required before subscription'; end if; perform 1 from commercial_lifecycles where order_id=p_order_id and org_id=v_org and state='awaiting_configuration'; if not found then raise exception 'commercial lifecycle is not ready for configuration'; end if;
 select i.* into v_instance from automation_instances i join product_orders o on o.id=p_order_id join automation_products p on p.id=o.product_ref::uuid where i.org_id=v_org and i.definition_id=p.definition_id and i.release_id is not null and i.state in ('ready','active') order by i.created_at limit 1;
 if not found then raise exception 'operator has not assigned an approved automation target'; end if;
 insert into product_subscriptions(org_id,order_id,status,automation_instance_id,requested_release_id,idempotency_key) values(v_org,p_order_id,'eligible',v_instance.id,v_instance.release_id,p_idempotency_key) on conflict(org_id,idempotency_key) do update set order_id=product_subscriptions.order_id returning * into s;
 return jsonb_build_object('id',s.id,'orgId',s.org_id,'status',s.status,'summary',s.order_id,'version',1); end $$;

create or replace function public.linkautowork_product_client_instances(p_limit integer,p_cursor text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); v_offset integer:=coalesce(nullif(p_cursor,'')::integer,0); begin perform lautowork.assert_product_api_authorized(v_org); if p_limit<1 or p_limit>100 or v_offset<0 then raise exception 'invalid cursor'; end if;
 return jsonb_build_object('items',coalesce((select jsonb_agg(jsonb_build_object('id',i.id,'orgId',i.org_id,'state',i.state,'configurationStatus','operator_assisted_required','deploymentStatus',coalesce((select d.state from automation_deployments d where d.instance_id=i.id and d.org_id=i.org_id order by d.created_at desc limit 1),'not_deployed'),'health','healthy','executions','[]'::jsonb,'incidents','[]'::jsonb,'approvedOutputs','[]'::jsonb,'supportRequests','[]'::jsonb) order by i.created_at) from (select * from automation_instances where org_id=v_org order by created_at offset v_offset limit p_limit) i),'[]'::jsonb)); end $$;

create or replace function public.linkautowork_product_client_portal(p_area text,p_limit integer,p_cursor text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_org uuid:=lautowork.product_api_org(); v_offset integer:=coalesce(nullif(p_cursor,'')::integer,0); v_items jsonb; begin perform lautowork.assert_product_api_authorized(v_org); if p_limit<1 or p_limit>100 or v_offset<0 then raise exception 'invalid cursor'; end if;
 if p_area='orders' then select coalesce(jsonb_agg(jsonb_build_object('id',id,'orgId',org_id,'status',status,'summary',product_ref,'version',1) order by created_at),'[]'::jsonb) into v_items from (select * from product_orders where org_id=v_org order by created_at offset v_offset limit p_limit) q;
 elsif p_area='subscriptions' then select coalesce(jsonb_agg(jsonb_build_object('id',id,'orgId',org_id,'status',status,'summary',order_id,'version',1) order by created_at),'[]'::jsonb) into v_items from (select * from product_subscriptions where org_id=v_org order by created_at offset v_offset limit p_limit) q;
 elsif p_area='configuration' then select coalesce(jsonb_agg(jsonb_build_object('id',id,'orgId',org_id,'status',status,'summary','safe configuration submitted','version',1) order by created_at),'[]'::jsonb) into v_items from (select * from product_configuration_submissions where org_id=v_org order by created_at offset v_offset limit p_limit) q;
 elsif p_area='provisioning' then select coalesce(jsonb_agg(jsonb_build_object('id',id,'orgId',org_id,'status',status,'summary','WP-05 provisioning request','version',1) order by created_at),'[]'::jsonb) into v_items from (select * from provisioning_requests where org_id=v_org and request_ref like 'product-subscription:%' order by created_at offset v_offset limit p_limit) q;
 elsif p_area='supportRequests' then v_items:='[]'::jsonb;
 else raise exception 'unknown portal area'; end if; return jsonb_build_object('items',v_items); end $$;

create or replace function public.linkautowork_product_operator_records(p_resource text,p_limit integer,p_cursor text) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare v_offset integer:=coalesce(nullif(p_cursor,'')::integer,0); v_items jsonb; begin if p_limit<1 or p_limit>100 or v_offset<0 then raise exception 'invalid cursor'; end if;
 if p_resource='incidents' then select coalesce(jsonb_agg(jsonb_build_object('id',id,'orgId',org_id,'state',status,'version',1,'summary','[redacted]') order by opened_at),'[]'::jsonb) into v_items from (select * from automation_incidents order by opened_at offset v_offset limit p_limit) q;
 elsif p_resource='deployments' then select coalesce(jsonb_agg(jsonb_build_object('id',id,'orgId',org_id,'state',state,'version',1,'summary','deployment state') order by created_at),'[]'::jsonb) into v_items from (select * from automation_deployments order by created_at offset v_offset limit p_limit) q;
 else v_items:='[]'::jsonb; end if; return jsonb_build_object('items',v_items); end $$;

create or replace function public.linkautowork_product_operator_action(p_resource text,p_id uuid,p_action text,p_reason text,p_idempotency_key text,p_expected_version integer) returns jsonb language plpgsql security definer set search_path=lautowork,pg_temp as $$
declare i automation_incidents%rowtype; begin if p_resource='incidents' and p_action='acknowledge' then select * into strict i from automation_incidents where id=p_id for update; if i.status<>'open' then raise exception 'invalid transition'; end if; update automation_incidents set status='acknowledged' where id=i.id; insert into automation_incident_events(org_id,incident_id,event_type,actor_ref,evidence_ref) values(i.org_id,i.id,'acknowledged','product-api','evidence://product-api/operator-action'); return jsonb_build_object('id',i.id,'orgId',i.org_id,'state','acknowledged','version',2,'summary','[redacted]'); end if; raise exception 'invalid transition'; end $$;

do $$ declare f record; begin for f in select p.oid::regprocedure sig from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname in ('linkautowork_product_published_products','linkautowork_product_client_instances','linkautowork_product_client_portal','linkautowork_product_operator_records','linkautowork_product_operator_action') loop execute format('revoke all on function %s from public',f.sig); execute format('grant execute on function %s to service_role, svc_lautowork_runtime',f.sig); end loop; end $$;

-- migrate:down
drop function if exists public.linkautowork_product_operator_action(text,uuid,text,text,text,integer);
drop function if exists public.linkautowork_product_operator_records(text,integer,text);
drop function if exists public.linkautowork_product_client_portal(text,integer,text);
drop function if exists public.linkautowork_product_client_instances(integer,text);
drop function if exists public.linkautowork_product_published_products(integer,text);
