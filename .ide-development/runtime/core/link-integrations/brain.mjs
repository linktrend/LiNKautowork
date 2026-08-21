/**
 * Fail-closed LiNKbrain knowledge / coordination validator.
 *
 * Consumes `FROZEN_PROVIDERS.brain` and `ConsumerContractError`. Accepts only
 * advisory, metadata-first projections (`contractVersion` `2.0.0`) and returns
 * opaque `projectionRef` plus optional `handoffRef`. Optional OKF `0.2`
 * mapping is validated only after advisory / `executionAuthority=none` gates.
 * Snapshots own enumerable
 * plain data properties before any read; inherited, prototype, accessor,
 * getter, setter, and TOCTOU inputs are rejected. Validation and the returned
 * projection use only that immutable snapshot. Brain remains advisory
 * (`authority=advisory`, `executionAuthority=none`). This module never calls
 * Brain, executes tools, copies raw conversation, or holds credentials.
 */

import { fail } from './errors.mjs'
import { validateOkfMapping } from './mcp.mjs'
import { FROZEN_PROVIDERS } from './pins.mjs'

export const BRAIN_CONTRACT_VERSION = '2.0.0'
export const BRAIN_PIN = FROZEN_PROVIDERS.brain

const OPAQUE_REF = /^[A-Za-z0-9][A-Za-z0-9._~:-]{0,159}$/
const GIT_SHA = /^[a-f0-9]{40}$/
const SUMMARY_MAX = 2000
const PROJECTION_KEYS = new Set([
  'contractVersion',
  'authority',
  'executionAuthority',
  'projectionRef',
  'summary',
  'handoffRef',
  'okf',
])
const CONTEXT_KEYS = new Set(['providerPin', 'providerStatus'])
const PIN_KEYS = new Set(['repository', 'commit', 'tree'])
const EXECUTION_REQUEST_KEYS = new Set([
  'tools',
  'tool',
  'toolRequest',
  'toolCalls',
  'tool_request',
  'execute',
  'execution',
  'skills_run',
])
const HANDOFF_KEYS = new Set([
  'contractVersion',
  'authority',
  'executionAuthority',
  'handoffRef',
  'namespaceRef',
  'status',
  'actorRef',
  'targetRef',
  'summary',
  'createdAt',
  'updatedAt',
])
const HANDOFF_REF = /^[A-Za-z0-9][A-Za-z0-9._~:/@+-]{0,255}$/
const HANDOFF_STATUSES = new Set(['open', 'accepted', 'closed'])
const SENSITIVE = /(?:secret|password|token|authorization|private.?key|prompt|transcript|conversation|raw(?:_|$)|full.?content|^body$)/i

/**
 * @param {unknown} value
 * @param {string} [code]
 * @returns {Record<string, unknown>}
 */
function object(value, code = 'invalid_object') {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    fail(code, 'value must be a non-array object', { classification: 'fail_closed' })
  }
  return /** @type {Record<string, unknown>} */ (value)
}

/**
 * @param {unknown} value
 * @returns {value is string}
 */
function isNonEmptyString(value) {
  return typeof value === 'string' && value.length > 0
}

/**
 * @param {unknown} item
 * @param {string} code
 * @param {string} label
 * @param {number} depth
 * @returns {unknown}
 */
function snapshotChild(item, code, label, depth) {
  if (item === null || typeof item !== 'object') return item
  if (Array.isArray(item)) return snapshotArray(item, code, label, depth + 1)
  return snapshotOwnEnumerablePlainData(item, code, label, depth + 1)
}

/**
 * @param {object} proto
 * @param {string} label
 */
function rejectInheritedEnumerable(proto, label) {
  const protoDescriptors = Object.getOwnPropertyDescriptors(proto)
  for (const key of Object.keys(protoDescriptors)) {
    if (protoDescriptors[key].enumerable) {
      fail('inherited_property', `${label} inherits a property: ${key}`, {
        classification: 'fail_closed',
        field: key,
      })
    }
  }
}

/**
 * @param {unknown} value
 * @param {string} code
 * @param {string} label
 * @param {number} depth
 * @returns {readonly unknown[]}
 */
function snapshotArray(value, code, label, depth) {
  if (depth > 5) {
    fail('payload_too_deep', 'brain projection exceeded bounded depth', { classification: 'fail_closed' })
  }
  const list = /** @type {unknown[]} */ (value)
  const descriptors = Object.getOwnPropertyDescriptors(list)
  const proto = Object.getPrototypeOf(list)
  if (proto !== Array.prototype && proto !== null) {
    fail('inherited_property', `${label} array must be a plain array`, { classification: 'fail_closed' })
  }
  if (proto === Array.prototype) {
    rejectInheritedEnumerable(proto, label)
  }
  for (const key of Object.keys(descriptors)) {
    if (key === 'length') continue
    const desc = descriptors[key]
    if (desc.get !== undefined || desc.set !== undefined) {
      fail('accessor_property', `${label} array has an accessor: ${key}`, {
        classification: 'fail_closed',
        field: key,
      })
    }
    if (desc.enumerable && !/^(0|[1-9]\d*)$/.test(key)) {
      fail('unknown_field', `${label} array has a non-index field: ${key}`, {
        classification: 'fail_closed',
        field: key,
      })
    }
  }
  const length = descriptors.length && typeof descriptors.length.value === 'number' ? descriptors.length.value : 0
  const copy = []
  for (let index = 0; index < length; index += 1) {
    const desc = descriptors[String(index)]
    copy[index] = desc ? snapshotChild(desc.value, code, label, depth) : undefined
  }
  return Object.freeze(copy)
}

/**
 * Copy own enumerable plain data properties before any semantic read.
 * Rejects inherited, prototype, accessor, getter, setter, and TOCTOU inputs.
 *
 * @param {unknown} value
 * @param {string} [code]
 * @param {string} [label]
 * @param {number} [depth]
 * @returns {Record<string, unknown>}
 */
function snapshotOwnEnumerablePlainData(value, code = 'invalid_object', label = 'brain input', depth = 0) {
  if (depth > 5) {
    fail('payload_too_deep', 'brain projection exceeded bounded depth', { classification: 'fail_closed' })
  }
  const record = object(value, code)
  const proto = Object.getPrototypeOf(record)
  const descriptors = Object.getOwnPropertyDescriptors(record)
  if (proto !== Object.prototype && proto !== null) {
    fail('inherited_property', `${label} must be a plain object`, { classification: 'fail_closed' })
  }
  if (proto === Object.prototype) {
    rejectInheritedEnumerable(proto, label)
  }
  const snapshot = Object.create(null)
  for (const key of Object.keys(descriptors)) {
    const desc = descriptors[key]
    if (desc.get !== undefined || desc.set !== undefined) {
      fail('accessor_property', `${label} has an accessor: ${key}`, {
        classification: 'fail_closed',
        field: key,
      })
    }
    if (!desc.enumerable) continue
    snapshot[key] = snapshotChild(desc.value, code, label, depth)
  }
  return Object.freeze(snapshot)
}

/**
 * @param {Record<string, unknown>} value
 * @param {number} [depth]
 */
function rejectSensitive(value, depth = 0) {
  if (depth > 5) {
    fail('payload_too_deep', 'brain projection exceeded bounded depth', { classification: 'fail_closed' })
  }
  for (const [key, item] of Object.entries(value)) {
    if (SENSITIVE.test(key)) {
      fail('sensitive_field', `brain projection contains a sensitive field: ${key}`, {
        classification: 'fail_closed',
        field: key,
      })
    }
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      rejectSensitive(/** @type {Record<string, unknown>} */ (item), depth + 1)
    }
  }
}

/**
 * @param {Record<string, unknown>} value
 * @param {Set<string>} allowed
 * @param {string} label
 */
function rejectUnknown(value, allowed, label) {
  for (const key of Object.keys(value)) {
    if (EXECUTION_REQUEST_KEYS.has(key)) {
      fail('brain_execution_request', `${label} requests Brain execution or tools: ${key}`, {
        classification: 'fail_closed',
        field: key,
      })
    }
    if (!allowed.has(key)) {
      fail('unknown_field', `${label} has an unknown field: ${key}`, {
        classification: 'fail_closed',
        field: key,
      })
    }
  }
}

/**
 * @param {unknown} value
 * @param {string} field
 * @returns {string}
 */
function opaqueRef(value, field) {
  if (typeof value !== 'string' || !OPAQUE_REF.test(value) || value.length > 160) {
    fail('brain_identity_invalid', `brain ${field} is malformed`, {
      classification: 'fail_closed',
      field,
    })
  }
  return value
}

/**
 * @param {unknown} pin
 */
function assertFrozenPin(pin) {
  if (pin === undefined) return
  const value = object(pin, 'incompatible_pin')
  rejectSensitive(value)
  rejectUnknown(value, PIN_KEYS, 'brain provider pin')
  if (!isNonEmptyString(value.commit) || !isNonEmptyString(value.tree)) {
    fail('incompatible_pin', 'brain provider pin is missing commit or tree', {
      classification: 'fail_closed',
      provider: 'brain',
    })
  }
  if (!GIT_SHA.test(value.commit) || !GIT_SHA.test(value.tree)) {
    fail('brain_identity_invalid', 'brain provider pin identity is malformed', {
      classification: 'fail_closed',
      provider: 'brain',
    })
  }
  if (value.repository !== undefined && value.repository !== BRAIN_PIN.repository) {
    fail('incompatible_pin', 'context provider pin does not match the frozen LiNKbrain pin', {
      classification: 'fail_closed',
      provider: 'brain',
      frozenRepository: BRAIN_PIN.repository,
      frozenCommit: BRAIN_PIN.commit,
      frozenTree: BRAIN_PIN.tree,
    })
  }
  if (value.commit !== BRAIN_PIN.commit || value.tree !== BRAIN_PIN.tree) {
    fail('incompatible_pin', 'context provider pin does not match the frozen LiNKbrain pin', {
      classification: 'fail_closed',
      provider: 'brain',
      frozenRepository: BRAIN_PIN.repository,
      frozenCommit: BRAIN_PIN.commit,
      frozenTree: BRAIN_PIN.tree,
    })
  }
}

/**
 * @param {Record<string, unknown>} context
 */
function assertContext(context) {
  rejectSensitive(context)
  rejectUnknown(context, CONTEXT_KEYS, 'brain context')
  assertFrozenPin(context.providerPin)

  if (context.providerStatus === undefined) return
  if (context.providerStatus === 'unavailable') {
    fail('brain_unavailable', 'brain provider reports unavailability', {
      classification: 'unavailable',
      provider: 'brain',
    })
  }
  if (context.providerStatus === 'available') return
  fail('incompatible_provider_state', 'brain provider state is incompatible', {
    classification: 'fail_closed',
    provider: 'brain',
    providerStatus: context.providerStatus,
  })
}

/**
 * @param {unknown} value
 * @param {unknown} [context]
 * @returns {Readonly<{ projectionRef: string, handoffRef?: string }>}
 */
export function validateBrainProjection(value, context = {}) {
  const ctx = snapshotOwnEnumerablePlainData(context, 'invalid_context', 'brain context')
  assertContext(ctx)

  if (value === null || value === undefined) {
    fail('brain_projection_unavailable', 'required brain projection material is absent', {
      classification: 'unavailable',
      provider: 'brain',
    })
  }

  const record = snapshotOwnEnumerablePlainData(value, 'invalid_object', 'brain projection')
  rejectSensitive(record)
  rejectUnknown(record, PROJECTION_KEYS, 'brain projection')

  if (record.contractVersion !== BRAIN_CONTRACT_VERSION) {
    fail('wrong_contract_version', 'contractVersion must be 2.0.0', {
      classification: 'fail_closed',
      field: 'contractVersion',
    })
  }

  const projectionRef = record.projectionRef
  if (projectionRef === undefined || projectionRef === null || projectionRef === '') {
    fail('brain_projection_unavailable', 'required brain projectionRef is missing', {
      classification: 'unavailable',
      provider: 'brain',
      field: 'projectionRef',
    })
  }
  const acceptedRef = opaqueRef(projectionRef, 'projectionRef')

  if (!isNonEmptyString(record.authority)) {
    fail('brain_identity_invalid', 'authority must be a non-empty string', {
      classification: 'fail_closed',
      field: 'authority',
    })
  }
  if (!isNonEmptyString(record.executionAuthority)) {
    fail('brain_identity_invalid', 'executionAuthority must be a non-empty string', {
      classification: 'fail_closed',
      field: 'executionAuthority',
    })
  }
  if (record.authority !== 'advisory') {
    fail('brain_authority_denied', 'brain authority must remain advisory', {
      classification: 'denied',
      field: 'authority',
      authority: record.authority,
    })
  }
  if (record.executionAuthority !== 'none') {
    fail('brain_execution_denied', 'brain executionAuthority must remain none', {
      classification: 'denied',
      field: 'executionAuthority',
      executionAuthority: record.executionAuthority,
    })
  }

  if (record.summary !== undefined) {
    if (!isNonEmptyString(record.summary)) {
      fail('brain_summary_invalid', 'brain summary must be a non-empty string', {
        classification: 'fail_closed',
        field: 'summary',
      })
    }
    if (record.summary.length > SUMMARY_MAX) {
      fail('brain_summary_invalid', 'brain summary exceeds the bounded size', {
        classification: 'fail_closed',
        field: 'summary',
      })
    }
  }

  // Optional OKF mapping is validated after Brain authority gates so it can
  // never override advisory / executionAuthority=none provider authority.
  if (record.okf !== undefined) {
    validateOkfMapping(record.okf)
  }

  /** @type {{ projectionRef: string, handoffRef?: string }} */
  const accepted = { projectionRef: acceptedRef }
  if (record.handoffRef !== undefined) {
    accepted.handoffRef = opaqueRef(record.handoffRef, 'handoffRef')
  }
  return Object.freeze(accepted)
}

/**
 * Validate a bounded Brain handoff without turning it into execution
 * authority. Handoff references are opaque and namespace-bound; payloads,
 * prompts, and tool instructions are never accepted.
 *
 * @param {unknown} value
 * @returns {Readonly<Record<string, string>>}
 */
export function validateBrainHandoff(value) {
  const record = snapshotOwnEnumerablePlainData(value, 'brain_handoff_invalid', 'brain handoff')
  rejectSensitive(record)
  rejectUnknown(record, HANDOFF_KEYS, 'brain handoff')
  if (record.contractVersion !== BRAIN_CONTRACT_VERSION) {
    fail('brain_handoff_incompatible', 'brain handoff contractVersion is incompatible', {
      classification: 'incompatible',
      field: 'contractVersion',
    })
  }
  if (record.authority !== 'advisory') {
    fail('brain_handoff_denied', 'brain handoff authority must remain advisory', {
      classification: 'denied',
      field: 'authority',
    })
  }
  if (record.executionAuthority !== 'none') {
    fail('brain_execution_denied', 'brain handoff executionAuthority must remain none', {
      classification: 'denied',
      field: 'executionAuthority',
    })
  }
  if (typeof record.handoffRef !== 'string' || !HANDOFF_REF.test(record.handoffRef)) {
    fail('brain_handoff_malformed', 'brain handoff reference is malformed', {
      classification: 'fail_closed',
      field: 'handoffRef',
    })
  }
  if (typeof record.namespaceRef !== 'string' || !HANDOFF_REF.test(record.namespaceRef)) {
    fail('brain_handoff_malformed', 'brain handoff namespace is malformed', {
      classification: 'fail_closed',
      field: 'namespaceRef',
    })
  }
  if (record.status === 'unavailable') {
    fail('brain_handoff_unavailable', 'brain handoff provider is unavailable', {
      classification: 'unavailable',
      provider: 'brain',
    })
  }
  if (typeof record.status !== 'string' || !HANDOFF_STATUSES.has(record.status)) {
    fail('brain_handoff_malformed', 'brain handoff status is malformed', {
      classification: 'fail_closed',
      field: 'status',
    })
  }
  for (const field of ['actorRef', 'targetRef']) {
    if (record[field] !== undefined && (typeof record[field] !== 'string' || !HANDOFF_REF.test(record[field]))) {
      fail('brain_handoff_malformed', `brain handoff ${field} is malformed`, {
        classification: 'fail_closed',
        field,
      })
    }
  }
  if (record.summary !== undefined && (typeof record.summary !== 'string' || record.summary.length > 1000)) {
    fail('brain_handoff_malformed', 'brain handoff summary is outside the bounded size', {
      classification: 'fail_closed',
      field: 'summary',
    })
  }
  for (const field of ['createdAt', 'updatedAt']) {
    if (record[field] !== undefined && (typeof record[field] !== 'string' || !Number.isFinite(Date.parse(record[field])))) {
      fail('brain_handoff_malformed', `brain handoff ${field} is malformed`, {
        classification: 'fail_closed',
        field,
      })
    }
  }
  return Object.freeze({
    contractVersion: BRAIN_CONTRACT_VERSION,
    authority: 'advisory',
    executionAuthority: 'none',
    handoffRef: record.handoffRef,
    namespaceRef: record.namespaceRef,
    status: record.status,
    ...(record.actorRef === undefined ? {} : { actorRef: record.actorRef }),
    ...(record.targetRef === undefined ? {} : { targetRef: record.targetRef }),
    ...(record.summary === undefined ? {} : { summary: record.summary }),
    ...(record.createdAt === undefined ? {} : { createdAt: record.createdAt }),
    ...(record.updatedAt === undefined ? {} : { updatedAt: record.updatedAt }),
  })
}
