-- LiNKautowork automation catalogue and operational-control model (WP-04).
--
-- Prerequisites (owned outside this packet):
--   * LiNKplatform platform.organizations and platform.has_org_access().
--   * 20260715_000001_lautowork_control_core.sql and
--     20260718_000001_lautowork_control_persistence.sql.
--
-- This is additive. It never changes n8n's upstream-owned lautowork_n8n schema,
-- existing MVO tables, or platform objects. Do not apply it to a live project
-- until LiNKplatform has reviewed the manifest under docs/contracts/.

-- migrate:up

create or replace function lautowork.jsonb_has_secret_shaped_key(value jsonb)
returns boolean
language sql
immutable
set search_path = lautowork, pg_temp
as $$
  select coalesce(
    value::text ~* '"(password|passwd|secret|token|api[_-]?key|private[_-]?key|credential|connection[_-]?string)"[[:space:]]*:'
    or value::text ~* '(postgres(ql)?|mysql|mongodb(\+srv)?|redis|amqp)://[^"[:space:]\\]+:[^"[:space:]@\\]+@'
    or value::text ~* '(^|[^[:alnum:]])bearer[[:space:]]+[a-z0-9._~+/-]{8,}'
    or value::text ~* '-----begin[[:space:]][a-z ]*private[[:space:]]key-----'
    or value::text ~* '(^|[^[:alnum:]_])(sk|pk|ghp|xox[baprs])[_-][a-z0-9-]{12,}',
    false
  );
$$;

-- SECURITY DEFINER commands deliberately derive the target organisation from
-- the addressed record. p_org_id is retained as a consistency guard for the
-- API contract, never as an authority grant. Canonical request claims are set
-- only by the authenticated database/API boundary. A fixed service-role JWT
-- delegates the canonical organisation through the Product API's governed
-- request-claims header; an organisation-scoped runtime JWT names it directly.
create or replace function lautowork.assert_command_authorized(p_target_org_id uuid)
returns void
language plpgsql
stable
set search_path = lautowork, pg_temp
as $$
declare
  claims jsonb := coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
  headers jsonb := coalesce(nullif(current_setting('request.headers', true), '')::jsonb, '{}'::jsonb);
  delegated_claims jsonb := coalesce(nullif(headers->>'x-link-request-claims', '')::jsonb, '{}'::jsonb);
  test_context boolean := coalesce(current_setting('lautowork.test_context', true), 'off') = 'on';
  claim_org_id text;
  claim_role text;
  transport_role text;
  header_org_id text;
begin
  claim_org_id := claims->>'org_id';
  claim_role := claims->>'role';
  transport_role := claim_role;
  header_org_id := headers->>'x-link-org-id';
  if test_context then
    claim_org_id := coalesce(claim_org_id, nullif(current_setting('request.jwt.claim.org_id', true), ''));
    claim_role := coalesce(claim_role, nullif(current_setting('request.jwt.claim.role', true), ''));
    transport_role := claim_role;
    header_org_id := coalesce(header_org_id, claim_org_id);
  end if;
  if transport_role = 'service_role'
     and delegated_claims->>'role' = 'service_role' then
    claim_org_id := coalesce(claim_org_id, delegated_claims->>'org_id');
  end if;
  if claim_org_id is distinct from p_target_org_id::text then
    raise exception 'command is not authorized for target organization';
  end if;
  if header_org_id is distinct from p_target_org_id::text then
    raise exception 'request organization header does not match authorized organization';
  end if;

  if claim_role in ('service_role', 'svc_lautowork_runtime') then
    return;
  end if;

  if platform.has_org_access(p_target_org_id, 'client_viewer') then
    return;
  end if;

  raise exception 'caller has no membership authority for target organization';
end;
$$;

create table if not exists lautowork.automation_definitions (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  automation_id text not null check (automation_id ~ '^[a-z][a-z0-9-]{2,62}$'),
  display_name text not null check (char_length(display_name) between 3 and 160),
  summary text not null check (char_length(summary) between 20 and 1200),
  owning_program text not null check (owning_program ~ '^[a-z][a-z0-9-]{1,63}$'),
  owner_kind text not null check (owner_kind in ('internal_system', 'commercial_product', 'shared_internal')),
  classification text not null check (classification in ('internal_only', 'commercial_capable')),
  created_at timestamptz not null default now(),
  created_by text not null default 'system',
  unique (org_id, automation_id),
  unique (id, org_id)
);

create table if not exists lautowork.automation_releases (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  definition_id uuid not null,
  version text not null check (version ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$'),
  channel text not null check (channel in ('development', 'canary', 'stable')),
  lifecycle text not null check (lifecycle in ('draft', 'eval_pending', 'certified', 'deprecated', 'retired')),
  package_digest text not null check (package_digest ~ '^sha256:[a-f0-9]{64}$'),
  workflow_digest text not null check (workflow_digest ~ '^sha256:[a-f0-9]{64}$'),
  source_git_sha text not null check (source_git_sha ~ '^[a-f0-9]{40}$'),
  n8n_version text not null check (n8n_version ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$'),
  package_path text not null check (package_path ~ '^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9][A-Za-z0-9._/-]*$'),
  created_at timestamptz not null default now(),
  created_by text not null default 'system',
  certified_at timestamptz,
  retired_at timestamptz,
  foreign key (definition_id, org_id) references lautowork.automation_definitions(id, org_id) on delete restrict,
  unique (definition_id, org_id, version),
  unique (package_digest),
  unique (id, org_id)
);

create table if not exists lautowork.automation_sources (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  release_id uuid not null,
  source_id text not null check (source_id ~ '^[a-z][a-z0-9-]{2,127}$'),
  source_kind text not null check (source_kind in ('n8n_template', 'make', 'zapier', 'github', 'oss', 'documentation', 'internal')),
  locator text not null check (char_length(locator) <= 2048),
  revision text not null check (char_length(revision) between 1 and 512),
  content_digest text not null check (content_digest ~ '^sha256:[a-f0-9]{64}$'),
  licence text not null check (char_length(licence) between 1 and 240),
  commercial_use text not null check (commercial_use in ('not_applicable', 'cleared', 'requires_review', 'prohibited')),
  review_status text not null check (review_status in ('pending', 'resolved', 'rejected')),
  adaptation_status text not null check (adaptation_status in ('reference_only', 'adapted', 'composed')),
  created_at timestamptz not null default now(),
  foreign key (release_id, org_id) references lautowork.automation_releases(id, org_id) on delete restrict,
  unique (release_id, source_id)
);

create table if not exists lautowork.automation_products (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  definition_id uuid not null,
  offering_key text not null check (offering_key ~ '^[a-z][a-z0-9-]{2,62}$'),
  display_name text not null check (char_length(display_name) between 3 and 160),
  status text not null check (status in ('draft', 'active', 'paused', 'retired')),
  created_at timestamptz not null default now(),
  foreign key (definition_id, org_id) references lautowork.automation_definitions(id, org_id) on delete restrict,
  unique (org_id, offering_key),
  unique (id, org_id)
);

create table if not exists lautowork.automation_instances (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  definition_id uuid not null,
  release_id uuid not null,
  product_id uuid,
  instance_key text not null check (instance_key ~ '^[a-z][a-z0-9-]{2,62}$'),
  state text not null check (state in ('draft', 'provisioning', 'ready', 'active', 'paused', 'failed', 'retired')),
  configuration jsonb not null default '{}'::jsonb check (not lautowork.jsonb_has_secret_shaped_key(configuration)),
  configuration_digest text not null check (configuration_digest ~ '^sha256:[a-f0-9]{64}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (definition_id, org_id) references lautowork.automation_definitions(id, org_id) on delete restrict,
  foreign key (release_id, org_id) references lautowork.automation_releases(id, org_id) on delete restrict,
  -- Product offerings are provider-owned commercial metadata. They may be
  -- selected during client provisioning, but an instance's security boundary
  -- is its own org_id; do not make a client instance impersonate the provider.
  foreign key (product_id) references lautowork.automation_products(id) on delete restrict,
  unique (org_id, instance_key),
  unique (id, org_id)
);

create table if not exists lautowork.automation_bindings (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  instance_id uuid not null,
  consumer_system text not null check (consumer_system ~ '^[a-z][a-z0-9-]{1,63}$'),
  binding_operation text not null check (binding_operation ~ '^[a-z][a-z0-9._-]{2,127}$'),
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  foreign key (instance_id, org_id) references lautowork.automation_instances(id, org_id) on delete restrict,
  unique (org_id, consumer_system, binding_operation),
  unique (id, org_id)
);

create table if not exists lautowork.automation_secret_bindings (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  instance_id uuid not null,
  secret_ref text not null check (secret_ref ~ '^[A-Z][A-Z0-9_]{2,127}$'),
  purpose text not null check (char_length(purpose) between 3 and 240),
  scope text not null check (scope in ('instance', 'connector')),
  required boolean not null,
  health_state text not null default 'unknown' check (health_state in ('unknown', 'healthy', 'expiring', 'invalid', 'revoked')),
  expires_at timestamptz,
  rotation_due_at timestamptz,
  created_at timestamptz not null default now(),
  foreign key (instance_id, org_id) references lautowork.automation_instances(id, org_id) on delete restrict,
  unique (instance_id, secret_ref)
);

create table if not exists lautowork.provisioning_requests (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  instance_id uuid not null,
  requested_release_id uuid not null,
  status text not null check (status in ('requested', 'awaiting_configuration', 'provisioning', 'ready_for_review', 'completed', 'failed', 'cancelled')),
  request_ref text not null check (char_length(request_ref) between 1 and 512),
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  foreign key (instance_id, org_id) references lautowork.automation_instances(id, org_id) on delete restrict,
  foreign key (requested_release_id, org_id) references lautowork.automation_releases(id, org_id) on delete restrict,
  unique (id, org_id)
);

create table if not exists lautowork.provisioning_steps (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  request_id uuid not null,
  step_key text not null check (step_key ~ '^[a-z][a-z0-9-]{2,127}$'),
  status text not null check (status in ('pending', 'running', 'blocked', 'completed', 'failed', 'skipped')),
  evidence_ref text,
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  foreign key (request_id, org_id) references lautowork.provisioning_requests(id, org_id) on delete restrict,
  unique (request_id, step_key)
);

create or replace function lautowork.reject_unprovisionable_release()
returns trigger
language plpgsql
set search_path = lautowork, pg_temp
as $$
declare
  release_lifecycle text;
begin
  select lifecycle into release_lifecycle from lautowork.automation_releases
  where id = new.requested_release_id and org_id = new.org_id;
  if release_lifecycle is distinct from 'certified' then
    raise exception 'only certified releases may be provisioned (release lifecycle: %)', coalesce(release_lifecycle, 'missing');
  end if;
  return new;
end;
$$;

create trigger provisioning_requires_certified_release
before insert or update of requested_release_id, org_id on lautowork.provisioning_requests
for each row execute function lautowork.reject_unprovisionable_release();

create table if not exists lautowork.automation_deployments (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  instance_id uuid not null,
  release_id uuid not null,
  environment text not null check (environment in ('development', 'stage', 'production')),
  n8n_workflow_id text not null check (char_length(n8n_workflow_id) between 1 and 255),
  workflow_digest text not null check (workflow_digest ~ '^sha256:[a-f0-9]{64}$'),
  configuration_digest text not null check (configuration_digest ~ '^sha256:[a-f0-9]{64}$'),
  state text not null check (state in ('planned', 'provisioning', 'canary', 'active', 'paused', 'rolled_back', 'retired', 'failed')),
  deployed_at timestamptz,
  retired_at timestamptz,
  created_at timestamptz not null default now(),
  foreign key (instance_id, org_id) references lautowork.automation_instances(id, org_id) on delete restrict,
  foreign key (release_id, org_id) references lautowork.automation_releases(id, org_id) on delete restrict,
  unique (org_id, environment, n8n_workflow_id),
  unique (id, org_id)
);

create table if not exists lautowork.automation_executions (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  instance_id uuid not null,
  release_id uuid not null,
  deployment_id uuid not null,
  idempotency_key text not null check (char_length(idempotency_key) between 1 and 255),
  status text not null check (status in ('accepted', 'started', 'succeeded', 'failed', 'cancelled', 'timed_out')),
  accepted_at timestamptz not null default now(),
  completed_at timestamptz,
  latency_ms integer check (latency_ms is null or latency_ms >= 0),
  retry_count integer not null default 0 check (retry_count >= 0),
  failure_class text,
  evidence_ref text,
  input_digest text check (input_digest is null or input_digest ~ '^sha256:[a-f0-9]{64}$'),
  output_digest text check (output_digest is null or output_digest ~ '^sha256:[a-f0-9]{64}$'),
  foreign key (instance_id, org_id) references lautowork.automation_instances(id, org_id) on delete restrict,
  foreign key (release_id, org_id) references lautowork.automation_releases(id, org_id) on delete restrict,
  foreign key (deployment_id, org_id) references lautowork.automation_deployments(id, org_id) on delete restrict,
  unique (org_id, instance_id, idempotency_key),
  unique (id, org_id)
);

create table if not exists lautowork.automation_execution_events (
  id bigserial primary key,
  org_id uuid not null,
  execution_id uuid not null,
  sequence integer not null check (sequence > 0),
  event_type text not null check (event_type in ('accepted', 'started', 'checkpoint', 'succeeded', 'failed', 'cancelled', 'timed_out')),
  occurred_at timestamptz not null,
  payload_digest text check (payload_digest is null or payload_digest ~ '^sha256:[a-f0-9]{64}$'),
  evidence_ref text,
  created_at timestamptz not null default now(),
  foreign key (execution_id, org_id) references lautowork.automation_executions(id, org_id) on delete restrict,
  unique (execution_id, sequence)
);

create table if not exists lautowork.automation_eval_runs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  release_id uuid not null,
  suite_digest text not null check (suite_digest ~ '^sha256:[a-f0-9]{64}$'),
  package_digest text not null check (package_digest ~ '^sha256:[a-f0-9]{64}$'),
  workflow_digest text not null check (workflow_digest ~ '^sha256:[a-f0-9]{64}$'),
  n8n_version text not null,
  status text not null check (status in ('running', 'passed', 'failed', 'cancelled')),
  independent_verdict boolean not null default false,
  evaluator_ref text not null check (char_length(evaluator_ref) between 3 and 512),
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  receipt_ref text,
  foreign key (release_id, org_id) references lautowork.automation_releases(id, org_id) on delete restrict,
  unique (id, org_id)
);

create table if not exists lautowork.automation_eval_results (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  eval_run_id uuid not null,
  case_id text not null check (case_id ~ '^[a-z][a-z0-9-]{2,127}$'),
  fixture_digest text not null check (fixture_digest ~ '^sha256:[a-f0-9]{64}$'),
  status text not null check (status in ('passed', 'failed', 'skipped')),
  assertion_count integer not null default 0 check (assertion_count >= 0),
  evidence_ref text,
  created_at timestamptz not null default now(),
  foreign key (eval_run_id, org_id) references lautowork.automation_eval_runs(id, org_id) on delete restrict,
  unique (eval_run_id, case_id)
);

create table if not exists lautowork.automation_health_snapshots (
  id bigserial primary key,
  org_id uuid not null references platform.organizations(id) on delete restrict,
  instance_id uuid not null,
  health_state text not null check (health_state in ('unknown', 'healthy', 'warning', 'critical', 'paused')),
  observed_at timestamptz not null default now(),
  summary_ref text,
  foreign key (instance_id, org_id) references lautowork.automation_instances(id, org_id) on delete restrict
);

create table if not exists lautowork.automation_alerts (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  instance_id uuid not null,
  dedupe_key text not null check (char_length(dedupe_key) between 3 and 255),
  severity text not null check (severity in ('info', 'warning', 'critical')),
  status text not null check (status in ('open', 'acknowledged', 'resolved')),
  evidence_ref text,
  created_at timestamptz not null default now(),
  resolved_at timestamptz,
  foreign key (instance_id, org_id) references lautowork.automation_instances(id, org_id) on delete restrict,
  unique (org_id, instance_id, dedupe_key, status),
  unique (id, org_id)
);

create table if not exists lautowork.automation_incidents (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  instance_id uuid,
  deployment_id uuid,
  execution_id uuid,
  severity text not null check (severity in ('info', 'warning', 'critical')),
  status text not null check (status in ('open', 'acknowledged', 'investigating', 'mitigated', 'resolved', 'closed')),
  incident_key text not null check (incident_key ~ '^[a-z][a-z0-9-]{2,127}$'),
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  foreign key (instance_id, org_id) references lautowork.automation_instances(id, org_id) on delete restrict,
  foreign key (deployment_id, org_id) references lautowork.automation_deployments(id, org_id) on delete restrict,
  foreign key (execution_id, org_id) references lautowork.automation_executions(id, org_id) on delete restrict,
  unique (org_id, incident_key),
  unique (id, org_id)
);

create table if not exists lautowork.automation_incident_events (
  id bigserial primary key,
  org_id uuid not null,
  incident_id uuid not null,
  event_type text not null check (event_type in ('opened', 'acknowledged', 'investigating', 'mitigated', 'resolved', 'closed', 'note')),
  actor_ref text not null check (char_length(actor_ref) between 1 and 512),
  evidence_ref text,
  created_at timestamptz not null default now(),
  foreign key (incident_id, org_id) references lautowork.automation_incidents(id, org_id) on delete restrict
);

create table if not exists lautowork.maintenance_cases (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  instance_id uuid not null,
  incident_id uuid,
  status text not null check (status in ('open', 'investigating', 'awaiting_approval', 'mitigated', 'resolved', 'closed')),
  classification text not null check (classification in ('platform', 'release', 'instance', 'credential', 'dependency', 'unknown')),
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  foreign key (instance_id, org_id) references lautowork.automation_instances(id, org_id) on delete restrict,
  foreign key (incident_id, org_id) references lautowork.automation_incidents(id, org_id) on delete restrict,
  unique (id, org_id)
);

create table if not exists lautowork.maintenance_case_events (
  id bigserial primary key,
  org_id uuid not null,
  maintenance_case_id uuid not null,
  action text not null check (action in ('detected', 'retry', 'pause', 'rollback', 'diagnose', 'escalate', 'resolved', 'note')),
  actor_ref text not null check (char_length(actor_ref) between 1 and 512),
  before_state_ref text,
  after_state_ref text,
  evidence_ref text,
  created_at timestamptz not null default now(),
  foreign key (maintenance_case_id, org_id) references lautowork.maintenance_cases(id, org_id) on delete restrict
);

create table if not exists lautowork.automation_improvement_candidates (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  definition_id uuid not null,
  base_release_id uuid not null,
  candidate_release_id uuid,
  status text not null check (status in ('proposed', 'evaluating', 'review_required', 'approved', 'rejected', 'withdrawn')),
  opportunity_class text not null check (opportunity_class in ('failure_repair', 'reliability', 'cost', 'compatibility', 'quality', 'security')),
  evidence_ref text not null,
  created_at timestamptz not null default now(),
  foreign key (definition_id, org_id) references lautowork.automation_definitions(id, org_id) on delete restrict,
  foreign key (base_release_id, org_id) references lautowork.automation_releases(id, org_id) on delete restrict,
  foreign key (candidate_release_id, org_id) references lautowork.automation_releases(id, org_id) on delete restrict,
  unique (id, org_id)
);

create table if not exists lautowork.approval_requests (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references platform.organizations(id) on delete restrict,
  subject_type text not null check (subject_type in ('release', 'deployment', 'maintenance', 'improvement_candidate', 'provisioning')),
  subject_id uuid not null,
  required_role text not null check (char_length(required_role) between 3 and 128),
  status text not null check (status in ('pending', 'approved', 'rejected', 'cancelled', 'expired')),
  requested_at timestamptz not null default now(),
  expires_at timestamptz,
  unique (id, org_id)
);

create table if not exists lautowork.approval_decisions (
  id bigserial primary key,
  org_id uuid not null,
  approval_request_id uuid not null,
  decision text not null check (decision in ('approved', 'rejected')),
  decided_by_ref text not null check (char_length(decided_by_ref) between 1 and 512),
  evidence_ref text,
  created_at timestamptz not null default now(),
  foreign key (approval_request_id, org_id) references lautowork.approval_requests(id, org_id) on delete restrict
);

create table if not exists lautowork.automation_domain_audit_events (
  id bigserial primary key,
  org_id uuid not null references platform.organizations(id) on delete restrict,
  event_type text not null check (event_type ~ '^[a-z][a-z0-9._-]{2,127}$'),
  subject_type text not null check (char_length(subject_type) between 1 and 128),
  subject_id uuid,
  actor_ref text not null check (char_length(actor_ref) between 1 and 512),
  evidence_ref text,
  created_at timestamptz not null default now()
);

create index if not exists idx_lautowork_releases_definition on lautowork.automation_releases (org_id, definition_id, created_at desc);
create index if not exists idx_lautowork_instances_release on lautowork.automation_instances (org_id, release_id, state);
create index if not exists idx_lautowork_executions_instance on lautowork.automation_executions (org_id, instance_id, accepted_at desc);
create index if not exists idx_lautowork_execution_events_execution on lautowork.automation_execution_events (org_id, execution_id, sequence);
create index if not exists idx_lautowork_eval_runs_release on lautowork.automation_eval_runs (org_id, release_id, completed_at desc);
create index if not exists idx_lautowork_incidents_org_status on lautowork.automation_incidents (org_id, status, opened_at desc);

-- Composite foreign keys prove an individual reference is in the right
-- organisation. These guards additionally prove that all references describe
-- the *same automation lineage*, rather than merely rows in that organisation.
create or replace function lautowork.assert_instance_lineage()
returns trigger
language plpgsql
set search_path = lautowork, pg_temp
as $$
declare
  release_definition_id uuid;
  product_definition_id uuid;
begin
  select definition_id into release_definition_id
  from lautowork.automation_releases
  where id = new.release_id and org_id = new.org_id;
  if release_definition_id is distinct from new.definition_id then
    raise exception 'instance definition and release definition must match';
  end if;
  if new.product_id is not null then
    select definition_id into product_definition_id
    from lautowork.automation_products where id = new.product_id;
    if product_definition_id is distinct from new.definition_id then
      raise exception 'instance definition and product definition must match';
    end if;
  end if;
  return new;
end;
$$;

create trigger automation_instances_require_coherent_lineage
before insert or update of org_id, definition_id, release_id, product_id on lautowork.automation_instances
for each row execute function lautowork.assert_instance_lineage();

create or replace function lautowork.assert_provisioning_request_lineage()
returns trigger
language plpgsql
set search_path = lautowork, pg_temp
as $$
declare
  instance_release_id uuid;
  instance_definition_id uuid;
  release_definition_id uuid;
begin
  select release_id, definition_id into instance_release_id, instance_definition_id
  from lautowork.automation_instances where id = new.instance_id and org_id = new.org_id;
  select definition_id into release_definition_id
  from lautowork.automation_releases where id = new.requested_release_id and org_id = new.org_id;
  if instance_release_id is distinct from new.requested_release_id
     or instance_definition_id is distinct from release_definition_id then
    raise exception 'provisioning request release must match the instance lineage';
  end if;
  return new;
end;
$$;

create trigger provisioning_requests_require_coherent_lineage
before insert or update of org_id, instance_id, requested_release_id on lautowork.provisioning_requests
for each row execute function lautowork.assert_provisioning_request_lineage();

create or replace function lautowork.assert_deployment_lineage()
returns trigger
language plpgsql
set search_path = lautowork, pg_temp
as $$
declare
  instance_release_id uuid;
  instance_configuration_digest text;
  release_workflow_digest text;
begin
  select release_id, configuration_digest into instance_release_id, instance_configuration_digest
  from lautowork.automation_instances where id = new.instance_id and org_id = new.org_id;
  select workflow_digest into release_workflow_digest
  from lautowork.automation_releases where id = new.release_id and org_id = new.org_id;
  if instance_release_id is distinct from new.release_id
     or release_workflow_digest is distinct from new.workflow_digest
     or instance_configuration_digest is distinct from new.configuration_digest then
    raise exception 'deployment must match the instance release, workflow, and configuration lineage';
  end if;
  return new;
end;
$$;

create trigger automation_deployments_require_coherent_lineage
before insert or update of org_id, instance_id, release_id, workflow_digest, configuration_digest on lautowork.automation_deployments
for each row execute function lautowork.assert_deployment_lineage();

create or replace function lautowork.assert_execution_lineage()
returns trigger
language plpgsql
set search_path = lautowork, pg_temp
as $$
declare
  instance_release_id uuid;
  deployment_instance_id uuid;
  deployment_release_id uuid;
begin
  select release_id into instance_release_id from lautowork.automation_instances
  where id = new.instance_id and org_id = new.org_id;
  select instance_id, release_id into deployment_instance_id, deployment_release_id
  from lautowork.automation_deployments where id = new.deployment_id and org_id = new.org_id;
  if instance_release_id is distinct from new.release_id
     or deployment_instance_id is distinct from new.instance_id
     or deployment_release_id is distinct from new.release_id then
    raise exception 'execution must match the instance and deployment lineage';
  end if;
  return new;
end;
$$;

create trigger automation_executions_require_coherent_lineage
before insert or update of org_id, instance_id, release_id, deployment_id on lautowork.automation_executions
for each row execute function lautowork.assert_execution_lineage();

-- Only release lifecycle changes performed through the controlled functions below
-- are permitted. A replacement is always a new immutable release row.
create or replace function lautowork.reject_immutable_release_mutation()
returns trigger
language plpgsql
set search_path = lautowork, pg_temp
as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'automation releases are immutable and cannot be deleted';
  end if;
  if current_setting('lautowork.allow_release_lifecycle_update', true) <> 'on' then
    raise exception 'automation releases are immutable; use a controlled lifecycle transition';
  end if;
  if (to_jsonb(new) - 'lifecycle' - 'certified_at' - 'retired_at')
     is distinct from (to_jsonb(old) - 'lifecycle' - 'certified_at' - 'retired_at') then
    raise exception 'only release lifecycle timestamps may change';
  end if;
  return new;
end;
$$;

create trigger automation_releases_immutable
before update or delete on lautowork.automation_releases
for each row execute function lautowork.reject_immutable_release_mutation();

create or replace function lautowork.reject_append_only_mutation()
returns trigger
language plpgsql
set search_path = lautowork, pg_temp
as $$
begin
  raise exception '% is append-only; update/delete is forbidden', tg_table_name;
end;
$$;

do $$
declare
  table_name text;
  append_only_tables text[] := array[
    'automation_sources', 'automation_execution_events', 'automation_eval_results',
    'automation_health_snapshots', 'automation_incident_events',
    'maintenance_case_events', 'approval_decisions', 'automation_domain_audit_events'
  ];
begin
  foreach table_name in array append_only_tables loop
    execute format('create trigger %I before update or delete on lautowork.%I for each row execute function lautowork.reject_append_only_mutation()', table_name || '_append_only', table_name);
  end loop;
end $$;

-- Lifecycle transitions are intentionally narrow. Certification additionally
-- requires an independent, passed, hash-matching evaluation receipt.
create or replace function public.linkautowork_certify_automation_release(
  p_org_id uuid,
  p_release_id uuid,
  p_evaluator_ref text,
  p_reason text
)
returns void
language plpgsql
security definer
set search_path = lautowork, pg_temp
as $$
declare
  release_row lautowork.automation_releases%rowtype;
begin
  select * into release_row from lautowork.automation_releases where id = p_release_id for update;
  if not found then raise exception 'release does not exist'; end if;
  if p_org_id is distinct from release_row.org_id then raise exception 'requested organization does not match release organization'; end if;
  perform lautowork.assert_command_authorized(release_row.org_id);
  if release_row.lifecycle <> 'eval_pending' then raise exception 'only eval_pending releases may be certified'; end if;
  if not exists (
    select 1 from lautowork.automation_eval_runs r
    where r.org_id = p_org_id and r.release_id = p_release_id and r.status = 'passed'
      and r.independent_verdict = true and r.package_digest = release_row.package_digest
      and r.workflow_digest = release_row.workflow_digest and r.n8n_version = release_row.n8n_version
  ) then raise exception 'certification requires independent passing hash-matching evaluation evidence'; end if;
  perform set_config('lautowork.allow_release_lifecycle_update', 'on', true);
  update lautowork.automation_releases set lifecycle = 'certified', certified_at = now() where id = p_release_id;
  insert into lautowork.automation_domain_audit_events (org_id, event_type, subject_type, subject_id, actor_ref, evidence_ref)
  values (p_org_id, 'release.certified', 'automation_release', p_release_id, p_evaluator_ref, p_reason);
end;
$$;

create or replace function public.linkautowork_transition_automation_release(
  p_org_id uuid,
  p_release_id uuid,
  p_to_state text,
  p_actor_ref text,
  p_reason text
)
returns void
language plpgsql
security definer
set search_path = lautowork, pg_temp
as $$
declare
  release_row lautowork.automation_releases%rowtype;
begin
  select * into release_row from lautowork.automation_releases where id = p_release_id for update;
  if not found then raise exception 'release does not exist'; end if;
  if p_org_id is distinct from release_row.org_id then raise exception 'requested organization does not match release organization'; end if;
  perform lautowork.assert_command_authorized(release_row.org_id);
  if not ((release_row.lifecycle = 'certified' and p_to_state = 'deprecated')
       or (release_row.lifecycle = 'deprecated' and p_to_state = 'retired')) then
    raise exception 'invalid release lifecycle transition from % to %', release_row.lifecycle, p_to_state;
  end if;
  perform set_config('lautowork.allow_release_lifecycle_update', 'on', true);
  update lautowork.automation_releases
  set lifecycle = p_to_state, retired_at = case when p_to_state = 'retired' then now() else retired_at end
  where id = p_release_id;
  insert into lautowork.automation_domain_audit_events (org_id, event_type, subject_type, subject_id, actor_ref, evidence_ref)
  values (p_org_id, 'release.lifecycle_transition', 'automation_release', p_release_id, p_actor_ref, p_reason);
end;
$$;

create or replace function public.linkautowork_append_execution_event(
  p_org_id uuid,
  p_execution_id uuid,
  p_sequence integer,
  p_event_type text,
  p_occurred_at timestamptz,
  p_payload_digest text default null,
  p_evidence_ref text default null
)
returns void
language plpgsql
security definer
set search_path = lautowork, pg_temp
as $$
declare
  _target_org_id uuid;
begin
  select org_id into strict _target_org_id from lautowork.automation_executions where id = p_execution_id;
  if p_org_id is distinct from _target_org_id then raise exception 'requested organization does not match execution organization'; end if;
  perform lautowork.assert_command_authorized(_target_org_id);
  insert into lautowork.automation_execution_events (org_id, execution_id, sequence, event_type, occurred_at, payload_digest, evidence_ref)
  values (p_org_id, p_execution_id, p_sequence, p_event_type, p_occurred_at, p_payload_digest, p_evidence_ref);
end;
$$;

create or replace function public.linkautowork_append_approval_decision(
  p_org_id uuid,
  p_request_id uuid,
  p_decision text,
  p_decided_by_ref text,
  p_evidence_ref text default null
)
returns void
language plpgsql
security definer
set search_path = lautowork, pg_temp
as $$
declare
  _target_org_id uuid;
begin
  if p_decision not in ('approved', 'rejected') then raise exception 'invalid approval decision'; end if;
  select org_id into strict _target_org_id from lautowork.approval_requests where id = p_request_id and status = 'pending';
  if p_org_id is distinct from _target_org_id then raise exception 'requested organization does not match approval organization'; end if;
  perform lautowork.assert_command_authorized(_target_org_id);
  insert into lautowork.approval_decisions (org_id, approval_request_id, decision, decided_by_ref, evidence_ref)
  values (p_org_id, p_request_id, p_decision, p_decided_by_ref, p_evidence_ref);
  update lautowork.approval_requests set status = p_decision where id = p_request_id;
end;
$$;

-- RLS applies to every new organisation-scoped table. Runtime writes use the
-- narrow SECURITY DEFINER commands above; no broad table mutation is granted.
do $$
declare
  table_name text;
  org_tables text[] := array[
    'automation_definitions','automation_releases','automation_sources','automation_products',
    'automation_instances','automation_bindings','automation_secret_bindings','provisioning_requests',
    'provisioning_steps','automation_deployments','automation_executions','automation_execution_events',
    'automation_eval_runs','automation_eval_results','automation_health_snapshots','automation_alerts',
    'automation_incidents','automation_incident_events','maintenance_cases','maintenance_case_events',
    'automation_improvement_candidates','approval_requests','approval_decisions','automation_domain_audit_events'
  ];
begin
  foreach table_name in array org_tables loop
    execute format('alter table lautowork.%I enable row level security', table_name);
    execute format('alter table lautowork.%I force row level security', table_name);
    execute format('create policy %I on lautowork.%I for select to svc_lautowork_runtime, svc_observer using (org_id::text = current_setting(''request.jwt.claim.org_id'', true) and (current_setting(''request.jwt.claim.role'', true) = ''service_role'' or platform.has_org_access(org_id, ''client_viewer'')))', 'lautowork_' || table_name || '_select', table_name);
  end loop;
end $$;

grant usage on schema lautowork to svc_lautowork_runtime, svc_observer;
grant select on all tables in schema lautowork to svc_observer;
alter default privileges in schema lautowork grant select on tables to svc_observer;
revoke all on lautowork.automation_definitions, lautowork.automation_releases, lautowork.automation_sources,
  lautowork.automation_products, lautowork.automation_instances, lautowork.automation_bindings,
  lautowork.automation_secret_bindings, lautowork.provisioning_requests, lautowork.provisioning_steps,
  lautowork.automation_deployments, lautowork.automation_executions, lautowork.automation_execution_events,
  lautowork.automation_eval_runs, lautowork.automation_eval_results, lautowork.automation_health_snapshots,
  lautowork.automation_alerts, lautowork.automation_incidents, lautowork.automation_incident_events,
  lautowork.maintenance_cases, lautowork.maintenance_case_events, lautowork.automation_improvement_candidates,
  lautowork.approval_requests, lautowork.approval_decisions, lautowork.automation_domain_audit_events
  from svc_lautowork_runtime;
grant select on lautowork.automation_definitions, lautowork.automation_releases, lautowork.automation_instances,
  lautowork.automation_bindings, lautowork.automation_deployments, lautowork.automation_executions,
  lautowork.automation_eval_runs, lautowork.automation_health_snapshots to svc_lautowork_runtime;

revoke all on function public.linkautowork_certify_automation_release(uuid, uuid, text, text) from public;
revoke all on function public.linkautowork_transition_automation_release(uuid, uuid, text, text, text) from public;
revoke all on function public.linkautowork_append_execution_event(uuid, uuid, integer, text, timestamptz, text, text) from public;
revoke all on function public.linkautowork_append_approval_decision(uuid, uuid, text, text, text) from public;
grant execute on function public.linkautowork_certify_automation_release(uuid, uuid, text, text) to svc_lautowork_runtime;
grant execute on function public.linkautowork_transition_automation_release(uuid, uuid, text, text, text) to svc_lautowork_runtime;
grant execute on function public.linkautowork_append_execution_event(uuid, uuid, integer, text, timestamptz, text, text) to svc_lautowork_runtime;
grant execute on function public.linkautowork_append_approval_decision(uuid, uuid, text, text, text) to svc_lautowork_runtime;

comment on table lautowork.automation_secret_bindings is
  'GSM reference and health metadata only. No raw secret value, credential payload, connection string, or token may be stored here.';
comment on table lautowork.automation_releases is
  'Immutable Golden Automation Package release identity. Lifecycle moves only through controlled functions; all functional changes create a new release.';
comment on table lautowork.automation_execution_events is
  'Append-only, ordered execution evidence. Raw payloads are forbidden; store an approved evidence reference and optional digest only.';

-- migrate:down -- forward fix is preferred. This down section is for a
-- disposable pre-production database only and must never be run against an
-- environment containing operational evidence.
drop table if exists lautowork.automation_domain_audit_events cascade;
drop table if exists lautowork.approval_decisions cascade;
drop table if exists lautowork.approval_requests cascade;
drop table if exists lautowork.automation_improvement_candidates cascade;
drop table if exists lautowork.maintenance_case_events cascade;
drop table if exists lautowork.maintenance_cases cascade;
drop table if exists lautowork.automation_incident_events cascade;
drop table if exists lautowork.automation_incidents cascade;
drop table if exists lautowork.automation_alerts cascade;
drop table if exists lautowork.automation_health_snapshots cascade;
drop table if exists lautowork.automation_eval_results cascade;
drop table if exists lautowork.automation_eval_runs cascade;
drop table if exists lautowork.automation_execution_events cascade;
drop table if exists lautowork.automation_executions cascade;
drop table if exists lautowork.automation_deployments cascade;
drop table if exists lautowork.provisioning_steps cascade;
drop table if exists lautowork.provisioning_requests cascade;
drop table if exists lautowork.automation_secret_bindings cascade;
drop table if exists lautowork.automation_bindings cascade;
drop table if exists lautowork.automation_instances cascade;
drop table if exists lautowork.automation_products cascade;
drop table if exists lautowork.automation_sources cascade;
drop table if exists lautowork.automation_releases cascade;
drop table if exists lautowork.automation_definitions cascade;
drop function if exists public.linkautowork_append_approval_decision(uuid, uuid, text, text, text);
drop function if exists public.linkautowork_append_execution_event(uuid, uuid, integer, text, timestamptz, text, text);
drop function if exists public.linkautowork_transition_automation_release(uuid, uuid, text, text, text);
drop function if exists public.linkautowork_certify_automation_release(uuid, uuid, text, text);
drop function if exists lautowork.assert_execution_lineage();
drop function if exists lautowork.assert_deployment_lineage();
drop function if exists lautowork.assert_provisioning_request_lineage();
drop function if exists lautowork.assert_instance_lineage();
drop function if exists lautowork.reject_append_only_mutation();
drop function if exists lautowork.reject_immutable_release_mutation();
drop function if exists lautowork.reject_unprovisionable_release();
drop function if exists lautowork.assert_command_authorized(uuid);
-- 000011 deliberately retains immutable commercial publication evidence during
-- its down path. Keep this guard function while any retained object still
-- depends on it; otherwise the disposable rollback restores 000001 fully.
do $$
declare
  helper_oid oid;
begin
  select p.oid
    into helper_oid
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'lautowork'
     and p.proname = 'jsonb_has_secret_shaped_key'
     and pg_get_function_identity_arguments(p.oid) = 'jsonb';

  if helper_oid is not null and not exists (
    select 1
      from pg_depend
     where refclassid = 'pg_proc'::regclass
       and refobjid = helper_oid
       and deptype = 'n'
  ) then
    execute 'drop function lautowork.jsonb_has_secret_shaped_key(jsonb)';
  end if;
end $$;
