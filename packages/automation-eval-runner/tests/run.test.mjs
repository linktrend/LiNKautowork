import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { DockerN8nRuntime, FileReceiptStore, runEvaluation, verifyReceiptEnvelope } from '../src/run.mjs';

class VerifiedRuntimeAdapter {
  constructor(overrides = {}) { this.overrides = overrides; this.stopped = false; }
  start() { return { version: '2.30.0', image: 'n8nio/n8n:2.30.0', imageId: 'sha256:official', repoDigests: ['n8nio/n8n@sha256:official'], imported: true, ...this.overrides }; }
  execute() { return { output: { status: 'ok', automation_id: 'golden-example-validation' }, status: 'success', startedAt: new Date().toISOString(), stoppedAt: new Date().toISOString(), lastNodeExecuted: 'Return Contract Output' }; }
  exportWorkflow(outputDir) { const file = path.join(outputDir, 'workflows.json'); fs.writeFileSync(file, '[]\n'); return file; }
  restoreAndExecute() { return { imported: true, executed: true, executionDigest: `sha256:${'a'.repeat(64)}` }; }
  stop() { this.stopped = true; }
}

const key = crypto.randomBytes(32);
const store = () => new FileReceiptStore(fs.mkdtempSync(path.join(os.tmpdir(), 'wp06-receipts-')));
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');

test('full evaluation checks every declared assertion and persists an authenticated receipt', () => {
  const result = runEvaluation({ runtime: new VerifiedRuntimeAdapter(), verifierKey: key, receiptStore: store(), gitSha: 'a'.repeat(40) });
  assert.equal(result.envelope.receipt.verdict, 'passed');
  assert.equal(result.envelope.receipt.observations.length, 11);
  assert.ok(result.envelope.receipt.observations.every((item) => item.assertions.length > 0 && item.assertions.every((assertion) => assertion.passed)));
  assert.equal(verifyReceiptEnvelope(result.envelope, key), true);
  assert.equal(fs.existsSync(result.evidence), true);
});

test('rejects the fake-image defect even when its label contains 2.30.0', () => {
  assert.throws(() => runEvaluation({ runtime: new VerifiedRuntimeAdapter({ version: '0.0.0' }), verifierKey: key, receiptStore: store() }), /runtime evidence/);
});

test('rejects canonical package digest drift instead of trusting a copied manifest', () => {
  const original = path.join(repoRoot, 'automations/packages/_golden-template/automation.json');
  const packageDir = fs.mkdtempSync(path.join(os.tmpdir(), 'wp06-drift-'));
  fs.cpSync(path.dirname(original), packageDir, { recursive: true });
  const fixture = path.join(packageDir, 'evals/fixtures/compatibility-v1.json');
  fs.writeFileSync(fixture, '{"invocation_contract_version":"v2"}\n');
  assert.throws(() => runEvaluation({ packageDir, runtime: new VerifiedRuntimeAdapter(), verifierKey: key, receiptStore: store() }), /package identity digest mismatch/);
});

test('receipt verifier rejects tampering and fixture declarations cannot self-assert pass', () => {
  const result = runEvaluation({ runtime: new VerifiedRuntimeAdapter(), verifierKey: key, receiptStore: store() });
  result.envelope.receipt.verdict = 'failed';
  assert.equal(verifyReceiptEnvelope(result.envelope, key), false);
  const forced = runEvaluation({ runtime: new VerifiedRuntimeAdapter(), verifierKey: key, receiptStore: store(), forcedFailures: ['manual-output-contract'] });
  assert.equal(forced.envelope.receipt.verdict, 'failed');
});

test('Docker cleanup accepts an already-removed disposable volume', () => {
  const calls = [];
  const runtime = new DockerN8nRuntime({ commandRunner: (_command, args) => {
    calls.push(args);
    throw new Error(`docker ${args.join(' ')} failed: Error response from daemon: get ${args.at(-1)}: no such volume`);
  } });

  runtime.stop();

  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].slice(0, 2), ['volume', 'rm']);
});

test('Docker cleanup settles repeated stop calls exactly once', () => {
  const calls = [];
  const runtime = new DockerN8nRuntime({ commandRunner: (_command, args) => {
    calls.push(args);
    return args.at(-1);
  } });

  runtime.stop();
  runtime.stop();

  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].slice(0, 2), ['volume', 'rm']);
});

test('Docker runtime labels only its primary and restore disposable volumes', () => {
  const calls = [];
  const rawExecution = JSON.stringify({ data: { resultData: { lastNodeExecuted: 'Return Contract Output', runData: { 'Return Contract Output': [{ data: { main: [[{ json: { status: 'ok' } }]] } }] } } }, status: 'success', finished: true, startedAt: '2026-01-01T00:00:00.000Z', stoppedAt: '2026-01-01T00:00:01.000Z' }, null, 2);
  const runtime = new DockerN8nRuntime({ commandRunner: (_command, args) => {
    calls.push(args);
    if (args[0] === 'image') return 'sha256:official|["n8nio/n8n@sha256:official"]';
    if (args.includes('--version')) return '2.30.0';
    if (args.includes('--rawOutput')) return rawExecution;
    return '';
  } });
  const packageDir = path.join(repoRoot, 'automations/packages/_golden-template');
  runtime.start(packageDir);
  assert.deepEqual(calls[0], ['pull', 'n8nio/n8n:2.30.0']);
  assert.deepEqual(calls[1].slice(0, 2), ['image', 'inspect']);
  const output = fs.mkdtempSync(path.join(os.tmpdir(), 'wp06-label-'));
  fs.writeFileSync(path.join(output, 'workflows.json'), '[]');
  runtime.restoreAndExecute(path.join(output, 'workflows.json'), 'golden-example-validation-eval');
  runtime.stop();
  const creates = calls.filter((args) => args[0] === 'volume' && args[1] === 'create');
  assert.equal(creates.length, 2);
  assert.ok(creates.every((args) => args.includes('--label') && args.includes('com.linktrend.linkautowork.disposable-eval=true')));
  assert.ok(calls.every((args) => !args.includes('system') && !args.includes('prune')));
});

test('Docker cleanup preserves unexpected errors and evaluation invokes it once', () => {
  const cleanupError = new Error('docker volume rm eval failed: daemon permission denied');
  const runtime = new VerifiedRuntimeAdapter();
  let stopCalls = 0;
  runtime.stop = () => { stopCalls += 1; throw cleanupError; };

  assert.throws(() => runEvaluation({ runtime, verifierKey: key, receiptStore: store() }), cleanupError);
  assert.equal(stopCalls, 1);
});
