/**
 * WP-I6-S5 Autowork consumer validators.
 *
 * Frozen identity is LiNKautowork GitHub `development` pin from WP-I6-S0 plus
 * pin-time contract `2026-08-13.v1` (Issue 244 receipt contract ids are refused).
 * This module validates request / status / handoff / receipt / callback objects
 * only. It has no transport, credentials, Git write, Ledger, Gate, or job APIs.
 * Program Ledger, Git, and gates remain execution authority.
 */
import { createHash } from 'node:crypto'
import { fail } from './errors.mjs'
import { FROZEN_PROVIDERS } from './pins.mjs'

export const AUTOWORK_CONTRACT_VERSION = '2026-08-13.v1'
export const AUTOWORK_AUDIENCE = 'lautowork'
export const AUTOWORK_PIN = FROZEN_PROVIDERS.autowork
export const AUTOWORK_EXECUTION_AUTHORITY = 'none'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const DIGEST = /^sha256:[a-f0-9]{64}$/
const OPAQUE = /^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._~/%:-]+$/
const BOUNDED_TEXT = /^[A-Za-z0-9._:/@-]{1,256}$/
const SEMVER = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$/
const IDEMPOTENCY = /^[A-Za-z0-9._:-]{16,160}$/
const MEDIA = /^[a-z]+\/[a-z0-9.+-]+$/
const SENSITIVE = /^(?:secret|password|token|authorization|private(?:_?key|_?payload)?|prompt|transcript|conversation|raw(?:_payload)?|full.?content|body)$/i
const ACCESSOR = /^(?:input|input_ref|raw_payload|body|prompt|transcript|accessor|credentials|private_payload|full_content)$/i
const AUTHORITY = /^(?:authority|ledger|gate|git|execute|dispatch)$/i

const RUN_STATES = Object.freeze([
  'accepted', 'queued', 'running', 'succeeded', 'failed', 'expired', 'cancelled',
  'timed_out', 'rejected', 'blocked', 'quarantined', 'unavailable', 'contract_incompatible',
])
const TERMINAL = new Set([
  'succeeded', 'failed', 'expired', 'cancelled', 'timed_out', 'rejected',
  'blocked', 'quarantined', 'unavailable', 'contract_incompatible',
])
const OPERATION_KINDS = new Set([
  'status_collection', 'precheck', 'evidence_collection', 'notification_delivery',
  'external_assistance', 'artifact_transform', 'media_package', 'outreach_adapter',
])
const DENIED_WORK_KINDS = new Set([
  'execute', 'dispatch', 'order_placement', 'git_write', 'ledger_mutate', 'gate_close',
])
const REQUEST_KEYS = new Set([
  'contract_version', 'protocol_version', 'request_id', 'platform', 'automation',
  'operation_kind', 'input_ref', 'artifact_refs', 'result_destination_ref',
  'correlation_refs', 'brain_handoff_ref', 'idempotency_key', 'expires_at',
  'cancellation_requested_at', 'policy', 'approval_refs', 'sanitized_brain_candidate_ref',
])
const PLATFORM_KEYS = new Set([
  'org_id', 'actor_id', 'audience', 'capability', 'credential_id', 'binding_id',
  'issued_at', 'expires_at', 'revocation_ref',
])
const AUTOMATION_KEYS = new Set(['automation_id', 'version', 'definition_digest', 'configuration_ref'])
const REF_KEYS = new Set(['ref', 'digest', 'observed_at'])
const ARTIFACT_KEYS = new Set([
  'ref', 'digest', 'media_type', 'byte_size', 'provenance_ref', 'retention_profile_ref',
  'retrieval_authorization_ref',
])
const APPROVAL_KEYS = new Set([
  'approval_ref', 'approver_id', 'credential_id', 'binding_id', 'role', 'expires_at',
])
const POLICY_KEYS = new Set([
  'side_effect_class', 'approval_requirement', 'policy_profile_ref', 'data_classification',
  'rate_policy_ref', 'quiet_hour_policy_ref', 'suppression_ref',
])
const STATUS_KEYS = new Set(['request_id', 'state', 'attempt_count', 'automation', 'receipt_id'])
const STATUS_AUTOMATION_KEYS = new Set([
  'automation_id', 'version', 'definition_digest', 'configuration_digest',
])
const RECEIPT_KEYS = new Set([
  'contract_version', 'request_id', 'receipt_id', 'state', 'accepted_at', 'updated_at',
  'attempt_count', 'request_fingerprint', 'automation', 'freshness_at', 'result_refs',
  'evidence_refs', 'error', 'uncertain_outcome',
])
const CALLBACK_KEYS = new Set([
  'request_id', 'receipt_id', 'org_id', 'callback_binding_ref', 'source_timestamp', 'receipt',
])
const EVIDENCE_KEYS = new Set(['ref', 'digest', 'classification'])
const ERROR_KEYS = new Set(['category', 'code', 'retryable'])
const ERROR_CATEGORIES = new Set([
  'validation', 'authorization', 'forbidden', 'expired', 'unavailable', 'incompatible',
  'cancelled', 'timeout', 'transient', 'uncertain_outcome',
])

function closed(code, message, details = {}) {
  fail(code, message, { classification: 'fail_closed', ...details })
}

function denied(code, message, details = {}) {
  fail(code, message, { classification: 'denied', ...details })
}

function object(value, code = 'invalid_object') {
  if (!value || typeof value !== 'object' || Array.isArray(value)) closed(code)
  return value
}

function text(value, code) {
  if (typeof value !== 'string' || value.length === 0) closed(code)
  return value
}

function iso(value, code) {
  text(value, code)
  if (!Number.isFinite(Date.parse(value))) closed(code)
  return value
}

function uuid(value, code = 'autowork_id_malformed') {
  if (!UUID.test(text(value, code))) closed(code)
  return value
}

function digest(value, code = 'autowork_request_invalid') {
  if (!DIGEST.test(text(value, code))) closed(code)
  return value
}

function opaque(value, code) {
  if (!OPAQUE.test(text(value, code)) || value.length > 512) closed(code)
  return value
}

function bounded(value, code) {
  if (!BOUNDED_TEXT.test(text(value, code))) closed(code)
  return value
}

function rejectInheritedEnumerable(proto, label) {
  const protoDescriptors = Object.getOwnPropertyDescriptors(proto)
  for (const key of Object.keys(protoDescriptors)) {
    if (protoDescriptors[key].enumerable) {
      closed('inherited_property', `${label} inherits a property: ${key}`)
    }
  }
}

function snapshotChild(item, code, label, depth) {
  if (item === null || typeof item !== 'object') return item
  if (Array.isArray(item)) return snapshotArray(item, code, label, depth + 1)
  return snapshotOwnEnumerablePlainData(item, code, label, depth + 1)
}

function snapshotArray(value, code, label, depth) {
  if (depth > 5) closed('payload_too_deep')
  const list = value
  const descriptors = Object.getOwnPropertyDescriptors(list)
  const proto = Object.getPrototypeOf(list)
  if (proto !== Array.prototype && proto !== null) {
    closed('inherited_property', `${label} array must be a plain array`)
  }
  if (proto === Array.prototype) rejectInheritedEnumerable(proto, label)
  for (const key of Reflect.ownKeys(descriptors)) {
    if (key === 'length') continue
    const desc = descriptors[key]
    if (typeof key !== 'string') {
      if (desc.enumerable) closed('unknown_field', `${label} array has a non-string property key`)
      continue
    }
    if (desc.get !== undefined || desc.set !== undefined) {
      closed('accessor_property', `${label} array has an accessor: ${key}`)
    }
    if (desc.enumerable && !/^(0|[1-9]\d*)$/.test(key)) {
      closed('unknown_field', `${label} array has a non-index field: ${key}`)
    }
  }
  const length = descriptors.length && typeof descriptors.length.value === 'number'
    ? descriptors.length.value
    : 0
  const copy = []
  for (let index = 0; index < length; index += 1) {
    const desc = descriptors[String(index)]
    copy[index] = desc ? snapshotChild(desc.value, code, label, depth) : undefined
  }
  return Object.freeze(copy)
}

/** Copy own enumerable plain data before any semantic read; reject prototypes/accessors/TOCTOU. */
function snapshotOwnEnumerablePlainData(value, code = 'invalid_object', label = 'autowork input', depth = 0) {
  if (depth > 5) closed('payload_too_deep')
  const record = object(value, code)
  const proto = Object.getPrototypeOf(record)
  const descriptors = Object.getOwnPropertyDescriptors(record)
  if (proto !== Object.prototype && proto !== null) {
    closed('inherited_property', `${label} must be a plain object`)
  }
  if (proto === Object.prototype) rejectInheritedEnumerable(proto, label)
  const snapshot = Object.create(null)
  for (const key of Reflect.ownKeys(descriptors)) {
    const desc = descriptors[key]
    if (typeof key !== 'string') {
      if (desc.get !== undefined || desc.set !== undefined) {
        closed('accessor_property', `${label} has an accessor`)
      }
      if (desc.enumerable) closed('unknown_field', `${label} has a non-string property key`)
      continue
    }
    if (desc.get !== undefined || desc.set !== undefined) {
      closed('accessor_property', `${label} has an accessor: ${key}`)
    }
    if (!desc.enumerable) continue
    snapshot[key] = snapshotChild(desc.value, code, label, depth)
  }
  return Object.freeze(snapshot)
}

function denyKey(key, { accessors }) {
  if (key === 'internal' || AUTHORITY.test(key)) {
    denied(key === 'internal' ? 'autowork_internal_mutation' : 'autowork_authority_denied')
  }
  if (SENSITIVE.test(key)) closed('sensitive_field')
  if (accessors && ACCESSOR.test(key)) closed('accessor_field')
}

function walkKeys(value, options, depth = 0) {
  if (depth > 5) closed('payload_too_deep')
  if (typeof value === 'string' && value.length > 4096) closed('payload_too_large')
  if (value === null || typeof value !== 'object') return
  if (Array.isArray(value)) {
    if (value.length > 32) closed('payload_too_large')
    for (const item of value) walkKeys(item, options, depth + 1)
    return
  }
  for (const [key, item] of Object.entries(value)) {
    denyKey(key, options)
    walkKeys(item, options, depth + 1)
  }
}

function exactKeys(value, allowed) {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) closed('unknown_field')
  }
}

function exactPin(providerPin) {
  if (providerPin === undefined) return AUTOWORK_PIN
  const pin = object(providerPin, 'incompatible_pin')
  if (
    pin.repository !== AUTOWORK_PIN.repository
    || pin.commit !== AUTOWORK_PIN.commit
    || pin.tree !== AUTOWORK_PIN.tree
  ) {
    closed('incompatible_pin', 'provider pin must equal the frozen Autowork identity')
  }
  return AUTOWORK_PIN
}

function immutableRef(value, code) {
  const ref = object(value, code)
  exactKeys(ref, REF_KEYS)
  return Object.freeze({
    ref: opaque(ref.ref, code),
    digest: digest(ref.digest, code),
    observed_at: iso(ref.observed_at, code),
  })
}

function exactAutomation(value, code) {
  const automation = object(value, code)
  exactKeys(automation, AUTOMATION_KEYS)
  const version = text(automation.version, code)
  if (version === 'latest' || !SEMVER.test(version)) closed(code)
  return Object.freeze({
    automation_id: bounded(automation.automation_id, code),
    version,
    definition_digest: digest(automation.definition_digest, code),
    configuration_ref: immutableRef(automation.configuration_ref, code),
  })
}

function artifactRef(value) {
  const artifact = object(value, 'autowork_request_invalid')
  exactKeys(artifact, ARTIFACT_KEYS)
  opaque(artifact.ref, 'autowork_request_invalid')
  digest(artifact.digest, 'autowork_request_invalid')
  if (!MEDIA.test(text(artifact.media_type, 'autowork_request_invalid')) || artifact.media_type.length > 128) {
    closed('autowork_request_invalid')
  }
  if (!Number.isInteger(artifact.byte_size) || artifact.byte_size < 1 || artifact.byte_size > 10_000_000) {
    closed('autowork_request_invalid')
  }
  opaque(artifact.provenance_ref, 'autowork_request_invalid')
  opaque(artifact.retention_profile_ref, 'autowork_request_invalid')
  opaque(artifact.retrieval_authorization_ref, 'autowork_request_invalid')
}

function approvalRef(value, { now, enforceExpiry } = {}) {
  const approval = object(value, 'autowork_request_invalid')
  exactKeys(approval, APPROVAL_KEYS)
  opaque(approval.approval_ref, 'autowork_request_invalid')
  bounded(approval.approver_id, 'autowork_request_invalid')
  bounded(approval.credential_id, 'autowork_request_invalid')
  bounded(approval.binding_id, 'autowork_request_invalid')
  iso(approval.expires_at, 'autowork_request_invalid')
  if (enforceExpiry && Date.parse(approval.expires_at) <= now) closed('expired')
  if (approval.role !== undefined && !['matter_lawyer', 'tenant_administrator'].includes(approval.role)) {
    closed('autowork_request_invalid')
  }
  return approval
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonicalize(item)]),
    )
  }
  return value
}

function snapshotPreviousStatus(previousStatus) {
  if (previousStatus === undefined) return undefined
  if (typeof previousStatus === 'string') return previousStatus
  return snapshotOwnEnumerablePlainData(previousStatus, 'autowork_status_invalid', 'autowork previous status')
}

function previousState(previousStatus) {
  if (previousStatus === undefined) return undefined
  if (typeof previousStatus === 'string') return previousStatus
  return previousStatus.state
}

function previousAttempt(previousStatus) {
  if (!previousStatus || typeof previousStatus === 'string') return undefined
  return previousStatus.attempt_count
}

function assertMonotonic(previous, current, { previousTime, currentTime } = {}) {
  if (previous === undefined) return
  if (TERMINAL.has(previous) && current !== previous) closed('autowork_terminal_regression')
  if (previousTime !== undefined && currentTime !== undefined && Date.parse(currentTime) < Date.parse(previousTime)) {
    closed('autowork_terminal_regression')
  }
}

/** Stable canonical fingerprint used to bind receipts and idempotent replays. */
export function autoworkRequestFingerprint(value) {
  const request = snapshotOwnEnumerablePlainData(value, 'invalid_object', 'autowork request')
  return `sha256:${createHash('sha256').update(JSON.stringify(canonicalize(request))).digest('hex')}`
}

export function validateAutoworkRequest(value, { now = Date.now(), priorFingerprint, providerPin } = {}) {
  const pin = exactPin(providerPin)
  const request = snapshotOwnEnumerablePlainData(value, 'invalid_object', 'autowork request')
  walkKeys(request, { accessors: false })
  exactKeys(request, REQUEST_KEYS)
  if (request.contract_version !== AUTOWORK_CONTRACT_VERSION) closed('autowork_contract_incompatible')
  text(request.protocol_version, 'autowork_request_invalid')
  if (request.protocol_version.length > 64) closed('autowork_request_invalid')
  const requestId = uuid(request.request_id)
  const platform = object(request.platform, 'autowork_request_invalid')
  exactKeys(platform, PLATFORM_KEYS)
  uuid(platform.org_id, 'autowork_id_malformed')
  bounded(platform.actor_id, 'autowork_request_invalid')
  if (platform.audience !== AUTOWORK_AUDIENCE) denied('autowork_audience_denied')
  bounded(platform.capability, 'autowork_request_invalid')
  bounded(platform.credential_id, 'autowork_request_invalid')
  bounded(platform.binding_id, 'autowork_request_invalid')
  iso(platform.issued_at, 'autowork_request_invalid')
  iso(platform.expires_at, 'expired')
  opaque(platform.revocation_ref, 'autowork_request_invalid')
  if (String(platform.revocation_ref).endsWith('/revoked')) denied('autowork_identity_revoked')
  const automation = exactAutomation(request.automation, 'autowork_request_invalid')
  if (DENIED_WORK_KINDS.has(request.operation_kind) || !OPERATION_KINDS.has(request.operation_kind)) {
    denied('autowork_work_kind_denied')
  }
  immutableRef(request.input_ref, 'autowork_request_invalid')
  if (!Array.isArray(request.artifact_refs) || request.artifact_refs.length > 16) closed('autowork_request_invalid')
  for (const item of request.artifact_refs) artifactRef(item)
  opaque(request.result_destination_ref, 'autowork_request_invalid')
  if (!Array.isArray(request.correlation_refs) || request.correlation_refs.length < 1 || request.correlation_refs.length > 8) {
    closed('autowork_request_invalid')
  }
  for (const item of request.correlation_refs) immutableRef(item, 'autowork_request_invalid')
  if (request.operation_kind === 'external_assistance' && request.brain_handoff_ref === undefined) {
    closed('autowork_handoff_invalid')
  }
  if (request.brain_handoff_ref !== undefined) immutableRef(request.brain_handoff_ref, 'autowork_handoff_invalid')
  if (!IDEMPOTENCY.test(text(request.idempotency_key, 'autowork_request_invalid'))) closed('autowork_request_invalid')
  iso(request.expires_at, 'expired')
  if (request.cancellation_requested_at !== undefined) iso(request.cancellation_requested_at, 'autowork_request_invalid')
  if (Date.parse(request.expires_at) <= now || Date.parse(platform.expires_at) <= now) closed('expired')
  const policy = object(request.policy, 'autowork_request_invalid')
  exactKeys(policy, POLICY_KEYS)
  if (!['read_only', 'reversible_external_write', 'irreversible_external_write'].includes(policy.side_effect_class)) {
    closed('autowork_request_invalid')
  }
  if (!['none', 'explicit', 'dual_human'].includes(policy.approval_requirement)) closed('autowork_request_invalid')
  opaque(policy.policy_profile_ref, 'autowork_request_invalid')
  if (!['public', 'internal', 'confidential_metadata', 'restricted_metadata'].includes(policy.data_classification)) {
    closed('autowork_request_invalid')
  }
  if (policy.rate_policy_ref !== undefined) opaque(policy.rate_policy_ref, 'autowork_request_invalid')
  if (policy.quiet_hour_policy_ref !== undefined) opaque(policy.quiet_hour_policy_ref, 'autowork_request_invalid')
  if (policy.suppression_ref !== undefined) opaque(policy.suppression_ref, 'autowork_request_invalid')
  if (request.operation_kind === 'outreach_adapter' && policy.suppression_ref === undefined) {
    closed('autowork_request_invalid')
  }
  if (!Array.isArray(request.approval_refs) || request.approval_refs.length > 2) closed('autowork_request_invalid')
  const enforceExpiry = policy.approval_requirement === 'explicit' || policy.approval_requirement === 'dual_human'
  const approvals = request.approval_refs.map((item) => approvalRef(item, { now, enforceExpiry }))
  if (policy.approval_requirement === 'explicit' && approvals.length !== 1) closed('autowork_request_invalid')
  if (policy.approval_requirement === 'dual_human') {
    const approvers = new Set(approvals.map((item) => item.approver_id))
    const roles = new Set(approvals.map((item) => item.role))
    if (approvals.length !== 2 || approvers.size !== 2) closed('autowork_request_invalid')
    if (!roles.has('matter_lawyer') || !roles.has('tenant_administrator')) closed('autowork_request_invalid')
    if (request.sanitized_brain_candidate_ref === undefined) closed('autowork_request_invalid')
  }
  if (request.sanitized_brain_candidate_ref !== undefined) {
    opaque(request.sanitized_brain_candidate_ref, 'autowork_request_invalid')
  }
  const fingerprint = `sha256:${createHash('sha256').update(JSON.stringify(canonicalize(request))).digest('hex')}`
  if (priorFingerprint && priorFingerprint !== fingerprint) closed('autowork_fingerprint_conflict')
  return Object.freeze({
    requestId,
    idempotencyKey: request.idempotency_key,
    fingerprint,
    audience: platform.audience,
    automationId: automation.automation_id,
    version: automation.version,
    operationKind: request.operation_kind,
    executionAuthority: AUTOWORK_EXECUTION_AUTHORITY,
    pin,
  })
}

export function validateAutoworkStatus(value, { previousStatus, providerPin } = {}) {
  const pin = exactPin(providerPin)
  const status = snapshotOwnEnumerablePlainData(value, 'invalid_object', 'autowork status')
  const prior = snapshotPreviousStatus(previousStatus)
  walkKeys(status, { accessors: true })
  exactKeys(status, STATUS_KEYS)
  const requestId = uuid(status.request_id)
  if (!RUN_STATES.includes(status.state)) closed('autowork_status_invalid')
  assertMonotonic(previousState(prior), status.state)
  if (!Number.isInteger(status.attempt_count) || status.attempt_count < 0) closed('autowork_status_invalid')
  const priorAttempt = previousAttempt(prior)
  if (priorAttempt !== undefined && status.attempt_count < priorAttempt) closed('autowork_terminal_regression')
  const automation = object(status.automation, 'autowork_status_invalid')
  exactKeys(automation, STATUS_AUTOMATION_KEYS)
  bounded(automation.automation_id, 'autowork_status_invalid')
  if (automation.version === 'latest' || !SEMVER.test(automation.version)) closed('autowork_status_invalid')
  digest(automation.definition_digest, 'autowork_status_invalid')
  digest(automation.configuration_digest, 'autowork_status_invalid')
  if (status.receipt_id !== undefined) uuid(status.receipt_id)
  return Object.freeze({
    requestId,
    status: status.state,
    attemptCount: status.attempt_count,
    receiptId: status.receipt_id,
    executionAuthority: AUTOWORK_EXECUTION_AUTHORITY,
    pin,
  })
}

export function validateAutoworkHandoff(value, { providerPin } = {}) {
  const pin = exactPin(providerPin)
  const handoff = snapshotOwnEnumerablePlainData(value, 'autowork_handoff_invalid', 'autowork handoff')
  walkKeys(handoff, { accessors: true })
  exactKeys(handoff, REF_KEYS)
  return Object.freeze({
    handoffRef: opaque(handoff.ref, 'autowork_handoff_invalid'),
    digest: digest(handoff.digest, 'autowork_handoff_invalid'),
    observedAt: iso(handoff.observed_at, 'autowork_handoff_invalid'),
    executionAuthority: AUTOWORK_EXECUTION_AUTHORITY,
    pin,
  })
}

export function validateAutoworkReceipt(value, { request, fingerprint, now = Date.now(), providerPin } = {}) {
  const pin = exactPin(providerPin)
  const receipt = snapshotOwnEnumerablePlainData(value, 'invalid_object', 'autowork receipt')
  walkKeys(receipt, { accessors: true })
  exactKeys(receipt, RECEIPT_KEYS)
  if (receipt.contract_version !== AUTOWORK_CONTRACT_VERSION) closed('autowork_contract_incompatible')
  const requestId = uuid(receipt.request_id)
  const receiptId = uuid(receipt.receipt_id)
  if (!RUN_STATES.includes(receipt.state)) closed('autowork_status_invalid')
  iso(receipt.accepted_at, 'autowork_receipt_invalid')
  iso(receipt.updated_at, 'autowork_receipt_invalid')
  if (Date.parse(receipt.updated_at) < Date.parse(receipt.accepted_at)) closed('autowork_receipt_invalid')
  if (!Number.isInteger(receipt.attempt_count) || receipt.attempt_count < 0) closed('autowork_receipt_invalid')
  const requestFingerprint = digest(receipt.request_fingerprint, 'autowork_receipt_invalid')
  const automation = exactAutomation(receipt.automation, 'autowork_receipt_invalid')
  iso(receipt.freshness_at, 'expired')
  if (Date.parse(receipt.freshness_at) <= now) closed('expired')
  if (!Array.isArray(receipt.result_refs) || receipt.result_refs.length > 8) closed('autowork_receipt_invalid')
  if (!Array.isArray(receipt.evidence_refs) || receipt.evidence_refs.length > 8) closed('autowork_receipt_invalid')
  for (const item of [...receipt.result_refs, ...receipt.evidence_refs]) {
    const evidence = object(item, 'autowork_receipt_invalid')
    exactKeys(evidence, EVIDENCE_KEYS)
    opaque(evidence.ref, 'autowork_receipt_invalid')
    digest(evidence.digest, 'autowork_receipt_invalid')
    if (!['public', 'internal', 'confidential_metadata', 'restricted_metadata'].includes(evidence.classification)) {
      closed('autowork_receipt_invalid')
    }
  }
  if (receipt.error !== undefined) {
    const error = object(receipt.error, 'autowork_receipt_invalid')
    exactKeys(error, ERROR_KEYS)
    if (!ERROR_CATEGORIES.has(error.category)) closed('autowork_receipt_invalid')
    bounded(error.code, 'autowork_receipt_invalid')
    if (typeof error.retryable !== 'boolean') closed('autowork_receipt_invalid')
  }
  if (receipt.uncertain_outcome !== undefined && typeof receipt.uncertain_outcome !== 'boolean') {
    closed('autowork_receipt_invalid')
  }
  let trustedBinding = false
  if (request !== undefined) {
    const expected = snapshotOwnEnumerablePlainData(request, 'autowork_receipt_unbound', 'autowork request binding')
    if (expected.request_id !== requestId) closed('autowork_receipt_unbound')
    if (expected.automation?.automation_id !== automation.automation_id || expected.automation?.version !== automation.version) {
      closed('autowork_receipt_unbound')
    }
    if (expected.expires_at && Date.parse(receipt.accepted_at) >= Date.parse(expected.expires_at)) closed('expired')
    const computed = autoworkRequestFingerprint(expected)
    if (computed !== requestFingerprint) closed('autowork_fingerprint_conflict')
    if (fingerprint !== undefined && fingerprint !== computed) closed('autowork_fingerprint_conflict')
    trustedBinding = true
  } else if (fingerprint !== undefined) {
    if (fingerprint !== requestFingerprint) closed('autowork_fingerprint_conflict')
    trustedBinding = true
  }
  if (receipt.state === 'succeeded' && !trustedBinding) closed('autowork_receipt_unbound')
  return Object.freeze({
    requestId,
    receiptId,
    status: receipt.state,
    fingerprint: requestFingerprint,
    executionAuthority: AUTOWORK_EXECUTION_AUTHORITY,
    pin,
  })
}

export function validateAutoworkCallback(value, { previous, request, fingerprint, now = Date.now(), providerPin } = {}) {
  const pin = exactPin(providerPin)
  const callback = snapshotOwnEnumerablePlainData(value, 'invalid_object', 'autowork callback')
  const boundRequest = request === undefined
    ? undefined
    : snapshotOwnEnumerablePlainData(request, 'autowork_receipt_unbound', 'autowork request binding')
  walkKeys(callback, { accessors: true })
  exactKeys(callback, CALLBACK_KEYS)
  const requestId = uuid(callback.request_id)
  const receiptId = uuid(callback.receipt_id)
  const orgId = uuid(callback.org_id, 'autowork_id_malformed')
  if (boundRequest !== undefined) {
    const platform = object(boundRequest.platform, 'autowork_receipt_unbound')
    if (platform.org_id !== orgId) closed('autowork_receipt_unbound')
  }
  opaque(callback.callback_binding_ref, 'autowork_receipt_invalid')
  iso(callback.source_timestamp, 'autowork_receipt_invalid')
  const receipt = validateAutoworkReceipt(callback.receipt, {
    request: boundRequest,
    fingerprint,
    now,
    providerPin: pin,
  })
  if (receipt.requestId !== requestId || receipt.receiptId !== receiptId) closed('autowork_receipt_unbound')
  if (previous !== undefined) {
    const prior = snapshotOwnEnumerablePlainData(previous, 'autowork_receipt_invalid', 'autowork previous callback')
    if (prior.request_id && prior.request_id !== requestId) closed('autowork_receipt_unbound')
    if (prior.receipt_id && prior.receipt_id !== receiptId) closed('autowork_receipt_unbound')
    assertMonotonic(prior.receipt?.state, callback.receipt.state, {
      previousTime: prior.source_timestamp,
      currentTime: callback.source_timestamp,
    })
    if (prior.receipt?.updated_at && Date.parse(callback.receipt.updated_at) < Date.parse(prior.receipt.updated_at)) {
      closed('autowork_terminal_regression')
    }
    if (
      Number.isInteger(prior.receipt?.attempt_count)
      && callback.receipt.attempt_count < prior.receipt.attempt_count
    ) {
      closed('autowork_terminal_regression')
    }
  }
  return Object.freeze({
    requestId,
    receiptId,
    status: receipt.status,
    fingerprint: receipt.fingerprint,
    sourceTimestamp: callback.source_timestamp,
    executionAuthority: AUTOWORK_EXECUTION_AUTHORITY,
    pin,
  })
}
