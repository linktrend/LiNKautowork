/**
 * Fail-closed LiNKlibraries revision-2 reference validator.
 *
 * Consumes `FROZEN_PROVIDERS.libraries` and `ConsumerContractError`. Accepts
 * only immutable provider/tree/catalogue/entry identities with well-formed
 * digests and `verified_cache` or `consumption` receipts. Snapshots own
 * enumerable plain data properties before any read; inherited, prototype,
 * accessor, getter, setter, and TOCTOU inputs are rejected. Validation and
 * the returned reference use only that immutable snapshot, including a
 * deep-frozen `catalogueRecord` when present. This module never pulls
 * remote objects, executes payloads, calls live providers, or replaces the
 * installed Wave-1 library client.
 */

import { fail } from './errors.mjs'
import { FROZEN_PROVIDERS } from './pins.mjs'

const GIT_SHA = /^(?!([a-f0-9])\1{39}$)[a-f0-9]{40}$/
const RAW_SHA256 = /^(?!([a-f0-9])\1{63}$)[a-f0-9]{64}$/
const ENTRY_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/
const SEMVER = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/
const RECEIPT_ID = /^[a-z0-9][a-z0-9._-]*$/
const RECEIPT_TYPES = new Set(['verified_cache', 'consumption'])
const LIFECYCLES = new Set([
  'draft',
  'qualified',
  'admitted',
  'selectable',
  'deprecated',
  'withdrawn',
  'quarantined',
  'rejected',
  'superseded',
])
const SELECTABLE_LIFECYCLES = new Set(['admitted', 'selectable'])
const SELECTABILITIES = new Set(['selectable', 'conditionally_selectable', 'non_selectable'])
const COMPATIBILITIES = new Set([
  'compatible',
  'conditionally_compatible',
  'incompatible',
  'unknown',
  'not_applicable',
])
const SENSITIVE = /(?:secret|password|token|authorization|private.?key|prompt|transcript|raw(?:_|$)|full.?content|body)/i
const ALLOWED_KEYS = new Set([
  'sourceCommitSha',
  'sourceTreeSha',
  'releaseSourceCommitSha',
  'releaseSourceTreeSha',
  'artifactTreeSha1',
  'entryId',
  'version',
  'releaseManifestSha256',
  'inventorySha256',
  'payloadSha256',
  'dependencyLockSha256',
  'catalogueSha256',
  'catalogueRecordsSha256',
  'catalogueRecord',
  'receiptType',
  'receiptId',
  'lifecycle',
  'selectability',
  'compatibility',
  'contentMode',
])
const CATALOGUE_RECORD_KEYS = new Set([
  'entryId',
  'version',
  'releaseManifestSha256',
  'payloadSha256',
  'inventorySha256',
  'artifactTreeSha1',
])
const REQUIRED_GIT = ['releaseSourceCommitSha', 'releaseSourceTreeSha', 'artifactTreeSha1']
const REQUIRED_DIGESTS = ['releaseManifestSha256', 'inventorySha256', 'payloadSha256', 'dependencyLockSha256']
const REQUIRED_CATALOGUE = ['catalogueSha256', 'catalogueRecordsSha256']

/**
 * @param {unknown} value
 * @param {string} [code]
 * @returns {Record<string, unknown>}
 */
function object(value, code = 'invalid_object') {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    fail(code, 'library reference must be a non-array object')
  }
  return /** @type {Record<string, unknown>} */ (value)
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
  if (depth > 5) fail('payload_too_deep', 'library reference exceeded bounded depth')
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
function snapshotOwnEnumerablePlainData(value, code = 'invalid_object', label = 'library reference', depth = 0) {
  if (depth > 5) fail('payload_too_deep', 'library reference exceeded bounded depth')
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
  if (depth > 5) fail('payload_too_deep', 'library reference exceeded bounded depth')
  for (const [key, item] of Object.entries(value)) {
    if (SENSITIVE.test(key)) {
      fail('sensitive_field', `library reference contains a sensitive field: ${key}`, { field: key })
    }
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      rejectSensitive(/** @type {Record<string, unknown>} */ (item), depth + 1)
    }
  }
}

/**
 * @param {Record<string, unknown>} value
 * @param {ReadonlySet<string>} allowed
 * @param {string} [scope]
 */
function rejectUnknown(value, allowed, scope = 'library reference') {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) {
      fail('unknown_field', `${scope} has an unknown field: ${key}`, { field: key })
    }
  }
}

/**
 * @param {unknown} value
 * @param {RegExp} pattern
 * @param {string} code
 * @param {string} field
 * @returns {string}
 */
function matchField(value, pattern, code, field) {
  if (typeof value !== 'string' || !pattern.test(value)) {
    fail(code, `library reference field is malformed: ${field}`, { field })
  }
  return value
}

/**
 * @param {Record<string, unknown>} value
 */
function assertCatalogueEntryBinding(value) {
  if (value.catalogueRecord === undefined) return
  const record = object(value.catalogueRecord)
  rejectUnknown(record, CATALOGUE_RECORD_KEYS, 'catalogue record')
  for (const field of ['entryId', 'version', 'releaseManifestSha256']) {
    if (record[field] === undefined) {
      fail('library_identity_invalid', `catalogue record is missing ${field}`, { field })
    }
    if (record[field] !== value[field]) {
      fail('library_tampered', `catalogue record ${field} does not match entry identity`, {
        classification: 'tamper',
        field,
        catalogueValue: record[field],
        entryValue: value[field],
      })
    }
  }
  for (const field of ['payloadSha256', 'inventorySha256', 'artifactTreeSha1']) {
    if (record[field] !== undefined && record[field] !== value[field]) {
      fail('library_tampered', `catalogue record ${field} does not match declared identity`, {
        classification: 'tamper',
        field,
        catalogueValue: record[field],
        entryValue: value[field],
      })
    }
  }
}

/**
 * @param {unknown} facts
 * @returns {Readonly<Record<string, unknown>>}
 */
export function validateLibraryReference(facts) {
  const value = snapshotOwnEnumerablePlainData(facts)
  rejectSensitive(value)
  rejectUnknown(value, ALLOWED_KEYS)

  const pin = FROZEN_PROVIDERS.libraries
  const sourceCommit = value.sourceCommitSha
  const sourceTree = value.sourceTreeSha
  if (typeof sourceCommit !== 'string' || sourceCommit === '' || typeof sourceTree !== 'string' || sourceTree === '') {
    fail('library_unavailable', 'library source identity is missing', {
      classification: 'unavailable',
      provider: 'libraries',
    })
  }
  if (!GIT_SHA.test(sourceCommit) || !GIT_SHA.test(sourceTree)) {
    fail('library_git_identity_invalid', 'library source identity is malformed', {
      classification: 'malformed',
      provider: 'libraries',
    })
  }
  if (sourceCommit !== pin.commit || sourceTree !== pin.tree) {
    fail('library_reference_not_frozen', 'library source identity is stale relative to the frozen pin', {
      classification: 'stale',
      provider: 'libraries',
      sourceCommitSha: sourceCommit,
      sourceTreeSha: sourceTree,
      frozenCommit: pin.commit,
      frozenTree: pin.tree,
    })
  }

  for (const field of REQUIRED_GIT) {
    matchField(value[field], GIT_SHA, 'library_git_identity_invalid', field)
  }
  for (const field of REQUIRED_DIGESTS) {
    matchField(value[field], RAW_SHA256, 'library_digest_invalid', field)
  }
  for (const field of REQUIRED_CATALOGUE) {
    matchField(value[field], RAW_SHA256, 'library_digest_invalid', field)
  }

  const entryId = matchField(value.entryId, ENTRY_ID, 'library_identity_invalid', 'entryId')
  if (entryId.length < 2 || entryId.length > 128) {
    fail('library_identity_invalid', 'library entryId length is out of range', { field: 'entryId' })
  }
  matchField(value.version, SEMVER, 'library_identity_invalid', 'version')
  assertCatalogueEntryBinding(value)

  if (!RECEIPT_TYPES.has(/** @type {string} */ (value.receiptType))) {
    fail('library_receipt_invalid', 'library receiptType must be verified_cache or consumption', {
      field: 'receiptType',
      receiptType: value.receiptType,
    })
  }
  matchField(value.receiptId, RECEIPT_ID, 'library_receipt_invalid', 'receiptId')

  if (value.lifecycle !== undefined) {
    if (typeof value.lifecycle !== 'string' || !LIFECYCLES.has(value.lifecycle)) {
      fail('library_identity_invalid', 'library lifecycle is malformed', { field: 'lifecycle' })
    }
    if (!SELECTABLE_LIFECYCLES.has(value.lifecycle)) {
      fail('library_not_selectable', 'library lifecycle is not selectable', {
        lifecycle: value.lifecycle,
      })
    }
  }
  if (value.selectability !== undefined) {
    if (typeof value.selectability !== 'string' || !SELECTABILITIES.has(value.selectability)) {
      fail('library_identity_invalid', 'library selectability is malformed', { field: 'selectability' })
    }
    if (value.selectability !== 'selectable') {
      fail('library_not_selectable', 'library selectability is not selectable', {
        selectability: value.selectability,
      })
    }
  }
  if (value.compatibility !== undefined) {
    if (typeof value.compatibility !== 'string' || !COMPATIBILITIES.has(value.compatibility)) {
      fail('library_identity_invalid', 'library compatibility is malformed', { field: 'compatibility' })
    }
    if (value.compatibility === 'incompatible' || value.compatibility === 'unknown') {
      fail('library_incompatible', 'library compatibility is fail-closed', {
        classification: 'incompatible',
        compatibility: value.compatibility,
      })
    }
    if (value.compatibility === 'conditionally_compatible') {
      fail('library_not_selectable', 'conditionally compatible library references are not selectable', {
        compatibility: value.compatibility,
      })
    }
  }
  if (value.contentMode === 'metadata_only') {
    fail('library_not_selectable', 'metadata-only library references are not selectable', {
      classification: 'denied',
      contentMode: value.contentMode,
    })
  }
  if (value.contentMode !== undefined) {
    fail('library_identity_invalid', 'library contentMode is malformed', { field: 'contentMode' })
  }

  return value
}
