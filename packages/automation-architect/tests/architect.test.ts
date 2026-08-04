import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  ArchitectReportSchema,
  ArchitectRequestSchema,
  canTransitionIntake,
  createWp02Validator,
  hashIntakeArtifact,
  prepareCandidate,
  scanIntakeContent,
  type ArchitectRequest,
} from '../src/index.js';

const sourceGitSha = 'a'.repeat(40);
const repoRoot = fileURLToPath(new URL('../../../', import.meta.url));

function request(overrides: Partial<ArchitectRequest> = {}): ArchitectRequest {
  return {
    taskId: 'architect-test-task',
    mode: 'create',
    target: {
      automationId: 'candidate-invoice-reminder',
      version: '0.1.0',
      displayName: 'Candidate Invoice Reminder',
      owningProgram: 'linkautowork',
      classification: 'internal_only',
      ownerKind: 'shared_internal',
      bindingOperations: ['linkautowork.candidate-test'],
      sourceGitSha,
    },
    approvedSources: [],
    requirements: {
      summary: 'Prepare a safe inactive candidate with a deterministic contract output for independent evaluation.',
      expectedOutput: { description: 'A redacted candidate output.', fields: ['status', 'automation_id'] },
      triggerMode: 'manual',
      resultMode: 'none',
      sideEffects: ['none'],
      requiredCapabilities: [],
      requiredSecretReferences: [],
    },
    exclusions: ['No production mutation.'],
    runtime: { engine: 'n8n', n8nVersion: '2.30.0', supportedCapabilities: [] },
    evidenceReferences: [],
    ...overrides,
  };
}

async function fixture(name: string): Promise<string> {
  return readFile(resolve(repoRoot, 'automations/fixtures/intake', name), 'utf8');
}

function source(sourceId: string, kind: ArchitectRequest['approvedSources'][number]['kind'], content: string, licence: 'cleared' | 'not_applicable' | 'unknown' | 'restricted' = 'cleared'): ArchitectRequest['approvedSources'][number] {
  return {
    sourceId,
    kind,
    locator: `https://example.invalid/${sourceId}`,
    revision: 'v1',
    content,
    licence: { identifier: licence === 'cleared' ? 'MIT' : 'LicenseRef-LiNKtrend-Internal', state: licence },
    components: [
      { reference: 'trigger', kind: 'trigger' },
      { reference: 'result', kind: 'output' },
    ],
  };
}

describe('Automation Architect candidate preparation', () => {
  it('creates a deterministic candidate from a valid approved brief', async () => {
    const result = await prepareCandidate(request());

    expect(result.status).toBe('candidate');
    expect(result.candidate?.root).toBe('automations/catalog/candidate-invoice-reminder/0.1.0');
    expect(result.candidate?.files['workflow.json']).not.toContain('credential');
    expect(result.candidate?.files['automation.json']).toContain('"lifecycle": "draft"');
    expect(result.validation.status).toBe('runner_unavailable');
    expect(result.productionMutationPerformed).toBe(false);
    expect(ArchitectReportSchema.parse(result).status).toBe('candidate');
  });

  it('adapts a sanitized n8n source without copying its workflow content', async () => {
    const result = await prepareCandidate(request({
      mode: 'adapt',
      approvedSources: [source('sanitized-n8n-source', 'n8n_export', await fixture('sanitized-n8n-source.json'))],
    }));

    expect(result.status).toBe('candidate');
    expect(result.intake[0].detectedNodeTypes).toEqual(['n8n-nodes-base.manualTrigger', 'n8n-nodes-base.set']);
    expect(result.sourceMap).toHaveLength(2);
    expect(result.candidate?.files['workflow.json']).toContain('Manual Candidate Trigger');
    expect(result.candidate?.files['workflow.json']).not.toContain('Sanitized n8n source fixture');
  });

  it('adapts a Make descriptor into a mapped candidate', async () => {
    const result = await prepareCandidate(request({
      mode: 'adapt',
      approvedSources: [source('make-source-descriptor', 'make_blueprint', await fixture('make-source-descriptor.json'))],
    }));

    expect(result.status).toBe('candidate');
    expect(result.sourceMap.map((entry) => entry.sourceId)).toEqual(['make-source-descriptor', 'make-source-descriptor']);
    expect(result.candidate?.files['provenance/sources.json']).toContain('make_blueprint');
  });

  it('composes compatible sources while preserving individual provenance', async () => {
    const n8n = await fixture('sanitized-n8n-source.json');
    const make = await fixture('make-source-descriptor.json');
    const result = await prepareCandidate(request({
      mode: 'compose',
      approvedSources: [source('source-one', 'n8n_export', n8n), source('source-two', 'make_blueprint', make)],
    }));

    expect(result.status).toBe('candidate');
    const provenance = result.candidate?.files['provenance/sources.json'] ?? '';
    expect(provenance).toContain('source-one');
    expect(provenance).toContain('source-two');
    expect(result.sourceMap.every((entry) => entry.sourceId === 'source-one' || entry.sourceId === 'source-two')).toBe(true);
  });

  it('rejects unknown commercial licence before candidate generation', async () => {
    const result = await prepareCandidate(request({
      mode: 'adapt',
      target: { ...request().target, classification: 'commercial_capable', ownerKind: 'commercial_product' },
      approvedSources: [source('unknown-license-source', 'n8n_export', await fixture('sanitized-n8n-source.json'), 'unknown')],
    }));

    expect(result.status).toBe('stopped');
    expect(result.stopConditions.map((item) => item.code)).toContain('UNKNOWN_LICENCE');
    expect(result.candidate).toBeUndefined();
  });

  it('rejects embedded credential or customer-data-shaped source content without leaking it', async () => {
    const unsafe = await fixture('source-with-embedded-secret.json');
    const result = await prepareCandidate(request({
      mode: 'adapt',
      approvedSources: [source('unsafe-source', 'n8n_export', unsafe)],
    }));

    expect(scanIntakeContent(unsafe).secretFindingCount).toBeGreaterThan(0);
    expect(result.status).toBe('stopped');
    expect(result.stopConditions.map((item) => item.code)).toContain('EMBEDDED_SECRET_OR_CUSTOMER_DATA');
    expect(JSON.stringify(result)).not.toContain('redacted-test-value');
  });

  it('refines from redacted failure evidence and adds a regression evaluation case', async () => {
    const result = await prepareCandidate(request({
      mode: 'refine',
      approvedSources: [source('existing-release', 'n8n_export', await fixture('sanitized-n8n-source.json'))],
      evidenceReferences: [{ reference: 'incidents/redacted-123', kind: 'incident', digest: `sha256:${'b'.repeat(64)}` }],
    }));

    expect(result.status).toBe('candidate');
    expect(result.regressionAdditions).toEqual(['evals/suite.json#refine-regression']);
    expect(result.candidate?.files['evals/suite.json']).toContain('refine-regression');
  });

  it('rejects direct production mutation and self-certification requests', async () => {
    const result = await prepareCandidate(request({ requestProductionMutation: true, requestedStatus: 'certified' }));

    expect(result.status).toBe('stopped');
    expect(result.stopConditions.map((item) => item.code)).toEqual(expect.arrayContaining(['DIRECT_PRODUCTION_MUTATION', 'SELF_CERTIFICATION_REQUEST']));
    expect(result.certificationPerformed).toBe(false);
    expect(result.deploymentPerformed).toBe(false);
  });

  it('resumes safely by producing the same deterministic candidate and injected WP-02 validation result', async () => {
    const validator = createWp02Validator({
      async run(root, files) {
        return { status: files['automation.json'] ? 'passed' : 'failed', command: `wp02 --candidate ${root}`, findings: [], receiptRef: 'evidence/wp02-synthetic' };
      },
    });
    const first = await prepareCandidate(request(), validator);
    const resumed = await prepareCandidate(request({ resumeFromTaskId: 'architect-test-task' }), validator);

    expect(first.resumeKey).toBe(resumed.resumeKey);
    expect(first.candidate?.packageDigest).toBe(resumed.candidate?.packageDigest);
    expect(resumed.validation).toMatchObject({ status: 'passed', receiptRef: 'evidence/wp02-synthetic' });
  });

  it('validates the machine-readable request shape and hashes intake artefacts', async () => {
    expect(ArchitectRequestSchema.parse(request()).mode).toBe('create');
    await expect(hashIntakeArtifact(resolve(repoRoot, 'automations/fixtures/intake/sanitized-n8n-source.json'))).resolves.toMatchObject({ digest: expect.stringMatching(/^sha256:/), isArchive: false });
    expect(canTransitionIntake('submitted', 'quarantined')).toBe(true);
    expect(canTransitionIntake('archived', 'assessed')).toBe(false);
  });

  it('stops an integration adaptation until a GSM-reference design is supplied', async () => {
    const result = await prepareCandidate(request({
      mode: 'adapt',
      approvedSources: [{ ...source('integration-source', 'n8n_export', await fixture('sanitized-n8n-source.json')), components: [{ reference: 'remote-api', kind: 'integration' }] }],
    }));

    expect(result.status).toBe('stopped');
    expect(result.stopConditions.map((item) => item.code)).toContain('MISSING_GSM_REFERENCE_DESIGN');
  });

  it('rejects malformed JavaScript runtime input before it can become a candidate report', async () => {
    const malformed = { ...request(), target: { ...request().target, automationId: 'INVALID ID' }, unexpectedAuthority: 'deploy-now' };
    const result = await prepareCandidate(malformed);

    expect(result.status).toBe('stopped');
    expect(result.stopConditions.map((item) => item.code)).toEqual(['INVALID_REQUEST']);
    expect(result.candidate).toBeUndefined();
    expect(ArchitectReportSchema.parse(result).status).toBe('stopped');
  });

  it('makes each mode visible in the inactive workflow, contract fixture, and evaluation suite', async () => {
    const n8n = await fixture('sanitized-n8n-source.json');
    const make = await fixture('make-source-descriptor.json');
    const scenarios: Array<[ArchitectRequest['mode'], Partial<ArchitectRequest>, string]> = [
      ['create', {}, 'Apply Approved Creation Brief'],
      ['adapt', { approvedSources: [source('adapt-source', 'n8n_export', n8n)] }, 'Adapt Approved Source Behaviours'],
      ['compose', { approvedSources: [source('compose-one', 'n8n_export', n8n), source('compose-two', 'make_blueprint', make)] }, 'Compose Approved Source Behaviours'],
      ['refine', { approvedSources: [source('refine-source', 'n8n_export', n8n)], evidenceReferences: [{ reference: 'evaluations/redacted-1', kind: 'evaluation', digest: `sha256:${'d'.repeat(64)}` }] }, 'Apply Evidence Driven Refinement'],
    ];
    for (const [mode, overrides, nodeName] of scenarios) {
      const result = await prepareCandidate(request({ mode, ...overrides }));
      expect(result.status).toBe('candidate');
      expect(result.candidate?.files['workflow.json']).toContain(nodeName);
      expect(result.candidate?.files['evals/fixtures/happy-path.json']).toContain(`"architect_mode": "${mode}"`);
      expect(result.candidate?.files['evals/suite.json']).toContain(mode === 'create' ? 'create-approved-brief' : mode === 'adapt' ? 'adapt-source-mapping' : mode === 'compose' ? 'compose-source-compatibility' : 'refine-regression');
    }
  });

  it('retains replaced and rejected behaviour mapping evidence in governed candidate inputs', async () => {
    const result = await prepareCandidate(request({
      mode: 'adapt', exclusions: ['legacy-step must not be used'],
      approvedSources: [{ ...source('mapped-source', 'n8n_export', await fixture('sanitized-n8n-source.json')), components: [{ reference: 'legacy-step', kind: 'step' }, { reference: 'remote-api', kind: 'integration' }] }],
      requirements: { ...request().requirements, requiredSecretReferences: [{ secretRef: 'LINKTREND_TEST_API_REFERENCE', purpose: 'Governed replacement for the source integration.' }] },
    }));
    expect(result.status).toBe('candidate');
    expect(result.sourceMap.map((entry) => entry.action)).toEqual(['discarded', 'reimplemented']);
    const provenance = result.candidate?.files['provenance/sources.json'] ?? '';
    expect(provenance).toContain('"not_used"');
    expect(provenance).toContain('"reimplemented"');
    expect(result.candidate?.files['evals/fixtures/happy-path.json']).toContain('"rejected"');
    expect(result.candidate?.files['evals/fixtures/happy-path.json']).toContain('"replaced"');
  });

  it('generates the required webhook and response pair for a synchronous response', async () => {
    const result = await prepareCandidate(request({ requirements: { ...request().requirements, triggerMode: 'webhook', resultMode: 'synchronous_response' } }));
    expect(result.status).toBe('candidate');
    expect(result.candidate?.files['workflow.json']).toContain('n8n-nodes-base.webhook');
    expect(result.candidate?.files['workflow.json']).toContain('n8n-nodes-base.respondToWebhook');
  });
});
