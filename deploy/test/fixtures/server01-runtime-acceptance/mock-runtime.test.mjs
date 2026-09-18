import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import {
  MockAdmissionStore,
  compileInputValidator,
  evaluateAcceptanceSuite,
  executeAcceptanceCase,
  loadAcceptancePackage,
  redactSensitive,
} from './mock-runtime.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '../../../..');

test('self-test executes independent behavioral checks instead of echoing fixture flags', () => {
  const result = evaluateAcceptanceSuite();
  assert.equal(result.verdict, 'passed');
  assert.equal(result.results.length, 13);
  assert.ok(result.results.every((item) => item.passed && item.independent && item.activation.n8n_dispatched === false));
  assert.equal(result.envelope.receipt.environment.kind, 'source-only-mock');
  assert.equal(result.envelope.receipt.environment.live_n8n, false);
});

test('input schema rejection happens before mock admission', () => {
  const { inputSchema, workflow } = loadAcceptancePackage();
  const validateInput = compileInputValidator(inputSchema);
  const executed = executeAcceptanceCase('rejection-invalid-input', { input: { unexpected_field: true } }, { workflow, validateInput });
  assert.equal(executed.passed, true);
  assert.equal(executed.error.category, 'invalid_state');
  assert.equal(validateInput({ case_id: 'success-output-contract' }), true);
  assert.equal(validateInput({ unexpected_field: true }), false);
});

test('duplicate idempotency replays identity and changed content conflicts', () => {
  const store = new MockAdmissionStore();
  const request = {
    request_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    org_id: '11111111-1111-4111-8111-111111111111',
    automation_id: 'server01-runtime-acceptance',
    version: '0.1.0',
    configuration_ref: 'autowork://config/server01-runtime-acceptance/0.1.0',
    idempotency_key: 'server01-runtime-acceptance-duplicate-key-01',
    input: { case_id: 'duplicate-request' },
  };
  const first = store.accept(request);
  const replay = store.accept(structuredClone(request));
  assert.equal(first.replay, false);
  assert.equal(replay.replay, true);
  assert.equal(replay.record.request.request_id, first.record.request.request_id);
  assert.throws(() => store.accept({ ...structuredClone(request), input: { case_id: 'success-output-contract' } }), /idempotency key conflicts/);
});

test('fixture mock flags cannot self-declare a pass', () => {
  const { workflow, inputSchema } = loadAcceptancePackage();
  const validateInput = compileInputValidator(inputSchema);
  const executed = executeAcceptanceCase('rejection-invalid-input', {
    input: { case_id: 'success-output-contract' },
    mock: { error_code: 'invalid_state', n8n_dispatched: false, live_n8n_activation: 'hold' },
  }, { workflow, validateInput });
  assert.equal(executed.passed, false);
});

test('receipts redact synthetic tokens', () => {
  const redacted = redactSensitive({ synthetic_token: 'ltfx.ph.2149f427b7.v1', status: 'ok' });
  assert.equal(redacted.synthetic_token, '[redacted]');
  const { workflow, inputSchema } = loadAcceptancePackage();
  const executed = executeAcceptanceCase('privacy-redaction', { synthetic_token: 'ltfx.ph.2149f427b7.v1' }, { workflow, validateInput: compileInputValidator(inputSchema) });
  assert.equal(executed.passed, true);
  assert.equal(JSON.stringify(executed.value.receipt).includes('ltfx.ph.2149f427b7.v1'), false);
});

test('mock-n8n --self-test and smoke profile target this fixture', () => {
  const selfTest = spawnSync(process.execPath, [path.join(here, 'mock-n8n.mjs'), '--self-test'], { encoding: 'utf8', cwd: repoRoot });
  assert.equal(selfTest.status, 0, selfTest.stderr || selfTest.stdout);
  const selfBody = JSON.parse(selfTest.stdout);
  assert.equal(selfBody.verdict, 'passed');
  assert.equal(selfBody.cases.length, 13);

  const smoke = spawnSync(process.execPath, [path.join(repoRoot, 'scripts/run-automation-evals.mjs'), '--profile=smoke'], { encoding: 'utf8', cwd: repoRoot });
  assert.equal(smoke.status, 0, smoke.stderr || smoke.stdout);
  const smokeBody = JSON.parse(smoke.stdout);
  assert.equal(smokeBody.verdict, 'passed');
  assert.equal(smokeBody.runtime.kind, 'source-only-mock');
  assert.equal(smokeBody.fixture, 'automations/evals/server01-runtime-acceptance');
  assert.equal(smokeBody.restoreManifest, null);
  assert.equal(fs.existsSync(smokeBody.evidence), true);
});
