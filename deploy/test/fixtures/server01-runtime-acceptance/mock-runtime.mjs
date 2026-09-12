import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '../../../..');
const packageDir = path.join(repoRoot, 'automations/evals/server01-runtime-acceptance/package');

const FORBIDDEN_NODE_TYPES = new Set(['n8n-nodes-base.httpRequest', 'n8n-nodes-base.emailSend']);
const SECRET_HEADER = /authorization|api-key|x-n8n-key/i;
const BEARER = /\bBearer\s+[A-Za-z0-9._~+\/-]{12,}\b/;
const SENSITIVE_KEY = /token|secret|password/i;
const ORG_ID = '11111111-1111-4111-8111-111111111111';
const CONFIG_REF = 'autowork://config/server01-runtime-acceptance/0.1.0';
const AUTOMATION_ID = 'server01-runtime-acceptance';
const AUTOMATION_VERSION = '0.1.0';
const NOW = '2026-09-12T00:00:00.000Z';
const HOLD = 'hold';

const terminal = new Set(['succeeded', 'failed', 'expired', 'cancelled', 'timed_out', 'rejected', 'quarantined', 'unavailable', 'contract_incompatible']);
const allowedTransitions = {
  accepted: ['queued', 'running', 'cancelled', 'expired', 'blocked', 'rejected', 'unavailable'],
  queued: ['running', 'cancelled', 'expired', 'blocked', 'failed', 'unavailable'],
  running: ['succeeded', 'failed', 'cancelled', 'timed_out', 'blocked', 'unavailable'],
  succeeded: [], failed: [], expired: [], cancelled: [], timed_out: [], rejected: [], quarantined: [], unavailable: [], contract_incompatible: [],
  blocked: ['cancelled', 'expired', 'unavailable'],
};

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

/**
 * Deterministic UUID derived from a seed. Used so receipts stay replay-stable.
 * @param {string} seed
 * @returns {string}
 */
export function uuidFrom(seed) {
  const bytes = Buffer.from(crypto.createHash('sha256').update(seed).digest().subarray(0, 16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes.toString('hex');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20, 32)}`;
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

/**
 * Recursively redacts token/secret/password fields. Raw values never enter receipts.
 * @param {unknown} value
 * @returns {unknown}
 */
export function redactSensitive(value) {
  if (Array.isArray(value)) return value.map(redactSensitive);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, SENSITIVE_KEY.test(key) ? '[redacted]' : redactSensitive(entry)]));
  }
  return value;
}

function containsSensitivePlaintext(value, secrets) {
  const text = typeof value === 'string' ? value : canonicalJson(value);
  return secrets.some((secret) => secret && text.includes(secret));
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
 * @returns {{ automation: object, suite: object, workflow: object, packageDir: string, inputSchema: object }}
 */
export function loadAcceptancePackage() {
  const automation = readJson(path.join(packageDir, 'automation.json'));
  const suite = readJson(path.join(packageDir, automation.evaluation.suite_ref));
  const workflow = readJson(path.join(packageDir, automation.runtime.workflow_ref));
  const inputSchema = readJson(path.join(packageDir, automation.contracts.input_schema_ref));
  if (workflow.active !== false) throw new Error('acceptance fixture must remain inactive');
  if (workflow.nodes.some((node) => FORBIDDEN_NODE_TYPES.has(node.type) || node.credentials)) {
    throw new Error('acceptance fixture must not use credentialed or external-action nodes');
  }
  return { automation, suite, workflow, packageDir, inputSchema };
}

/**
 * Compiles the package input schema. Invalid payloads fail closed before mock admission.
 * @param {object} schema
 */
export function compileInputValidator(schema) {
  const ajv = new Ajv2020({ allErrors: true, strict: true, validateFormats: true });
  addFormats(ajv);
  return ajv.compile(schema);
}

/** Fail-closed mock of AW-02 durable admission plus AW-03 callback/receipt rules. Never talks to n8n. */
export class MockAdmissionStore {
  constructor() {
    this.records = new Map();
    this.idempotency = new Map();
    this.killSwitches = new Set();
    this.dispatchCount = new Map();
  }

  setKillSwitch(orgId, automationId, active) {
    const key = `${orgId}:${automationId ?? '*'}`;
    if (active) this.killSwitches.add(key); else this.killSwitches.delete(key);
  }

  isKilled(orgId, automationId) {
    return this.killSwitches.has(`${orgId}:*`) || this.killSwitches.has(`${orgId}:${automationId}`);
  }

  fingerprint(request) {
    return sha256(canonicalJson({
      org_id: request.org_id,
      automation_id: request.automation_id,
      version: request.version,
      configuration_ref: request.configuration_ref,
      idempotency_key: request.idempotency_key,
      input: request.input,
    }));
  }

  accept(request) {
    if (this.isKilled(request.org_id, request.automation_id)) {
      throw Object.assign(new Error('provider kill switch prevents request acceptance'), { category: 'blocked' });
    }
    const fingerprint = this.fingerprint(request);
    const key = `${request.org_id}:${request.idempotency_key}`;
    const priorId = this.idempotency.get(key);
    if (priorId) {
      const prior = this.records.get(priorId);
      if (prior.fingerprint !== fingerprint) {
        throw Object.assign(new Error('idempotency key conflicts with changed canonical request content'), { category: 'conflict' });
      }
      return { record: this.clone(prior), replay: true };
    }
    const record = {
      orgId: request.org_id,
      request,
      fingerprint,
      state: 'accepted',
      version: 1,
      attempts: 0,
      n8n_dispatched: false,
      live_n8n_activation: HOLD,
    };
    this.records.set(request.request_id, record);
    this.idempotency.set(key, request.request_id);
    return { record: this.clone(record), replay: false };
  }

  getRequest(orgId, requestId) {
    return this.clone(this.require(orgId, requestId));
  }

  transition(orgId, requestId, expectedVersion, next) {
    const record = this.require(orgId, requestId);
    if (record.version !== expectedVersion) {
      throw Object.assign(new Error('expected version does not match durable request version'), { category: 'invalid_state' });
    }
    if (terminal.has(record.state) || !allowedTransitions[record.state].includes(next)) {
      throw Object.assign(new Error('provider lifecycle transition is not allowed'), { category: 'invalid_state' });
    }
    if ((next === 'queued' || next === 'running') && this.isKilled(orgId, record.request.automation_id)) {
      throw Object.assign(new Error('provider kill switch prevents new start'), { category: 'blocked' });
    }
    if (next === 'running') {
      record.attempts += 1;
      this.dispatchCount.set(requestId, (this.dispatchCount.get(requestId) ?? 0) + 1);
      record.n8n_dispatched = false;
    }
    record.state = next;
    record.version += 1;
    return this.clone(record);
  }

  writeReceipt(orgId, receipt) {
    const record = this.require(orgId, receipt.request_id);
    if (receipt.automation_id !== record.request.automation_id || receipt.version !== record.request.version || receipt.configuration_ref !== record.request.configuration_ref) {
      throw Object.assign(new Error('receipt automation/configuration does not bind to request'), { category: 'forbidden' });
    }
    const clean = redactSensitive(receipt);
    if (record.receipt) {
      if (record.receipt.receipt_id !== clean.receipt_id) {
        throw Object.assign(new Error('provider receipt is immutable'), { category: 'conflict' });
      }
      return structuredClone(record.receipt);
    }
    record.receipt = structuredClone(clean);
    record.state = clean.state;
    record.attempts = clean.attempt_count ?? record.attempts;
    return structuredClone(record.receipt);
  }

  admitCallback(orgId, callback) {
    if (orgId !== callback.org_id) {
      throw Object.assign(new Error('organisation isolation denied'), { category: 'forbidden' });
    }
    const record = this.require(orgId, callback.request_id);
    if (callback.callback_binding_ref !== record.request.configuration_ref) {
      throw Object.assign(new Error('callback configuration binding does not match request'), { category: 'invalid_callback' });
    }
    if (record.callbackTimestamp && Date.parse(callback.source_timestamp) <= Date.parse(record.callbackTimestamp)) {
      throw Object.assign(new Error('callback is replayed or out of order'), { category: 'invalid_callback' });
    }
    if (callback.receipt.request_fingerprint !== record.fingerprint) {
      throw Object.assign(new Error('callback receipt fingerprint does not match request'), { category: 'invalid_callback' });
    }
    const before = record.receipt ? canonicalJson(record.receipt) : null;
    const receipt = this.writeReceipt(orgId, callback.receipt);
    record.callbackTimestamp = callback.source_timestamp;
    return { receipt, receipt_mutated: before !== null && before !== canonicalJson(record.receipt) };
  }

  mockDispatchCount(requestId) {
    return this.dispatchCount.get(requestId) ?? 0;
  }

  require(orgId, requestId) {
    const record = this.records.get(requestId);
    if (!record) throw Object.assign(new Error('provider request not found'), { category: 'not_found' });
    if (orgId !== record.orgId) throw Object.assign(new Error('organisation isolation denied'), { category: 'forbidden' });
    return record;
  }

  clone(record) {
    return structuredClone(record);
  }
}

function invocation(caseId, input, idempotencyKey) {
  return {
    request_id: uuidFrom(`request:${caseId}`),
    org_id: ORG_ID,
    automation_id: AUTOMATION_ID,
    version: AUTOMATION_VERSION,
    configuration_ref: CONFIG_REF,
    idempotency_key: idempotencyKey ?? `server01-runtime-acceptance-${caseId}-key-01`,
    input,
  };
}

function receiptFor(record, state, extras = {}) {
  return {
    contract_version: '2026-08-13.v1',
    request_id: record.request.request_id,
    receipt_id: uuidFrom(`receipt:${record.request.request_id}`),
    state,
    accepted_at: NOW,
    updated_at: NOW,
    attempt_count: record.attempts,
    request_fingerprint: record.fingerprint,
    automation_id: record.request.automation_id,
    version: record.request.version,
    configuration_ref: record.request.configuration_ref,
    n8n_dispatched: false,
    live_n8n_activation: HOLD,
    output: extras.output,
    redacted_fields: extras.redacted_fields,
    does_not_prove: ['automation_run', 'consumer_outcome', 'consumer_gate', 'external_side_effect', 'e2e_readiness', 'production_readiness'],
    ...(extras.synthetic_token !== undefined ? { synthetic_token: extras.synthetic_token } : {}),
  };
}

function caught(fn) {
  try {
    return { ok: true, value: fn() };
  } catch (error) {
    return { ok: false, error };
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

/**
 * Executes one named suite case with real store/schema behavior. Fixture mock flags are never the verdict.
 * @param {string} caseId
 * @param {object} fixture
 * @param {{ workflow: object, validateInput: Function }} ctx
 */
export function executeAcceptanceCase(caseId, fixture, ctx) {
  const store = new MockAdmissionStore();
  const secrets = Object.entries(fixture)
    .filter(([key, value]) => SENSITIVE_KEY.test(key) && typeof value === 'string')
    .map(([, value]) => value);

  const run = () => {
    switch (caseId) {
      case 'success-output-contract': {
        assert(ctx.validateInput(fixture.input) === true, 'success input must satisfy input schema');
        const first = store.accept(invocation(caseId, fixture.input));
        const queued = store.transition(ORG_ID, first.record.request.request_id, first.record.version, 'queued');
        const saved = store.writeReceipt(ORG_ID, receiptFor(queued, 'succeeded', {
          output: { status: 'ok', automation_id: AUTOMATION_ID, n8n_dispatched: false },
        }));
        assert(saved.output.status === 'ok', 'mocked output status must be ok');
        assert(saved.n8n_dispatched === false, 'success must not dispatch n8n');
        assert(store.mockDispatchCount(queued.request.request_id) === 0, 'success must not enter mock running/dispatch');
        return { state: saved.state, error_code: null, replay: first.replay, output: saved.output, receipt: saved };
      }
      case 'no-side-effects': {
        assert(fixture.expected_external_actions === 0, 'fixture must declare zero external actions');
        assert(ctx.workflow.active === false, 'workflow must stay inactive');
        assert(ctx.workflow.nodes.every((node) => !FORBIDDEN_NODE_TYPES.has(node.type) && !node.credentials), 'workflow must have no credentialed or external-action nodes');
        const admitted = store.accept(invocation(caseId, { case_id: 'no-side-effects' }));
        assert(admitted.record.n8n_dispatched === false);
        return { state: admitted.record.state, error_code: null, replay: false, receipt: null };
      }
      case 'rejection-invalid-input': {
        const valid = ctx.validateInput(fixture.input);
        assert(valid === false, 'invalid input must fail the compiled input schema');
        throw Object.assign(new Error('invalid input is rejected before mock dispatch'), { category: 'invalid_state', failure_class: 'validation' });
      }
      case 'duplicate-request': {
        const request = invocation(caseId, { case_id: 'duplicate-request' }, fixture.idempotency_key);
        const first = store.accept(request);
        const replay = store.accept(structuredClone(request));
        const conflict = caught(() => store.accept({ ...structuredClone(request), input: { case_id: 'success-output-contract' } }));
        assert(first.replay === false && replay.replay === true, 'duplicate key must replay');
        assert(replay.record.request.request_id === first.record.request.request_id, 'replay must keep execution identity');
        assert(conflict.ok === false && conflict.error.category === 'conflict', 'changed canonical content must conflict');
        assert(store.mockDispatchCount(first.record.request.request_id) === 0);
        return { state: replay.record.state, error_code: null, replay: true, same_execution_identity: true, receipt: null };
      }
      case 'cancel-before-dispatch': {
        const first = store.accept(invocation(caseId, { case_id: 'cancel-before-dispatch' }));
        const cancelled = store.transition(ORG_ID, first.record.request.request_id, first.record.version, 'cancelled');
        const second = caught(() => store.transition(ORG_ID, cancelled.request.request_id, cancelled.version, 'queued'));
        assert(cancelled.state === 'cancelled');
        assert(second.ok === false && second.error.category === 'invalid_state');
        assert(store.mockDispatchCount(cancelled.request.request_id) === 0);
        return { state: 'cancelled', error_code: null, replay: false, cancellation_execution_proven: false, receipt: null };
      }
      case 'cancel-after-queued': {
        const first = store.accept(invocation(caseId, { case_id: 'cancel-after-queued' }));
        const queued = store.transition(ORG_ID, first.record.request.request_id, first.record.version, 'queued');
        const cancelled = store.transition(ORG_ID, queued.request.request_id, queued.version, 'cancelled');
        const second = caught(() => store.transition(ORG_ID, cancelled.request.request_id, cancelled.version, 'running'));
        assert(cancelled.state === 'cancelled');
        assert(second.ok === false && second.error.category === 'invalid_state');
        assert(store.mockDispatchCount(cancelled.request.request_id) === 0);
        return { state: 'cancelled', error_code: null, second_dispatch: false, receipt: null };
      }
      case 'timeout-exhausted': {
        const first = store.accept(invocation(caseId, { case_id: 'timeout-exhausted' }));
        const queued = store.transition(ORG_ID, first.record.request.request_id, first.record.version, 'queued');
        const running = store.transition(ORG_ID, queued.request.request_id, queued.version, 'running');
        const timed = store.transition(ORG_ID, running.request.request_id, running.version, 'timed_out');
        assert(timed.state === 'timed_out');
        assert(timed.n8n_dispatched === false);
        return { state: 'timed_out', error_code: null, receipt: null };
      }
      case 'provider-outage': {
        const first = store.accept(invocation(caseId, { case_id: 'provider-outage' }));
        const queued = store.transition(ORG_ID, first.record.request.request_id, first.record.version, 'queued');
        const down = store.transition(ORG_ID, queued.request.request_id, queued.version, 'unavailable');
        assert(down.state === 'unavailable');
        return { state: 'unavailable', error_code: 'unavailable', receipt: null };
      }
      case 'callback-replay': {
        const first = store.accept(invocation(caseId, { case_id: 'callback-replay' }));
        const queued = store.transition(ORG_ID, first.record.request.request_id, first.record.version, 'queued');
        const callback = {
          request_id: queued.request.request_id,
          org_id: ORG_ID,
          callback_binding_ref: CONFIG_REF,
          source_timestamp: '2026-09-12T00:01:00.000Z',
          receipt: receiptFor(queued, 'succeeded'),
        };
        const admitted = store.admitCallback(ORG_ID, callback);
        const replayed = caught(() => store.admitCallback(ORG_ID, callback));
        const original = canonicalJson(admitted.receipt);
        const after = canonicalJson(store.getRequest(ORG_ID, queued.request.request_id).receipt);
        assert(replayed.ok === false && replayed.error.category === 'invalid_callback');
        assert(original === after, 'replayed callback must not mutate the receipt');
        return { state: admitted.receipt.state, error_code: 'invalid_callback', receipt_mutated: false, receipt: admitted.receipt };
      }
      case 'late-callback': {
        const first = store.accept(invocation(caseId, { case_id: 'late-callback' }));
        const queued = store.transition(ORG_ID, first.record.request.request_id, first.record.version, 'queued');
        const originalReceipt = receiptFor(queued, 'succeeded');
        const firstAdmit = store.admitCallback(ORG_ID, {
          request_id: queued.request.request_id,
          org_id: ORG_ID,
          callback_binding_ref: CONFIG_REF,
          source_timestamp: '2026-09-12T00:01:00.000Z',
          receipt: originalReceipt,
        });
        const late = store.admitCallback(ORG_ID, {
          request_id: queued.request.request_id,
          org_id: ORG_ID,
          callback_binding_ref: CONFIG_REF,
          source_timestamp: '2026-09-12T00:02:00.000Z',
          receipt: { ...originalReceipt, state: 'failed', output: { status: 'forged' } },
        });
        assert(late.receipt.receipt_id === firstAdmit.receipt.receipt_id);
        assert(late.receipt.state === 'succeeded', 'late callback must return the original terminal receipt');
        assert(late.receipt_mutated === false);
        return { state: late.receipt.state, error_code: null, returns_original_receipt: true, receipt_mutated: false, receipt: late.receipt };
      }
      case 'kill-switch-blocked': {
        store.setKillSwitch(ORG_ID, AUTOMATION_ID, true);
        const attempt = caught(() => store.accept(invocation(caseId, { case_id: 'kill-switch-blocked' })));
        assert(attempt.ok === false && attempt.error.category === 'blocked');
        assert(store.records.size === 0, 'kill switch must block before queue');
        return { state: 'blocked', error_code: 'blocked', receipt: null };
      }
      case 'restart-continuity': {
        const request = invocation(caseId, { case_id: 'restart-continuity' });
        const first = store.accept(request);
        const queued = store.transition(ORG_ID, first.record.request.request_id, first.record.version, 'queued');
        const restart = store.accept(structuredClone(request));
        assert(restart.replay === true);
        assert(restart.record.request.request_id === queued.request.request_id);
        assert(restart.record.state === 'queued');
        assert(store.mockDispatchCount(queued.request.request_id) === 0);
        return { state: 'queued', error_code: null, replay: true, second_dispatch: false, receipt: null };
      }
      case 'privacy-redaction': {
        assert(typeof fixture.synthetic_token === 'string' && fixture.synthetic_token.length > 0, 'privacy fixture must include a synthetic token');
        const admitted = store.accept(invocation(caseId, { case_id: 'privacy-redaction' }));
        const queued = store.transition(ORG_ID, firstRequestId(admitted), admitted.record.version, 'queued');
        const saved = store.writeReceipt(ORG_ID, receiptFor(queued, 'succeeded', {
          output: { status: 'ok', automation_id: AUTOMATION_ID, n8n_dispatched: false },
          redacted_fields: ['synthetic_token'],
          synthetic_token: fixture.synthetic_token,
        }));
        assert(saved.synthetic_token === '[redacted]', 'receipt must redact synthetic_token');
        assert(containsSensitivePlaintext(saved, secrets) === false, 'receipt must not retain raw secret plaintext');
        return { state: 'succeeded', error_code: null, redacted_fields: ['synthetic_token'], receipt: saved };
      }
      default:
        throw new Error(`undeclared mock branch: ${caseId}`);
    }
  };

  const outcome = caught(run);
  const failedClosed = outcome.ok === false;
  const value = outcome.ok ? outcome.value : { state: null, error_code: outcome.error.category ?? 'failed', receipt: null };
  const n8n_dispatched = false;
  const activation = {
    case_id: caseId,
    request_id: uuidFrom(`request:${caseId}`),
    org_id: ORG_ID,
    state: value.state ?? (failedClosed ? 'rejected' : 'queued'),
    replay: value.replay === true,
    n8n_dispatched,
    live_n8n_activation: HOLD,
    error_code: value.error_code ?? null,
    receipt_mutated: value.receipt_mutated === true,
    does_not_prove: ['automation_run', 'consumer_outcome', 'consumer_gate', 'external_side_effect', 'e2e_readiness', 'production_readiness'],
  };
  if (value.receipt && containsSensitivePlaintext(value.receipt, secrets)) {
    return { passed: false, activation, error: new Error('receipt leaked sensitive plaintext'), n8n_dispatched };
  }
  return { passed: casePassed(caseId, fixture, outcome), activation, error: outcome.error, n8n_dispatched, value };
}

function firstRequestId(admitted) {
  return admitted.record.request.request_id;
}

function casePassed(caseId, fixture, outcome) {
  if (caseId === 'rejection-invalid-input') {
    return outcome.ok === false && outcome.error?.category === 'invalid_state';
  }
  if (caseId === 'kill-switch-blocked') {
    return outcome.ok === true && outcome.value.error_code === 'blocked';
  }
  if (caseId === 'callback-replay') {
    return outcome.ok === true && outcome.value.error_code === 'invalid_callback' && outcome.value.receipt_mutated === false;
  }
  if (!outcome.ok) return false;
  const value = outcome.value;
  if (value.n8n_dispatched === true) return false;
  switch (caseId) {
    case 'success-output-contract':
      return value.output?.status === 'ok' && value.output?.n8n_dispatched === false && value.state === 'succeeded';
    case 'no-side-effects':
      return fixture.expected_external_actions === 0;
    case 'duplicate-request':
      return value.replay === true && value.same_execution_identity === true;
    case 'cancel-before-dispatch':
      return value.state === 'cancelled' && value.cancellation_execution_proven === false;
    case 'cancel-after-queued':
      return value.state === 'cancelled' && value.second_dispatch === false;
    case 'timeout-exhausted':
      return value.state === 'timed_out';
    case 'provider-outage':
      return value.error_code === 'unavailable';
    case 'late-callback':
      return value.returns_original_receipt === true && value.receipt_mutated === false;
    case 'restart-continuity':
      return value.replay === true && value.second_dispatch === false;
    case 'privacy-redaction':
      return Array.isArray(value.redacted_fields) && value.redacted_fields.includes('synthetic_token');
    default:
      return false;
  }
}

/**
 * Builds the compact AW-03-compatible mock activation view.
 * @param {object} fixture
 * @param {string} caseId
 * @param {object} [activation]
 */
export function mockActivation(fixture, caseId, activation) {
  return activation ?? {
    case_id: caseId,
    request_id: uuidFrom(`request:${caseId}`),
    org_id: ORG_ID,
    state: 'queued',
    replay: false,
    n8n_dispatched: false,
    live_n8n_activation: HOLD,
    error_code: null,
    receipt_mutated: false,
    does_not_prove: ['automation_run', 'consumer_outcome', 'consumer_gate', 'external_side_effect', 'e2e_readiness', 'production_readiness'],
  };
}

/**
 * Evaluates every declared suite case against executed mock behavior, not self-declared JSON flags.
 * @returns {{ verdict: 'passed' | 'failed', results: object[], receiptDigest: string, envelope: object }}
 */
export function evaluateAcceptanceSuite() {
  const { automation, suite, workflow, inputSchema } = loadAcceptancePackage();
  const validateInput = compileInputValidator(inputSchema);
  const results = suite.cases.map((testCase) => {
    const fixturePath = path.resolve(packageDir, 'evals', testCase.fixture_ref);
    if (!fixturePath.startsWith(`${path.resolve(packageDir, 'evals')}${path.sep}`)) {
      throw new Error(`unsafe fixture reference: ${testCase.fixture_ref}`);
    }
    const fixture = readJson(fixturePath);
    const executed = executeAcceptanceCase(testCase.case_id, fixture, { automation, workflow, validateInput });
    const passed = executed.passed === true && executed.n8n_dispatched === false && executed.activation.live_n8n_activation === HOLD;
    return {
      caseId: testCase.case_id,
      type: testCase.case_type,
      expected: testCase.expected.outcome,
      activation: executed.activation,
      passed,
      independent: true,
    };
  });
  const receipt = {
    schemaVersion: 'aw-04.mock.v1',
    automationId: automation.automation_id,
    automationVersion: automation.release.version,
    packageDigest: automation.release.identity.package_digest,
    workflowDigest: automation.release.identity.workflow_digest,
    sourceGitSha: automation.release.identity.source_git_sha,
    n8nVersion: suite.required_runtime.n8n_version,
    environment: { kind: 'source-only-mock', live_n8n: false, server01: HOLD, docker: false, network: false },
    observations: results,
    verdict: results.every((item) => item.passed) ? 'passed' : 'failed',
  };
  return { envelope: { receipt }, receiptDigest: sha256(canonicalJson(receipt)), results, verdict: receipt.verdict };
}
