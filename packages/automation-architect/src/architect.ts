import { createHash } from 'node:crypto';

import { assessSource } from './intake.js';
import { scaffoldCandidate } from './candidate.js';
import { ArchitectReportSchema, ArchitectRequestSchema } from './schemas.js';
import type { ArchitectReport, ArchitectRequest, CandidateValidationResult, CandidateValidator, SourceMapEntry, StopCondition } from './types.js';

const supportedSideEffects = new Set(['none', 'read_external', 'write_external', 'send_message', 'create_record', 'update_record', 'delete_record', 'financial_action']);

/** A deterministic fallback that records the WP-02 command is not yet supplied. */
export const unavailableWp02Validator: CandidateValidator = {
  async validate() {
    return { status: 'runner_unavailable', command: 'npm run validate:automations (WP-02)', findings: ['WP-02 command adapter was not injected; no validation receipt was forged.'] };
  },
};

function stop(code: StopCondition['code'], message: string, sourceId?: string): StopCondition {
  return { code, message, ...(sourceId ? { sourceId } : {}) };
}

function buildSourceMap(request: ArchitectRequest): SourceMapEntry[] {
  return request.approvedSources.flatMap((source) => {
    const components = source.components.length ? source.components : [{ reference: 'source-artifact', kind: 'other' as const }];
    return components.map((component) => ({
      sourceId: source.sourceId,
      sourceComponentRef: component.reference,
      ...mappingForComponent(request, component),
    }));
  });
}

/** Maps reused, replaced, and rejected source behaviours without copying untrusted implementation. */
function mappingForComponent(request: ArchitectRequest, component: ArchitectRequest['approvedSources'][number]['components'][number]): Omit<SourceMapEntry, 'sourceId' | 'sourceComponentRef'> {
  const excluded = request.exclusions.some((exclusion) => exclusion.toLowerCase().includes(component.reference.toLowerCase()));
  if (excluded) return { targetComponentRef: `excluded:${component.reference}`, action: 'discarded', reason: 'Rejected behaviour is explicitly excluded by the approved requirements.' };
  if (component.kind === 'integration') return { targetComponentRef: `workflow.json#reimplemented-${component.reference}`, action: 'reimplemented', reason: 'Replaced behaviour is reimplemented with governed n8n nodes and GSM references; source credentials are never copied.' };
  if (component.kind === 'output') return { targetComponentRef: 'contracts/output.schema.json', action: 'reimplemented', reason: 'Replaced output behaviour is expressed through the approved target output contract.' };
  return { targetComponentRef: `reference:${component.reference}`, action: 'reused_as_reference', reason: 'Reused behaviour is retained only as a documented reference; its source implementation is never copied.' };
}

function validateSourceMap(request: ArchitectRequest, sourceMap: readonly SourceMapEntry[]): StopCondition[] {
  const expected = request.approvedSources.flatMap((source) => (source.components.length ? source.components : [{ reference: 'source-artifact' }]).map((component) => `${source.sourceId}\0${component.reference}`));
  const actual = sourceMap.map((entry) => `${entry.sourceId}\0${entry.sourceComponentRef}`);
  if (expected.length !== actual.length || new Set(actual).size !== actual.length || expected.some((entry) => !actual.includes(entry))) {
    return [stop('INVALID_SOURCE_MAP', 'Every source behaviour must be mapped exactly once as reused, replaced, or rejected before a candidate can be generated.')];
  }
  if (sourceMap.some((entry) => !entry.reason.trim() || !entry.targetComponentRef.trim())) {
    return [stop('INVALID_SOURCE_MAP', 'Every source behaviour mapping requires a target reference and a reason.')];
  }
  return [];
}

function verifyRequest(request: ArchitectRequest): StopCondition[] {
  const failures: StopCondition[] = [];
  if (request.runtime.engine !== 'n8n') failures.push(stop('UNAVAILABLE_RUNTIME_CAPABILITY', 'GAP v0.1 accepts only the n8n runtime.'));
  if (request.requestProductionMutation) failures.push(stop('DIRECT_PRODUCTION_MUTATION', 'The Architect cannot mutate a production workflow, deployment pointer, credential, or certification record.'));
  if (request.requestedStatus === 'certified' || request.requestedStatus === 'deployed') failures.push(stop('SELF_CERTIFICATION_REQUEST', 'The Architect output may only be candidate; certification and deployment require independent controlled processes.'));
  if (!request.requirements.expectedOutput || !request.requirements.expectedOutput.fields.length) failures.push(stop('MISSING_EXPECTED_OUTPUT', 'A candidate requires an expected output description and at least one output field.'));
  if (request.requirements.resultMode === 'synchronous_response' && request.requirements.triggerMode !== 'webhook') failures.push(stop('UNSUPPORTED_RESULT_MODE', 'A synchronous response requires a webhook trigger in n8n.'));
  if (request.mode === 'create' && request.approvedSources.length !== 0) failures.push(stop('INVALID_MODE_SOURCE_COUNT', 'Create mode must begin from an approved brief without imported source content.'));
  if ((request.mode === 'adapt' || request.mode === 'refine') && request.approvedSources.length !== 1) failures.push(stop('INVALID_MODE_SOURCE_COUNT', `${request.mode} mode requires exactly one approved source.`));
  if (request.mode === 'compose' && request.approvedSources.length < 2) failures.push(stop('INVALID_MODE_SOURCE_COUNT', 'Compose mode requires at least two approved sources.'));
  if (request.mode === 'refine' && ![...request.evidenceReferences, ...(request.requirements.redactedEvidence ?? [])].length) failures.push(stop('REFINE_EVIDENCE_REQUIRED', 'Refine mode requires redacted evaluation, incident, telemetry, API-change, or approved-requirement evidence.'));
  for (const sideEffect of request.requirements.sideEffects) if (!supportedSideEffects.has(sideEffect)) failures.push(stop('UNSUPPORTED_SIDE_EFFECT', `Unsupported side effect declaration: ${sideEffect}.`));
  for (const capability of request.requirements.requiredCapabilities) if (!request.runtime.supportedCapabilities.includes(capability)) failures.push(stop('UNAVAILABLE_RUNTIME_CAPABILITY', `Required runtime capability is unavailable: ${capability}.`));
  if (request.approvedSources.some((source) => source.components.some((component) => component.kind === 'integration')) && !request.requirements.requiredSecretReferences.length) {
    failures.push(stop('MISSING_GSM_REFERENCE_DESIGN', 'An integration source requires an explicit GSM secret-reference design before candidate generation.'));
  }
  for (const source of request.approvedSources) {
    if (source.licence.state === 'unknown') failures.push(stop('UNKNOWN_LICENCE', 'Source licence is unknown and cannot influence a candidate.', source.sourceId));
    if (source.licence.state === 'restricted') failures.push(stop('RESTRICTED_LICENCE', 'Source licence is restricted and cannot influence a candidate.', source.sourceId));
    if (request.target.classification === 'commercial_capable' && source.licence.state !== 'cleared') failures.push(stop('UNKNOWN_LICENCE', 'Commercial-capable candidates require commercial-use licence clearance for every source.', source.sourceId));
    const intake = assessSource(source);
    if (intake.status === 'rejected') failures.push(stop('EMBEDDED_SECRET_OR_CUSTOMER_DATA', 'Quarantined source contains secret-shaped or customer-data-shaped content; values are intentionally not reported.', source.sourceId));
  }
  return failures;
}

function resumeKey(request: ArchitectRequest): string {
  return `architect:${createHash('sha256').update(JSON.stringify({ taskId: request.taskId, mode: request.mode, target: request.target, sourceDigests: request.approvedSources.map((source) => createHash('sha256').update(source.content).digest('hex')) })).digest('hex')}`;
}

function stoppedInvalidRequest(input: unknown): ArchitectReport {
  const detail = ArchitectRequestSchema.safeParse(input);
  const findings = detail.success ? ['Unexpected request parsing failure.'] : detail.error.issues.map((issue) => `${issue.path.join('.') || 'request'}: ${issue.message}`);
  return ArchitectReportSchema.parse({
    schemaVersion: '0.1', taskId: 'invalid-request', mode: 'create', status: 'stopped', target: { automationId: 'invalid-request', version: '0.0.0' }, intake: [],
    stopConditions: [stop('INVALID_REQUEST', 'The public Automation Architect request failed strict schema validation.')], sourceMap: [],
    validation: { status: 'runner_unavailable', command: 'not-run', findings }, regressionAdditions: [],
    productionMutationPerformed: false, certificationPerformed: false, deploymentPerformed: false, resumeKey: 'architect:invalid-request',
  });
}

function validateMachineValidation(result: unknown): CandidateValidationResult {
  const parsed = ArchitectReportSchema.shape.validation.safeParse(result);
  if (parsed.success) return parsed.data;
  return { status: 'failed', command: 'WP-02 adapter invalid response', findings: ['The validator returned a malformed machine report; no passing result was accepted.'] };
}

/** Prepare a candidate-only Golden Automation Package and branch/PR-ready report. */
export async function prepareCandidate(input: unknown, validator: CandidateValidator = unavailableWp02Validator): Promise<ArchitectReport> {
  const parsedRequest = ArchitectRequestSchema.safeParse(input);
  if (!parsedRequest.success) return stoppedInvalidRequest(input);
  const request: ArchitectRequest = parsedRequest.data;
  const intake = request.approvedSources.map(assessSource);
  const stopConditions = verifyRequest(request);
  const sourceMap = buildSourceMap(request);
  stopConditions.push(...validateSourceMap(request, sourceMap));
  const base = {
    schemaVersion: '0.1' as const,
    taskId: request.taskId,
    mode: request.mode,
    target: { automationId: request.target.automationId, version: request.target.version },
    intake,
    stopConditions,
    sourceMap,
    productionMutationPerformed: false as const,
    certificationPerformed: false as const,
    deploymentPerformed: false as const,
    resumeKey: resumeKey(request),
  };
  if (stopConditions.length) {
    return ArchitectReportSchema.parse({ ...base, status: 'stopped', validation: { status: 'runner_unavailable', command: 'not-run', findings: ['Candidate generation stopped before WP-02 validation.'] }, regressionAdditions: [] });
  }
  const candidate = scaffoldCandidate(request, sourceMap);
  const validation = validateMachineValidation(await validator.validate(candidate));
  return ArchitectReportSchema.parse({
    ...base,
    status: 'candidate',
    candidate,
    validation,
    regressionAdditions: request.mode === 'refine' ? ['evals/suite.json#refine-regression'] : [],
  });
}
