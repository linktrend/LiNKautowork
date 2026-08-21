/**
 * Fail-closed LiNKskills release and telemetry validator.
 *
 * Consumes `FROZEN_PROVIDERS.skills` and `ConsumerContractError`. Accepts only
 * published + qualified + available immutable releases whose provider
 * commit/tree match the S0 pin, with `sha256:` digests and discovery /
 * validation / execution addressing. Telemetry is the bounded completed-use
 * subset of pin-time `use-report-v0.2` (`report_kind`, `score`,
 * `skill_release_ref`, `actor_ref`, optional typed `issue.issue_ref`).
 * Inputs are snapshotted as plain own enumerable data properties before
 * validate/copy. This module never executes a skill, calls Skills HTTP, loads
 * a local catalogue or full pack, or adds credentials / network adapters.
 */

import { fail } from './errors.mjs'
import { FROZEN_PROVIDERS } from './pins.mjs'

export const SKILLS_CONTRACT_VERSION = 'skills.api.v0.2'
export const SKILLS_PIN = FROZEN_PROVIDERS.skills

const GIT_SHA = /^[a-f0-9]{40}$/
const SHA256 = /^sha256:[a-f0-9]{64}$/
const SKILL_ID = /^[a-z0-9][a-z0-9-]{0,94}$/
const SKILL_VERSION = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$/
const OPAQUE = /^opaque:[A-Za-z0-9][A-Za-z0-9._:/-]{1,94}$/
const SENSITIVE = /(?:secret|password|token|authorization|private.?key|credential|prompt|transcript|conversation|raw(?:_|$)|full.?content|^body$|narrative|notes|customer|consumer_data|^case$|^lead$|trading_order|portfolio|brokerage)/i

const ADDRESSING = Object.freeze(['discovery', 'validation', 'execution'])
const LIFECYCLES = new Set(['published', 'draft', 'deprecated', 'retired', 'eval_pending', 'unpublished'])
const QUALIFICATIONS = new Set(['qualified', 'unqualified', 'expired', 'withdrawn', 'not_applicable'])
const DENIED_AVAILABILITY = new Set(['unauthorized', 'forbidden'])
const UNAVAILABLE = new Set([
  'unavailable',
  'offline',
  'degraded',
  'revoked',
  'quarantined',
  'withdrawn',
  'disabled',
  'stale',
])
const INCOMPATIBLE_AVAILABILITY = new Set(['incompatible', 'contract_incompatible'])
const ISSUE_TYPES = new Set([
  'incorrect',
  'incomplete',
  'ambiguous',
  'unsafe',
  'incompatible',
  'unavailable',
  'latency',
  'other',
])
const ISSUE_SEVERITIES = new Set(['low', 'medium', 'high', 'critical'])

const DISCOVERY_OPERATIONS = Object.freeze([
  'skills_capabilities_get',
  'skills_catalog_list',
  'skills_catalog_search',
  'skills_release_list',
  'skills_release_describe',
])
const VALIDATION_OPERATIONS = Object.freeze([
  'skills_release_verify',
  'skills_qualification_get',
])
const EXECUTION_OPERATIONS = Object.freeze([
  'skills_release_entrypoint_get',
  'skills_release_sections_list',
  'skills_release_section_get',
  'skills_release_resources_list',
  'skills_release_resource_get',
  'skills_release_content_get',
])
const ADDRESSING_OPERATIONS = Object.freeze({
  discovery: new Set(DISCOVERY_OPERATIONS),
  validation: new Set(VALIDATION_OPERATIONS),
  execution: new Set(EXECUTION_OPERATIONS),
})
const LEGACY_OPERATIONS = new Set([
  'skills_run_start',
  'skills_run_update',
  'skills_run_complete',
  'skills_run_fail',
  'skills_tool_resolve',
  'skills_tool_invoke',
  'skills_list',
  'skills_search',
  'skills_describe',
  'skills_fragment_get',
  'skills_release_get',
  'skills_input_validate',
  'skills_output_validate',
  'skills_trace_candidate_submit',
])
const TELEMETRY_OPERATIONS = new Set([
  'skills_use_report_submit',
  'skills_use_report_status_get',
  'skills_feedback_submit',
  'skills_feedback_status_get',
])

const RELEASE_KEYS = new Set([
  'contractVersion',
  'providerCommit',
  'providerTree',
  'skillId',
  'version',
  'releaseHash',
  'bundleHash',
  'manifestHash',
  'lifecycle',
  'qualification',
  'availability',
  'fragmentLevel',
  'addressing',
  'operation',
  'compatibility',
])
const TELEMETRY_KEYS = new Set([
  'report_kind',
  'score',
  'issue',
  'skill_release_ref',
  'actor_ref',
])
const ISSUE_KEYS = new Set(['type', 'severity', 'issue_ref'])
const RELEASE_CROSS_FIELDS = new Set([
  'report_kind',
  'score',
  'issue',
  'skill_release_ref',
  'actor_ref',
  'reportKind',
  'skillReleaseRef',
  'actorRef',
  'idempotencyKey',
  'nonUseOutcome',
  'outcome',
  'opaqueRefs',
])
const TELEMETRY_CROSS_FIELDS = new Set([
  'contractVersion',
  'providerCommit',
  'providerTree',
  'skillId',
  'version',
  'releaseHash',
  'bundleHash',
  'manifestHash',
  'lifecycle',
  'qualification',
  'availability',
  'fragmentLevel',
  'addressing',
  'operation',
  'compatibility',
])
const RELEASE_COMPETING = new Set([
  'skill_id',
  'skill_version',
  'release_hash',
  'bundle_hash',
  'manifest_hash',
  'fragment_level',
  'provider_commit',
  'provider_tree',
  'contract_version',
  'report_kind',
])
const TELEMETRY_COMPETING = new Set([
  'reportKind',
  'skillReleaseRef',
  'actorRef',
  'idempotencyKey',
  'issueRef',
])

/**
 * @param {string} code
 * @param {string} message
 * @param {{
 *   classification: string,
 *   field?: string,
 *   provider?: string,
 *   frozenCommit?: string,
 *   frozenTree?: string,
 * }} details
 * @returns {never}
 */
function closed(code, message, details) {
  fail(code, message, {
    classification: details.classification,
    ...(details.field ? { field: details.field } : {}),
    ...(details.provider ? { provider: details.provider } : {}),
    ...(details.frozenCommit ? { frozenCommit: details.frozenCommit } : {}),
    ...(details.frozenTree ? { frozenTree: details.frozenTree } : {}),
  })
}

/**
 * @param {unknown} value
 * @returns {boolean}
 */
function isPlainObject(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const proto = Object.getPrototypeOf(value)
  return proto === Object.prototype || proto === null
}

/**
 * @param {unknown} value
 * @param {number} depth
 * @returns {unknown}
 */
function snapshotValue(value, depth) {
  if (value === null || typeof value !== 'object') return value
  if (Array.isArray(value)) return snapshotArray(value, depth)
  return snapshotPlain(value, 'invalid_object', depth)
}

/**
 * @param {unknown} value
 * @param {number} depth
 * @returns {unknown[]}
 */
function snapshotArray(value, depth) {
  if (depth > 5) {
    closed('payload_too_deep', 'skills payload exceeded bounded depth', { classification: 'fail_closed' })
  }
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype) {
    closed('skills_prototype_forbidden', 'skills payload arrays must be plain arrays', {
      classification: 'fail_closed',
    })
  }
  const descriptors = Object.getOwnPropertyDescriptors(value)
  /** @type {unknown[]} */
  const snapshot = []
  for (let index = 0; index < value.length; index += 1) {
    const key = String(index)
    const descriptor = descriptors[key]
    if (!descriptor || !descriptor.enumerable || descriptor.get !== undefined || descriptor.set !== undefined) {
      closed('skills_accessor_forbidden', 'skills payload must not use accessors', {
        classification: 'fail_closed',
        field: key,
      })
    }
    snapshot.push(snapshotValue(descriptor.value, depth + 1))
  }
  return snapshot
}

/**
 * @param {unknown} value
 * @param {string} [code]
 * @param {number} [depth]
 * @returns {Record<string, unknown>}
 */
function snapshotPlain(value, code = 'invalid_object', depth = 0) {
  if (depth > 5) {
    closed('payload_too_deep', 'skills payload exceeded bounded depth', { classification: 'fail_closed' })
  }
  if (!isPlainObject(value)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      closed('skills_prototype_forbidden', 'skills payload must be a plain object', {
        classification: 'fail_closed',
      })
    }
    closed(code, 'value must be a plain non-array object', { classification: 'fail_closed' })
  }
  const descriptors = Object.getOwnPropertyDescriptors(value)
  /** @type {Record<string, unknown>} */
  const snapshot = Object.create(null)
  for (const key of Reflect.ownKeys(descriptors)) {
    if (typeof key !== 'string') {
      closed('unknown_field', 'skills payload has a non-string property key', { classification: 'fail_closed' })
    }
    const descriptor = descriptors[key]
    if (!descriptor.enumerable) {
      closed('skills_non_data_property', 'skills payload must use own enumerable data properties', {
        classification: 'fail_closed',
        field: key,
      })
    }
    if (descriptor.get !== undefined || descriptor.set !== undefined) {
      closed('skills_accessor_forbidden', 'skills payload must not use accessors', {
        classification: 'fail_closed',
        field: key,
      })
    }
    snapshot[key] = snapshotValue(descriptor.value, depth + 1)
  }
  return snapshot
}

/**
 * @param {unknown} value
 * @param {number} [depth]
 */
function rejectSensitive(value, depth = 0) {
  if (depth > 5) {
    closed('payload_too_deep', 'skills payload exceeded bounded depth', { classification: 'fail_closed' })
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      if (item && typeof item === 'object') {
        rejectSensitive(item, depth + 1)
      }
    }
    return
  }
  if (!value || typeof value !== 'object') return
  for (const [key, item] of Object.entries(value)) {
    if (SENSITIVE.test(key)) {
      closed('sensitive_field', `skills payload contains a sensitive field: ${key}`, {
        classification: 'fail_closed',
        field: key,
      })
    }
    if (item && typeof item === 'object') {
      rejectSensitive(item, depth + 1)
    }
  }
}

/**
 * @param {Record<string, unknown>} value
 * @param {ReadonlySet<string>} competing
 * @param {ReadonlySet<string>} cross
 * @param {ReadonlySet<string>} allowed
 * @param {string} label
 */
function rejectShape(value, competing, cross, allowed, label) {
  for (const key of Object.keys(value)) {
    if (competing.has(key)) {
      closed('competing_envelope', `${label} uses a competing envelope field: ${key}`, {
        classification: 'fail_closed',
        field: key,
      })
    }
    if (cross.has(key)) {
      closed('cross_operation_field', `${label} mixes a cross-operation field: ${key}`, {
        classification: 'fail_closed',
        field: key,
      })
    }
    if (!allowed.has(key)) {
      closed('unknown_field', `${label} has an unknown field: ${key}`, {
        classification: 'fail_closed',
        field: key,
      })
    }
  }
}

/**
 * @param {unknown} value
 * @returns {boolean}
 */
function isLegacyOperation(value) {
  if (typeof value !== 'string' || value === '') return false
  return LEGACY_OPERATIONS.has(value) || value.startsWith('skills_run_') || value.startsWith('skills_tool_')
}

/**
 * Reject any path segment equal to `latest` case-insensitively when separated
 * by `/`, `:`, or `@` — not only suffix forms. Applies to skillId, version,
 * and opaque telemetry refs (`Latest`, `LATEST`, `release:Latest`, etc.).
 *
 * @param {unknown} value
 * @param {string} field
 */
function rejectLatestAlias(value, field) {
  if (typeof value !== 'string' || value === '') return
  for (const segment of value.split(/[/:@]/)) {
    if (segment.toLowerCase() === 'latest') {
      closed('skills_latest_alias', `skills ${field} must be an immutable identity, not latest`, {
        classification: 'fail_closed',
        field,
      })
    }
  }
}

/**
 * Missing / null / empty pin keys are unavailable. Present wrong-type,
 * non-SHA, or otherwise malformed pin material is fail-closed separately.
 *
 * @param {Record<string, unknown>} record
 * @returns {'absent' | 'present'}
 */
function pinMaterialPresence(record) {
  const hasCommit = Object.hasOwn(record, 'providerCommit')
  const hasTree = Object.hasOwn(record, 'providerTree')
  if (!hasCommit || !hasTree) return 'absent'
  const commit = record.providerCommit
  const tree = record.providerTree
  if (commit === null || commit === undefined || commit === '') return 'absent'
  if (tree === null || tree === undefined || tree === '') return 'absent'
  return 'present'
}

/**
 * @param {unknown} commit
 * @param {unknown} tree
 */
function rejectMalformedPin(commit, tree) {
  if (typeof commit !== 'string' || typeof tree !== 'string' || !GIT_SHA.test(commit) || !GIT_SHA.test(tree)) {
    closed('skills_pin_invalid', 'skills provider pin is malformed', {
      classification: 'fail_closed',
      provider: 'skills',
    })
  }
}

/**
 * @param {unknown} value
 * @returns {Readonly<{
 *   skillId: string,
 *   version: string,
 *   releaseHash: string,
 *   bundleHash: string,
 *   manifestHash: string,
 *   fragmentLevel: number,
 *   addressing: string,
 *   providerCommit: string,
 *   providerTree: string,
 * }>}
 */
export function validateSkillsRelease(value) {
  if (value === null || value === undefined) {
    closed('skills_release_unavailable', 'required skills provider pin material is absent', {
      classification: 'unavailable',
      provider: 'skills',
    })
  }

  const release = snapshotPlain(value)
  if (pinMaterialPresence(release) === 'absent') {
    closed('skills_release_unavailable', 'required skills provider pin material is absent', {
      classification: 'unavailable',
      provider: 'skills',
    })
  }
  rejectSensitive(release)
  rejectShape(release, RELEASE_COMPETING, RELEASE_CROSS_FIELDS, RELEASE_KEYS, 'skills release')

  if (isLegacyOperation(release.operation)) {
    closed('skills_legacy_operation', 'legacy skills run/tool names are not on the v0.2 consumer surface', {
      classification: 'fail_closed',
      field: 'operation',
    })
  }
  if (TELEMETRY_OPERATIONS.has(/** @type {string} */ (release.operation))) {
    closed('cross_operation_field', 'skills release cannot carry a telemetry operation', {
      classification: 'fail_closed',
      field: 'operation',
    })
  }
  if (release.operation === 'skills_release_package_get') {
    closed('skills_full_pack_forbidden', 'skills consumer must not address a full remote pack', {
      classification: 'fail_closed',
      field: 'operation',
    })
  }

  if (release.contractVersion !== SKILLS_CONTRACT_VERSION) {
    closed('skills_contract_incompatible', 'contractVersion must be skills.api.v0.2', {
      classification: 'fail_closed',
      field: 'contractVersion',
    })
  }

  const providerCommit = release.providerCommit
  const providerTree = release.providerTree
  rejectMalformedPin(providerCommit, providerTree)
  if (providerCommit !== SKILLS_PIN.commit || providerTree !== SKILLS_PIN.tree) {
    closed('incompatible_pin', 'skills provider pin does not match the frozen LiNKskills pin', {
      classification: 'fail_closed',
      provider: 'skills',
      frozenCommit: SKILLS_PIN.commit,
      frozenTree: SKILLS_PIN.tree,
    })
  }

  rejectLatestAlias(release.skillId, 'skillId')
  rejectLatestAlias(release.version, 'version')
  if (typeof release.skillId !== 'string' || !SKILL_ID.test(release.skillId)) {
    closed('skills_identity_invalid', 'skillId must be a lowercase hyphenated identity', {
      classification: 'fail_closed',
      field: 'skillId',
    })
  }
  if (typeof release.version !== 'string' || !SKILL_VERSION.test(release.version)) {
    closed('skills_identity_invalid', 'version must be an immutable semver identity', {
      classification: 'fail_closed',
      field: 'version',
    })
  }

  for (const field of ['releaseHash', 'bundleHash', 'manifestHash']) {
    if (typeof release[field] !== 'string' || !SHA256.test(/** @type {string} */ (release[field]))) {
      closed('skills_digest_invalid', `skills digest is malformed: ${field}`, {
        classification: 'fail_closed',
        field,
      })
    }
  }

  if (!Number.isInteger(release.fragmentLevel) || /** @type {number} */ (release.fragmentLevel) < 0 || /** @type {number} */ (release.fragmentLevel) > 6) {
    closed('skills_fragment_invalid', 'fragmentLevel must be an integer in 0..6', {
      classification: 'fail_closed',
      field: 'fragmentLevel',
    })
  }

  if (typeof release.addressing !== 'string' || !ADDRESSING.includes(release.addressing)) {
    closed('skills_addressing_invalid', 'addressing must be discovery, validation, or execution', {
      classification: 'fail_closed',
      field: 'addressing',
    })
  }
  if (release.operation !== undefined) {
    const allowed = ADDRESSING_OPERATIONS[/** @type {'discovery' | 'validation' | 'execution'} */ (release.addressing)]
    if (typeof release.operation !== 'string' || !allowed.has(release.operation)) {
      closed('cross_operation_field', 'skills operation is not allowed for the declared addressing', {
        classification: 'fail_closed',
        field: 'operation',
      })
    }
  }

  if (typeof release.lifecycle !== 'string' || !LIFECYCLES.has(release.lifecycle)) {
    closed('skills_lifecycle_invalid', 'skills lifecycle is malformed', {
      classification: 'fail_closed',
      field: 'lifecycle',
    })
  }
  if (release.lifecycle !== 'published') {
    closed('skills_not_published', 'skills lifecycle is not published', {
      classification: 'denied',
      field: 'lifecycle',
    })
  }

  if (typeof release.qualification !== 'string' || !QUALIFICATIONS.has(release.qualification)) {
    closed('skills_qualification_invalid', 'skills qualification is malformed', {
      classification: 'fail_closed',
      field: 'qualification',
    })
  }
  if (release.qualification !== 'qualified') {
    closed('skills_not_qualified', 'skills qualification is not qualified', {
      classification: 'denied',
      field: 'qualification',
    })
  }

  if (release.compatibility === undefined || release.compatibility === 'compatible') {
    // omitted or explicit compatible — allowed
  } else if (release.compatibility === 'incompatible') {
    closed('skills_release_incompatible', 'skills compatibility is incompatible', {
      classification: 'incompatible',
      field: 'compatibility',
    })
  } else {
    closed('skills_compatibility_invalid', 'skills compatibility is malformed', {
      classification: 'fail_closed',
      field: 'compatibility',
    })
  }

  if (typeof release.availability !== 'string') {
    closed('skills_availability_invalid', 'skills availability is malformed', {
      classification: 'fail_closed',
      field: 'availability',
    })
  }
  if (INCOMPATIBLE_AVAILABILITY.has(release.availability)) {
    closed('skills_release_incompatible', 'skills availability is incompatible', {
      classification: 'incompatible',
      field: 'availability',
    })
  }
  if (DENIED_AVAILABILITY.has(release.availability)) {
    closed('skills_not_permitted', 'skills release is forbidden by policy', {
      classification: 'denied',
      field: 'availability',
    })
  }
  if (release.availability !== 'available') {
    if (!UNAVAILABLE.has(release.availability)) {
      closed('skills_availability_invalid', 'skills availability is malformed', {
        classification: 'fail_closed',
        field: 'availability',
      })
    }
    closed('skills_release_unavailable', 'skills release is not available', {
      classification: 'unavailable',
      field: 'availability',
    })
  }

  return Object.freeze({
    skillId: /** @type {string} */ (release.skillId),
    version: /** @type {string} */ (release.version),
    releaseHash: /** @type {string} */ (release.releaseHash),
    bundleHash: /** @type {string} */ (release.bundleHash),
    manifestHash: /** @type {string} */ (release.manifestHash),
    fragmentLevel: /** @type {number} */ (release.fragmentLevel),
    addressing: /** @type {string} */ (release.addressing),
    providerCommit: /** @type {string} */ (release.providerCommit),
    providerTree: /** @type {string} */ (release.providerTree),
  })
}

/**
 * @param {unknown} value
 * @returns {Readonly<{
 *   report_kind: 'completed_use',
 *   score: number,
 *   skill_release_ref: string,
 *   actor_ref: string,
 *   issue?: Readonly<{ type: string, severity: string, issue_ref: string }>,
 * }>}
 */
export function validateSkillsTelemetry(value) {
  const report = snapshotPlain(value)
  rejectSensitive(report)
  rejectShape(report, TELEMETRY_COMPETING, TELEMETRY_CROSS_FIELDS, TELEMETRY_KEYS, 'skills telemetry')

  if (report.report_kind !== 'completed_use') {
    closed('skills_telemetry_invalid', 'report_kind must be completed_use', {
      classification: 'fail_closed',
      field: 'report_kind',
    })
  }
  if (!Number.isInteger(report.score) || /** @type {number} */ (report.score) < 0 || /** @type {number} */ (report.score) > 10) {
    closed('skills_telemetry_invalid', 'score must be an integer in 0..10', {
      classification: 'fail_closed',
      field: 'score',
    })
  }

  for (const field of ['skill_release_ref', 'actor_ref']) {
    if (typeof report[field] !== 'string') {
      closed('skills_reference_invalid', `skills telemetry reference is malformed: ${field}`, {
        classification: 'fail_closed',
        field,
      })
    }
    rejectLatestAlias(report[field], field)
    if (!OPAQUE.test(/** @type {string} */ (report[field]))) {
      closed('skills_reference_invalid', `skills telemetry reference is malformed: ${field}`, {
        classification: 'fail_closed',
        field,
      })
    }
  }

  if (report.score === 10 && report.issue !== undefined) {
    closed('skills_perfect_use_has_issue', 'score 10 use reports must not include an issue object', {
      classification: 'fail_closed',
      field: 'issue',
    })
  }

  /** @type {Readonly<{ type: string, severity: string, issue_ref: string }> | undefined} */
  let issue
  if (/** @type {number} */ (report.score) < 10) {
    const record = snapshotPlain(report.issue, 'skills_issue_required')
    rejectSensitive(record)
    rejectShape(record, TELEMETRY_COMPETING, new Set(), ISSUE_KEYS, 'skills telemetry issue')
    if (typeof record.type !== 'string' || !ISSUE_TYPES.has(record.type)) {
      closed('skills_issue_invalid', 'skills issue type is malformed', {
        classification: 'fail_closed',
        field: 'type',
      })
    }
    if (typeof record.severity !== 'string' || !ISSUE_SEVERITIES.has(record.severity)) {
      closed('skills_issue_invalid', 'skills issue severity is malformed', {
        classification: 'fail_closed',
        field: 'severity',
      })
    }
    if (typeof record.issue_ref !== 'string') {
      closed('skills_reference_invalid', 'skills issue_ref is malformed', {
        classification: 'fail_closed',
        field: 'issue_ref',
      })
    }
    rejectLatestAlias(record.issue_ref, 'issue_ref')
    if (!OPAQUE.test(record.issue_ref)) {
      closed('skills_reference_invalid', 'skills issue_ref is malformed', {
        classification: 'fail_closed',
        field: 'issue_ref',
      })
    }
    issue = Object.freeze({
      type: record.type,
      severity: record.severity,
      issue_ref: record.issue_ref,
    })
  }

  return Object.freeze({
    report_kind: 'completed_use',
    score: /** @type {number} */ (report.score),
    skill_release_ref: /** @type {string} */ (report.skill_release_ref),
    actor_ref: /** @type {string} */ (report.actor_ref),
    ...(issue ? { issue } : {}),
  })
}
