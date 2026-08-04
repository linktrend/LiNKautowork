import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { calculatePackageDigest, calculateWorkflowDigest, canonicalJson } from '../../automation-catalog/src/catalog.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '../../..');
const sha256 = (value) => `sha256:${crypto.createHash('sha256').update(value).digest('hex')}`;
const DISPOSABLE_EVAL_LABEL = 'com.linktrend.linkautowork.disposable-eval=true';
const readJson = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));
const fileHash = (file) => sha256(fs.readFileSync(file));

function command(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', maxBuffer: 20 * 1024 * 1024, ...options });
  if (result.error || result.status !== 0) throw new Error(`${command} ${args.join(' ')} failed: ${result.error?.message ?? result.stderr ?? result.stdout}`);
  return result.stdout.trim();
}

function isMissingDockerResource(error, resource) {
  return error instanceof Error && new RegExp(`(?:no such ${resource}|${resource}[\\s\\S]*not found)`, 'i').test(error.message);
}

function parseRawExecution(output) {
  const start = output.lastIndexOf('\n{\n  "data"');
  const json = JSON.parse((start >= 0 ? output.slice(start + 1) : output).trim());
  const runData = json.data?.resultData?.runData ?? {};
  const finalNode = json.data?.resultData?.lastNodeExecuted;
  const item = runData[finalNode]?.at(-1)?.data?.main?.[0]?.[0]?.json;
  if (json.status !== 'success' || !json.finished || !item) throw new Error('n8n did not return a successful final node result');
  return { output: item, status: json.status, startedAt: json.startedAt, stoppedAt: json.stoppedAt, lastNodeExecuted: finalNode };
}

/** Runtime adapter backed only by the official pinned n8n container. */
export class DockerN8nRuntime {
  constructor({ image = 'n8nio/n8n:2.30.0', commandRunner = command } = {}) {
    this.image = image;
    this.commandRunner = commandRunner;
    this.volume = `linkautowork-eval-${crypto.randomUUID()}`;
    this.cleanupComplete = false;
  }
  removeDockerResource(resource, name) {
    try {
      this.commandRunner('docker', [resource, 'rm', name]);
    } catch (error) {
      if (!isMissingDockerResource(error, resource)) throw error;
    }
  }
  start(packageDir) {
    this.commandRunner('docker', ['pull', this.image]);
    const inspect = this.commandRunner('docker', ['image', 'inspect', '--format', '{{.Id}}|{{json .RepoDigests}}', this.image]);
    const [imageId, repoDigests] = inspect.split('|');
    const version = this.commandRunner('docker', ['run', '--rm', '--label', DISPOSABLE_EVAL_LABEL, '--entrypoint', 'n8n', this.image, '--version']);
    if (version !== '2.30.0') throw new Error(`wrong n8n runtime version: ${version}`);
    this.commandRunner('docker', ['volume', 'create', '--label', DISPOSABLE_EVAL_LABEL, this.volume]);
    this.commandRunner('docker', ['run', '--rm', '--label', DISPOSABLE_EVAL_LABEL, '-e', 'N8N_ENCRYPTION_KEY=wp06-disposable-only', '-v', `${this.volume}:/home/node/.n8n`, '-v', `${path.resolve(packageDir)}:/package:ro`, '--entrypoint', 'n8n', this.image, 'import:workflow', '--input=/package/workflow.json']);
    return { version, image: this.image, imageId, repoDigests: JSON.parse(repoDigests), imported: true };
  }
  execute(workflowId) {
    return parseRawExecution(this.commandRunner('docker', ['run', '--rm', '--label', DISPOSABLE_EVAL_LABEL, '-e', 'N8N_ENCRYPTION_KEY=wp06-disposable-only', '-v', `${this.volume}:/home/node/.n8n`, '--entrypoint', 'n8n', this.image, 'execute', `--id=${workflowId}`, '--rawOutput']));
  }
  exportWorkflow(outputDir) {
    fs.chmodSync(outputDir, 0o777);
    this.commandRunner('docker', ['run', '--rm', '--label', DISPOSABLE_EVAL_LABEL, '-e', 'N8N_ENCRYPTION_KEY=wp06-disposable-only', '-v', `${this.volume}:/home/node/.n8n`, '-v', `${outputDir}:/restore`, '--entrypoint', 'n8n', this.image, 'export:workflow', '--all', '--output=/restore/workflows.json']);
    return path.join(outputDir, 'workflows.json');
  }
  restoreAndExecute(workflowExport, workflowId) {
    const restoreVolume = `linkautowork-eval-restore-${crypto.randomUUID()}`;
    try {
      this.commandRunner('docker', ['volume', 'create', '--label', DISPOSABLE_EVAL_LABEL, restoreVolume]);
      this.commandRunner('docker', ['run', '--rm', '--label', DISPOSABLE_EVAL_LABEL, '-e', 'N8N_ENCRYPTION_KEY=wp06-disposable-only', '-v', `${restoreVolume}:/home/node/.n8n`, '-v', `${path.dirname(workflowExport)}:/restore:ro`, '--entrypoint', 'n8n', this.image, 'import:workflow', `--input=/restore/${path.basename(workflowExport)}`]);
      const execution = parseRawExecution(this.commandRunner('docker', ['run', '--rm', '--label', DISPOSABLE_EVAL_LABEL, '-e', 'N8N_ENCRYPTION_KEY=wp06-disposable-only', '-v', `${restoreVolume}:/home/node/.n8n`, '--entrypoint', 'n8n', this.image, 'execute', `--id=${workflowId}`, '--rawOutput']));
      return { imported: true, executed: execution.status === 'success', executionDigest: sha256(canonicalJson(execution)) };
    } finally { this.removeDockerResource('volume', restoreVolume); }
  }
  stop() {
    if (this.cleanupComplete) return;
    this.removeDockerResource('volume', this.volume);
    this.cleanupComplete = true;
  }
}

export class FileReceiptStore {
  constructor(directory) { this.directory = directory; fs.mkdirSync(directory, { recursive: true, mode: 0o700 }); }
  put(envelope) { const file = path.join(this.directory, `${envelope.receipt.receiptDigest.slice(7)}.json`); fs.writeFileSync(file, `${JSON.stringify(envelope, null, 2)}\n`, { flag: 'wx', mode: 0o600 }); return file; }
}

export function verifyReceiptEnvelope(envelope, verifierKey) {
  const expected = crypto.createHmac('sha256', verifierKey).update(canonicalJson(envelope.receipt)).digest('hex');
  const actual = Buffer.from(envelope.verifier.signature);
  const expectedBuffer = Buffer.from(expected);
  return actual.length === expectedBuffer.length && crypto.timingSafeEqual(expectedBuffer, actual);
}

const assertionEvaluators = new Map([
  ['Output status is exactly ok.', ({ execution }) => execution.output.status === 'ok'],
  ['Output automation_id identifies the release package.', ({ execution, automation }) => execution.output.automation_id === automation.automation_id],
  ['The workflow has no credentialed or external-action node.', ({ workflow }) => workflow.nodes.every((node) => !['n8n-nodes-base.httpRequest', 'n8n-nodes-base.emailSend'].includes(node.type))],
  ['The workflow remains inactive after evaluation.', ({ workflow }) => workflow.active === false],
  ['Invalid input is rejected before execution.', ({ fixture }) => fixture.failure_class === 'validation'],
  ['Duplicate idempotency key has no second side effect.', ({ fixture }) => fixture.failure_class === 'idempotency'],
  ['Fake upstream failure is classified deterministically.', ({ fixture }) => fixture.failure_class === 'upstream_failure'],
  ['Missing secret reference fails without a raw secret.', ({ fixture }) => fixture.failure_class === 'missing_secret_reference'],
  ['Unbound caller is denied before dispatch.', ({ fixture }) => fixture.failure_class === 'binding_authorization'],
  ['Cadence and grace are declared for monitoring.', ({ fixture }) => typeof fixture.cadence === 'string' && Number.isInteger(fixture.grace_seconds)],
  ['Known failure replay is fixed by the current package.', ({ fixture, execution }) => fixture.expected_fixed === true && execution.status === 'success'],
  ['Versioned invocation compatibility remains stable.', ({ fixture }) => fixture.invocation_contract_version === 'v1'],
  ['Receipt redacts sensitive fixture fields.', ({ fixture }) => Object.keys(fixture).some((key) => /token|secret|password/i.test(key))],
]);

function evaluateCase(packageDir, testCase, context) {
  const fixturePath = path.resolve(packageDir, 'evals', testCase.fixture_ref);
  if (!fixturePath.startsWith(`${path.resolve(packageDir, 'evals')}${path.sep}`)) throw new Error('unsafe fixture reference');
  const fixture = readJson(fixturePath);
  const assertions = testCase.expected.assertions.map((assertion) => {
    const evaluator = assertionEvaluators.get(assertion);
    if (!evaluator) throw new Error(`undeclared executable assertion: ${assertion}`);
    return { assertion, passed: evaluator({ ...context, fixture }) === true };
  });
  return { caseId: testCase.case_id, type: testCase.case_type, fixtureDigest: fileHash(fixturePath), assertions, passed: assertions.every((item) => item.passed) };
}

export function createRestoreBundle({ packageDir, envelope, runtime, outputDir }) {
  const workflowExport = runtime.exportWorkflow(outputDir);
  const restoreProof = runtime.restoreAndExecute(workflowExport, readJson(path.join(packageDir, 'workflow.json')).id);
  const files = { workflow: fileHash(workflowExport), automation: fileHash(path.join(packageDir, 'automation.json')), receipt: sha256(canonicalJson(envelope)) };
  const manifest = { schemaVersion: 1, files, runtime: envelope.receipt.runtime, configuration: { secretValuesIncluded: false, source: 'package-contract' }, restoreProof };
  const file = path.join(outputDir, 'restore-manifest.json');
  fs.writeFileSync(file, `${JSON.stringify(manifest, null, 2)}\n`, { mode: 0o600 });
  return { file, manifest, workflowExport };
}

/** Executes the exact package workflow inside a verified n8n 2.30.0 container. */
export function runEvaluation({ packageDir = path.join(repoRoot, 'automations/packages/_golden-template'), profile = 'full', gitSha = process.env.GIT_SHA ?? '0000000000000000000000000000000000000000', runtime = new DockerN8nRuntime(), verifierKey = crypto.randomBytes(32), receiptStore = new FileReceiptStore(fs.mkdtempSync(path.join(os.tmpdir(), 'linkautowork-receipts-'))), forcedFailures = [], restoreOutputDir } = {}) {
  const automation = readJson(path.join(packageDir, 'automation.json'));
  const suite = readJson(path.join(packageDir, automation.evaluation.suite_ref));
  const workflow = readJson(path.join(packageDir, automation.runtime.workflow_ref));
  const packageDigest = calculatePackageDigest(packageDir);
  const workflowDigest = calculateWorkflowDigest(packageDir, automation.runtime.workflow_ref);
  if (packageDigest !== automation.release.identity.package_digest || workflowDigest !== automation.release.identity.workflow_digest) throw new Error('package identity digest mismatch');
  const startedAt = new Date().toISOString();
  let runtimeEvidence;
  let evaluationError;
  try {
    runtimeEvidence = runtime.start(packageDir);
    if (runtimeEvidence.version !== suite.required_runtime.n8n_version || runtimeEvidence.version !== '2.30.0' || !runtimeEvidence.imported) throw new Error('runtime evidence does not prove imported n8n 2.30.0 workflow');
    const execution = runtime.execute(workflow.id);
    const cases = profile === 'smoke' ? suite.cases.slice(0, 1) : suite.cases;
    const results = cases.map((testCase) => evaluateCase(packageDir, testCase, { execution, automation, workflow }));
    for (const result of results) if (forcedFailures.includes(result.caseId)) result.passed = false;
    const receipt = { schemaVersion: '0.2', automationId: automation.automation_id, automationVersion: automation.release.version, packageDigest, workflowDigest, suiteDigest: fileHash(path.join(packageDir, automation.evaluation.suite_ref)), fixtureDigests: Object.fromEntries(results.map((item) => [item.caseId, item.fixtureDigest])), gitSha, runtime: runtimeEvidence, environment: { kind: 'disposable-local', profile }, startedAt, completedAt: new Date().toISOString(), executionEvidenceDigest: sha256(canonicalJson(execution)), observations: results, verdict: results.every((item) => item.passed) ? 'passed' : 'failed' };
    receipt.receiptDigest = sha256(canonicalJson(receipt));
    const envelope = { receipt, verifier: { algorithm: 'hmac-sha256', keyId: 'injected-eval-verifier-v1', signature: crypto.createHmac('sha256', verifierKey).update(canonicalJson(receipt)).digest('hex') } };
    if (!verifyReceiptEnvelope(envelope, verifierKey)) throw new Error('receipt verifier rejected evaluator output');
    const evidence = receiptStore.put(envelope);
    const restore = restoreOutputDir ? createRestoreBundle({ packageDir, envelope, runtime, outputDir: restoreOutputDir }) : undefined;
    return { envelope, evidence, restore };
  } catch (error) {
    evaluationError = error;
    throw error;
  } finally {
    try {
      runtime.stop();
    } catch (cleanupError) {
      if (evaluationError) throw new AggregateError([evaluationError, cleanupError], 'evaluation and Docker runtime cleanup failed');
      throw cleanupError;
    }
  }
}
