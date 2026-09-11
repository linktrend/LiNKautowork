import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '../../../..');
const packageDir = path.join(repoRoot, 'automations/evals/server01-runtime-acceptance/package');

const FORBIDDEN_NODE_TYPES = new Set(['n8n-nodes-base.httpRequest', 'n8n-nodes-base.emailSend']);
const SECRET_HEADER = /authorization|api-key|x-n8n-key/i;
const BEARER = /\bBearer\s+[A-Za-z0-9._~+\/-]{12,}\b/;

/**
 * Canonical JSON used for mock receipt digests. It never includes credentials.
 * @param {unknown} value
 * @returns {string}
 */
export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

/**
 * @param {string} value
 * @returns {string}
 */
export function sha256(value) {
  return `sha256:${crypto.createHash('sha256').update(value).digest('hex')}`;
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

/**
 * Rejects credential-shaped HTTP headers. Mock traffic is unauthenticated.
 * @param {Record<string, string | string[] | undefined>} headers
 */
export function assertNoCredentialHeaders(headers = {}) {
  for (const [key, value] of Object.entries(headers)) {
    const joined = Array.isArray(value) ? value.join(' ') : String(value ?? '');
    if (SECRET_HEADER.test(key) || BEARER.test(joined) || /password|secret_value|private_key/i.test(key)) {
      throw new Error('mock n8n refuses credential-shaped headers');
    }
  }
}

/**
 * Loads the inactive technical package and suite from source.
 * @returns {{ automation: object, suite: object, workflow: object }}
 */
export function loadAcceptancePackage() {
  const automation = readJson(path.join(packageDir, 'automation.json'));
  const suite = readJson(path.join(packageDir, automation.evaluation.suite_ref));
  const workflow = readJson(path.join(packageDir, automation.runtime.workflow_ref));
  if (workflow.active !== false) throw new Error('acceptance fixture must remain inactive');
  if (workflow.nodes.some((node) => FORBIDDEN_NODE_TYPES.has(node.type) || node.credentials)) {
    throw new Error('acceptance fixture must not use credentialed or external-action nodes');
  }
  return { automation, suite, workflow, packageDir };
}

const BRANCH_EVALUATORS = new Map([
  ['success-output-contract', (fixture) => fixture.mock.branch === 'success' && fixture.mock.n8n_dispatched === false && fixture.expected_output.status === 'ok'],
  ['no-side-effects', (fixture, ctx) => fixture.expected_external_actions === 0 && ctx.workflow.active === false && ctx.workflow.nodes.every((node) => !FORBIDDEN_NODE_TYPES.has(node.type))],
  ['rejection-invalid-input', (fixture) => fixture.failure_class === 'validation' && fixture.mock.error_code === 'invalid_state'],
  ['duplicate-request', (fixture) => fixture.mock.replay === true && fixture.mock.same_execution_identity === true && fixture.mock.n8n_dispatched === false],
  ['cancel-before-dispatch', (fixture) => fixture.cancel_phase === 'before_dispatch' && fixture.mock.state === 'cancelled' && fixture.mock.n8n_dispatched === false],
  ['cancel-after-queued', (fixture) => fixture.cancel_phase === 'after_queued' && fixture.mock.second_dispatch === false],
  ['timeout-exhausted', (fixture) => fixture.mock.state === 'timed_out' && fixture.mock.n8n_dispatched === false],
  ['provider-outage', (fixture) => fixture.mock.error_code === 'unavailable' && fixture.mock.n8n_dispatched === false],
  ['callback-replay', (fixture) => fixture.mock.error_code === 'invalid_callback' && fixture.mock.receipt_mutated === false],
  ['late-callback', (fixture) => fixture.mock.returns_original_receipt === true && fixture.mock.receipt_mutated === false],
  ['kill-switch-blocked', (fixture) => fixture.mock.error_code === 'blocked' && fixture.mock.n8n_dispatched === false],
  ['restart-continuity', (fixture) => fixture.mock.replay === true && fixture.mock.second_dispatch === false],
  ['privacy-redaction', (fixture) => Object.keys(fixture).some((key) => /token|secret|password/i.test(key)) && Array.isArray(fixture.mock.redacted_fields)],
]);

/**
 * Builds the compact AW-03-compatible mock activation view.
 * @param {object} fixture
 * @param {string} caseId
 */
export function mockActivation(fixture, caseId) {
  return {
    case_id: caseId,
    request_id: '22222222-2222-4222-8222-222222222222',
    org_id: '11111111-1111-4111-8111-111111111111',
    state: fixture.mock.state ?? 'queued',
    replay: fixture.mock.replay === true,
    n8n_dispatched: false,
    live_n8n_activation: 'hold',
    error_code: fixture.mock.error_code ?? null,
    receipt_mutated: fixture.mock.receipt_mutated === true,
    does_not_prove: ['automation_run', 'consumer_outcome', 'consumer_gate', 'external_side_effect', 'e2e_readiness', 'production_readiness'],
  };
}

/**
 * Evaluates every declared suite case against mock fixtures.
 * @returns {{ verdict: 'passed' | 'failed', results: object[], receiptDigest: string }}
 */
export function evaluateAcceptanceSuite() {
  const { automation, suite, workflow } = loadAcceptancePackage();
  const results = suite.cases.map((testCase) => {
    const fixturePath = path.resolve(packageDir, 'evals', testCase.fixture_ref);
    if (!fixturePath.startsWith(`${path.resolve(packageDir, 'evals')}${path.sep}`)) {
      throw new Error(`unsafe fixture reference: ${testCase.fixture_ref}`);
    }
    const fixture = readJson(fixturePath);
    const evaluator = BRANCH_EVALUATORS.get(testCase.case_id);
    if (!evaluator) throw new Error(`undeclared mock branch: ${testCase.case_id}`);
    const passed = evaluator(fixture, { automation, workflow }) === true
      && fixture.mock.n8n_dispatched === false
      && fixture.mock.live_n8n_activation === 'hold';
    return {
      caseId: testCase.case_id,
      type: testCase.case_type,
      expected: testCase.expected.outcome,
      activation: mockActivation(fixture, testCase.case_id),
      passed,
    };
  });
  const receipt = {
    schemaVersion: 'aw-04.mock.v1',
    automationId: automation.automation_id,
    automationVersion: automation.release.version,
    packageDigest: automation.release.identity.package_digest,
    workflowDigest: automation.release.identity.workflow_digest,
    n8nVersion: suite.required_runtime.n8n_version,
    environment: { kind: 'source-only-mock', live_n8n: false, server01: 'hold' },
    observations: results,
    verdict: results.every((item) => item.passed) ? 'passed' : 'failed',
  };
  return { envelope: { receipt }, receiptDigest: sha256(canonicalJson(receipt)), results, verdict: receipt.verdict };
}
