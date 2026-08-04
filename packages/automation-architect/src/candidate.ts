import { createHash } from 'node:crypto';

import type { ArchitectRequest, CandidatePackage, SourceMapEntry } from './types.js';

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function digest(value: string): string {
  return `sha256:${createHash('sha256').update(value).digest('hex')}`;
}

function json(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function safeSourceKind(kind: string): string {
  const kinds: Record<string, string> = {
    n8n_export: 'n8n_template',
    make_blueprint: 'make_blueprint',
    zapier_export: 'zapier_export',
    github_repository: 'github_repository',
    open_source_project: 'open_source_project',
    documented_flow: 'documentation',
    manual_specification: 'manual_specification',
  };
  return kinds[kind] ?? 'documentation';
}

function candidateValue(field: string, automationId: string, mode: ArchitectRequest['mode']): string {
  if (field === 'status') return 'candidate_not_deployed';
  if (field === 'automation_id') return automationId;
  if (field === 'architect_mode') return mode;
  return `candidate_${field}`;
}

function modePlan(request: ArchitectRequest, sourceMap: readonly SourceMapEntry[]): { nodeName: string; note: string; evalCase: string } {
  const mapped = sourceMap.filter((entry) => entry.action !== 'discarded').length;
  if (request.mode === 'adapt') return { nodeName: 'Adapt Approved Source Behaviours', note: `Adapt one approved source through ${mapped} reviewed behaviour mappings.`, evalCase: 'adapt-source-mapping' };
  if (request.mode === 'compose') return { nodeName: 'Compose Approved Source Behaviours', note: `Compose ${request.approvedSources.length} approved sources through ${mapped} reviewed behaviour mappings.`, evalCase: 'compose-source-compatibility' };
  if (request.mode === 'refine') return { nodeName: 'Apply Evidence Driven Refinement', note: `Refine from ${request.evidenceReferences.length + (request.requirements.redactedEvidence?.length ?? 0)} redacted evidence references.`, evalCase: 'refine-regression' };
  return { nodeName: 'Apply Approved Creation Brief', note: 'Create from the approved target brief without imported source implementation.', evalCase: 'create-approved-brief' };
}

/** Compute the WP-01 deterministic digest of governed JSON package files. */
export function calculatePackageDigest(files: Readonly<Record<string, string>>): string {
  const governed = Object.keys(files).filter((path) =>
    path === 'automation.json'
    || path === 'workflow.json'
    || path.startsWith('contracts/') && path.endsWith('.json')
    || path.startsWith('evals/') && path.endsWith('.json')
    || path === 'operations/monitoring.json'
    || path === 'operations/maintenance.json'
    || path === 'operations/deployment.json'
    || path === 'provenance/sources.json',
  ).filter((path) =>
    path !== 'evals/certification-receipt.json'
    && !path.startsWith('evals/evidence/')
    && !path.startsWith('evals/receipts/'),
  ).sort();

  const entries = governed.map((path) => {
    let parsed = JSON.parse(files[path]) as unknown;
    if (path === 'automation.json') {
      const identity = (((parsed as Record<string, unknown>).release as Record<string, unknown>).identity as Record<string, unknown>);
      identity.package_digest = 'sha256:__excluded__';
    }
    return `${path}\0${createHash('sha256').update(`${canonicalJson(parsed)}\n`).digest('hex')}\0`;
  }).join('');
  return digest(entries);
}

/** Scaffold a safe, inactive Golden Automation Package. Source workflows are never copied into it. */
export function scaffoldCandidate(request: ArchitectRequest, sourceMap: readonly SourceMapEntry[]): CandidatePackage {
  const automationId = request.target.automationId;
  const root = `automations/catalog/${automationId}/${request.target.version}`;
  const externalSideEffects = request.requirements.sideEffects.filter((sideEffect) => sideEffect !== 'none');
  const commercial = request.target.classification === 'commercial_capable';
  const sourceRecords = request.approvedSources.map((source) => ({
    source_id: source.sourceId,
    kind: safeSourceKind(source.kind),
    locator: source.locator,
    revision: source.revision,
    content_digest: `sha256:${createHash('sha256').update(source.content).digest('hex')}`,
    license: source.licence.identifier,
    commercial_use: commercial ? 'allowed' : 'not_applicable',
    adaptation_status: sourceMap.some((entry) => entry.sourceId === source.sourceId && entry.action === 'reimplemented') ? 'reimplemented' : sourceMap.some((entry) => entry.sourceId === source.sourceId && entry.action === 'reused_as_reference') ? 'reference_only' : 'not_used',
  }));
  if (!sourceRecords.length) {
    sourceRecords.push({
      source_id: 'approved-create-brief',
      kind: 'manual_specification',
      locator: `https://linktrend.invalid/automation-architect/tasks/${request.taskId}`,
      revision: request.taskId,
      content_digest: digest(json({ target: request.target, requirements: request.requirements })),
      license: 'LicenseRef-LiNKtrend-Internal',
      commercial_use: 'not_applicable',
      adaptation_status: 'reference_only',
    });
  }
  const candidateSourceMap = sourceMap.length ? sourceMap : [{
    sourceId: 'approved-create-brief', sourceComponentRef: 'approved-brief', targetComponentRef: 'contracts/output.schema.json', action: 'reimplemented' as const,
    reason: 'The approved creation brief is reimplemented as the target output contract without importing source implementation.',
  }];
  const plan = modePlan(request, sourceMap);
  const expectedFields = [...new Set(request.requirements.expectedOutput?.fields ?? [])];
  const outputProperties = Object.fromEntries(expectedFields.map((field) => [field, { type: 'string', description: `Candidate-only ${field} output.` }]));
  const outputAssignments = expectedFields.map((field, index) => ({ id: `00000000-0000-4000-8000-${String(index + 2).padStart(12, '0')}`, name: field, value: candidateValue(field, automationId, request.mode), type: 'string' }));
  const trigger = request.requirements.triggerMode === 'webhook'
    ? { parameters: { httpMethod: 'POST', path: `${automationId}-candidate`, responseMode: request.requirements.resultMode === 'synchronous_response' ? 'responseNode' : 'onReceived', options: {} }, id: '00000000-0000-4000-8000-000000000001', name: 'Candidate Webhook Trigger', type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [260, 300] }
    : request.requirements.triggerMode === 'schedule'
      ? { parameters: { rule: { interval: [{ field: 'hours', hoursInterval: 24 }] } }, id: '00000000-0000-4000-8000-000000000001', name: 'Candidate Schedule Trigger', type: 'n8n-nodes-base.scheduleTrigger', typeVersion: 1.2, position: [260, 300] }
      : request.requirements.triggerMode === 'event'
        ? { parameters: {}, id: '00000000-0000-4000-8000-000000000001', name: 'Candidate Event Trigger', type: 'n8n-nodes-base.natsTrigger', typeVersion: 1, position: [260, 300] }
        : { parameters: {}, id: '00000000-0000-4000-8000-000000000001', name: 'Manual Candidate Trigger', type: 'n8n-nodes-base.manualTrigger', typeVersion: 1, position: [260, 300] };
  const responseNode = request.requirements.resultMode === 'synchronous_response'
    ? [{ parameters: { respondWith: 'json', responseBody: '={{ $json }}', options: {} }, id: '00000000-0000-4000-8000-000000000104', name: 'Candidate Synchronous Response', type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1.4, position: [980, 300] }]
    : [];
  const workflow = {
    name: `${request.target.displayName} Candidate`,
    nodes: [
      trigger,
      { parameters: { assignments: { assignments: [{ id: '00000000-0000-4000-8000-000000000100', name: 'architect_mode', value: request.mode, type: 'string' }, { id: '00000000-0000-4000-8000-000000000101', name: 'mapping_count', value: String(sourceMap.length), type: 'string' }] }, options: {} }, id: '00000000-0000-4000-8000-000000000102', name: plan.nodeName, type: 'n8n-nodes-base.set', typeVersion: 3.4, position: [500, 300] },
      { parameters: { assignments: { assignments: outputAssignments }, options: {} }, id: '00000000-0000-4000-8000-000000000103', name: 'Candidate Contract Output', type: 'n8n-nodes-base.set', typeVersion: 3.4, position: [740, 300] },
      ...responseNode,
    ],
    connections: { [trigger.name]: { main: [[{ node: plan.nodeName, type: 'main', index: 0 }]] }, [plan.nodeName]: { main: [[{ node: 'Candidate Contract Output', type: 'main', index: 0 }]] }, ...(responseNode.length ? { 'Candidate Contract Output': { main: [[{ node: 'Candidate Synchronous Response', type: 'main', index: 0 }]] } } : {}) },
    pinData: {}, settings: { executionOrder: 'v1' }, active: false, versionId: '00000000-0000-4000-8000-000000000005', tags: [],
  };
  const workflowDigest = digest(json(workflow));
  const files: Record<string, string> = {
    'workflow.json': json(workflow),
    'contracts/input.schema.json': json({ $schema: 'https://json-schema.org/draft/2020-12/schema', title: `${automationId} input`, type: 'object', additionalProperties: false, properties: {} }),
    'contracts/output.schema.json': json({ $schema: 'https://json-schema.org/draft/2020-12/schema', title: `${automationId} output`, description: `${plan.note} Output fields are taken only from approved requirements.`, type: 'object', additionalProperties: false, required: expectedFields, properties: outputProperties }),
    'contracts/configuration.schema.json': json({ $schema: 'https://json-schema.org/draft/2020-12/schema', title: `${automationId} configuration`, type: 'object', additionalProperties: false, description: 'Non-secret configuration only. Instance secrets are supplied through GSM bindings.' }),
    'evals/fixtures/happy-path.json': json({ kind: 'redacted_fixture', architect_mode: request.mode, expected_output_fields: expectedFields, behaviour_mappings: candidateSourceMap.map((entry) => ({ source_id: entry.sourceId, source_component_ref: entry.sourceComponentRef, target_component_ref: entry.targetComponentRef, disposition: entry.action === 'reused_as_reference' ? 'reused' : entry.action === 'reimplemented' ? 'replaced' : 'rejected' })) }),
    'evals/suite.json': json({ schema_version: '0.1', suite_id: `${automationId}-candidate-suite`, automation_id: automationId, automation_version: request.target.version, required_runtime: { engine: 'n8n', n8n_version: request.runtime.n8nVersion }, pass_threshold: 1, cases: [
      { case_id: 'candidate-happy-path', case_type: 'happy_path', fixture_ref: 'fixtures/happy-path.json', expected: { outcome: 'success', assertions: [`Candidate ${request.mode} output contains approved fields: ${expectedFields.join(', ')}.`, plan.note], receipt_fields: ['release_id', 'execution_id', 'status'] }, side_effect_mode: 'prohibited' },
      { case_id: plan.evalCase, case_type: request.mode === 'refine' ? 'regression' : request.mode === 'compose' ? 'compatibility' : 'validation', fixture_ref: 'fixtures/happy-path.json', expected: { outcome: request.mode === 'refine' ? 'controlled_failure' : 'success', assertions: [plan.note, 'Reviewed source behaviour mappings are retained without copying source implementation.'], receipt_fields: request.mode === 'refine' ? ['release_id', 'execution_id', 'status', 'failure_class'] : ['release_id', 'execution_id', 'status'] }, side_effect_mode: 'prohibited' },
    ], evidence_policy: { retain: ['case_result', 'assertion_result', 'release_hash', 'runtime_version', 'receipt_hash'], redact: ['Do not retain source, customer, or secret values in evaluation evidence.'], independent_verdict_required: true } }),
    'operations/monitoring.json': json({ schema_version: '0.1', profile_id: `${automationId}-candidate-monitoring`, slo: { success_rate_target: 0.99, max_latency_ms: 30000, missed_schedule_tolerance: 0 }, signals: ['execution_success', 'execution_failure'], alerts: [{ signal: 'execution_failure', severity: 'warning', condition: 'Any candidate evaluation fails.', route_key: 'linkautowork.operator-review' }], health_checks: [{ check_id: 'candidate-run-completion', kind: 'run_completion', interval_seconds: 3600 }] }),
    'operations/maintenance.json': json({ schema_version: '0.1', policy_id: `${automationId}-candidate-maintenance`, automatic_actions: ['none'], escalation: { create_maintenance_issue: true, severity_threshold: 'warning' }, candidate_change_policy: { workflow_logic_change: 'new_release_candidate', independent_eval_required: true, production_in_place_change_allowed: false } }),
    'operations/deployment.json': json({ schema_version: '0.1', profile_id: `${automationId}-candidate-deployment`, supported_environments: ['development'], promotion: { canary_required: true, independent_approval_required: true }, instance_isolation: { mode: 'logical_shared_n8n', separate_workflow_copy: true, separate_credential_scope: true }, configuration: { configuration_reference_required: true, secret_values_permitted: false }, rollback: { previous_certified_release_required: true, operator_runbook_required: true } }),
    'operations/runbook.md': `# ${request.target.displayName} candidate\n\nThis inactive candidate is not certified, deployed, or bound to an instance. Follow independent evaluation and controlled promotion before use.\n`,
    'provenance/sources.json': json({ schema_version: '0.1', automation_id: automationId, automation_version: request.target.version, required_runtime: { engine: 'n8n', n8n_version: request.runtime.n8nVersion }, sources: sourceRecords, source_to_target_map: candidateSourceMap.map((entry) => ({ source_id: entry.sourceId, source_content_digest: sourceRecords.find((source) => source.source_id === entry.sourceId)?.content_digest, source_component_ref: entry.sourceComponentRef, target_component_ref: entry.targetComponentRef, action: entry.action === 'reused_as_reference' ? 'reference_only' : entry.action === 'reimplemented' ? 'reimplemented' : 'not_used', reason: entry.reason })), review: { status: commercial ? 'cleared' : 'not_applicable', reviewer_role: 'Automation Architect candidate intake', conclusion: 'Candidate provenance and reused, replaced, and rejected behaviour mappings are recorded for independent licence and evaluation review.' } }),
    'README.md': `# ${request.target.displayName}\n\nCandidate-only Golden Automation Package. It is not certified, deployed, or eligible for a client or internal instance.\n`,
    'CHANGELOG.md': `# Changelog\n\n## ${request.target.version}\n\n- Candidate prepared by task ${request.taskId}.\n`,
  };
  const manifest = {
    schema_version: '0.1', automation_id: automationId, display_name: request.target.displayName, summary: request.requirements.summary,
    ownership: { owner_kind: request.target.ownerKind, owning_program: request.target.owningProgram, classification: request.target.classification, binding_operations: request.target.bindingOperations },
    release: { version: request.target.version, channel: 'development', lifecycle: 'draft', identity: { package_digest: 'sha256:__excluded__', workflow_digest: workflowDigest, source_git_sha: request.target.sourceGitSha, n8n_version: request.runtime.n8nVersion } },
    runtime: { engine: 'n8n', workflow_ref: 'workflow.json', trigger_mode: request.requirements.triggerMode, result_mode: request.requirements.resultMode, approved_node_policy: 'n8n-core-only-v0.1' },
    contracts: { input_schema_ref: 'contracts/input.schema.json', output_schema_ref: 'contracts/output.schema.json', configuration_schema_ref: 'contracts/configuration.schema.json', invocation_contract_version: 'v1' },
    secrets: request.requirements.requiredSecretReferences.map((secret) => ({ secret_ref: secret.secretRef, purpose: secret.purpose, required: true })),
    execution_policy: { criticality: 'standard', side_effects: externalSideEffects.length ? externalSideEffects : ['none'], approval: { mode: externalSideEffects.length ? 'operator_required' : 'none', evidence_required: true }, retry: { max_attempts: 0, backoff: 'none', max_delay_seconds: 0 }, idempotency: { required: false, key_location: 'not_applicable' }, kill_switch_scope: 'instance' },
    telemetry: { classification: 'internal', redaction_rules: ['Do not retain source, customer, credential, or secret values.'], retention_days: 30, required_fields: ['org_id', 'instance_id', 'release_id', 'execution_id', 'status', 'latency_ms', 'retry_count', 'failure_class'] },
    evaluation: { suite_ref: 'evals/suite.json', required_for_certification: true },
    operations: { monitoring_ref: 'operations/monitoring.json', maintenance_ref: 'operations/maintenance.json', deployment_ref: 'operations/deployment.json', runbook_ref: 'operations/runbook.md' },
    provenance: { sources_ref: 'provenance/sources.json', commercial_use_clearance: commercial ? 'cleared' : 'not_applicable' },
    source_authority: { kind: 'golden_automation_package', cutover_state: 'package_authoritative' },
  };
  files['automation.json'] = json(manifest);
  const packageDigest = calculatePackageDigest(files);
  const mutable = JSON.parse(files['automation.json']) as { release: { identity: { package_digest: string } } };
  mutable.release.identity.package_digest = packageDigest;
  files['automation.json'] = json(mutable);
  return { root, files, packageDigest, workflowDigest };
}
