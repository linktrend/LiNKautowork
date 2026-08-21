/**
 * Non-skill LiNKskills lock loader for Codex and Cursor.
 *
 * Progressive fragment retrieval and bounded telemetry only. This module does
 * not execute skills, call Skills HTTP, load a full remote pack, or remove
 * physical copies. Physical removal stays blocked until dual-app proof.
 */

import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { fail } from './errors.mjs'
import { validateSkillsTelemetry } from './skills.mjs'

export const SKILLS_LOCK_CONTRACT_VERSION = 'skills.lock.v0.2'
export const SKILLS_LOCK_PACKET = 'PKT-03'
export const V24_ROLLBACK_COMMIT = '004bd5faa1e14ee100a018e16dcb049f0fb2d8eb'
export const V24_ROLLBACK_TREE = '6c55220132cc7e9a1baef06f8c147ee9ac9431e7'
export const ACTIVE_COPY_COUNT = 88

const HERE = dirname(fileURLToPath(import.meta.url))
const DEFAULT_LOCK = join(HERE, 'skills-lock.json')
const GIT_SHA = /^[a-f0-9]{40}$/
const SHA256 = /^sha256:[a-f0-9]{64}$/
const PLATFORMS = new Set(['codex', 'cursor'])
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
const ADDRESSING = Object.freeze({
  0: 'discovery',
  1: 'discovery',
  2: 'validation',
  3: 'execution',
  4: 'execution',
  5: 'execution',
  6: 'execution',
})

/**
 * @param {string} code
 * @param {string} message
 * @param {{ classification: string, field?: string, provider?: string }} details
 * @returns {never}
 */
function closed(code, message, details) {
  fail(code, message, {
    classification: details.classification,
    ...(details.field ? { field: details.field } : {}),
    ...(details.provider ? { provider: details.provider } : {}),
  })
}

/**
 * @param {unknown} value
 * @returns {boolean}
 */
function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value) && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null)
}

/**
 * @param {string} [lockPath]
 * @returns {Readonly<Record<string, unknown>>}
 */
export function loadSkillsLock(lockPath = DEFAULT_LOCK) {
  if (typeof lockPath !== 'string' || lockPath === '' || !existsSync(lockPath)) {
    closed('skills_lock_unavailable', 'skills lock is not present', {
      classification: 'unavailable',
      provider: 'skills',
    })
  }
  let parsed
  try {
    parsed = JSON.parse(readFileSync(lockPath, 'utf8'))
  } catch {
    closed('skills_lock_invalid', 'skills lock is malformed JSON', { classification: 'fail_closed' })
  }
  if (!isPlainObject(parsed)) {
    closed('skills_lock_invalid', 'skills lock must be a plain object', { classification: 'fail_closed' })
  }
  if (parsed.contractVersion !== SKILLS_LOCK_CONTRACT_VERSION) {
    closed('skills_contract_incompatible', 'skills lock contractVersion mismatch', {
      classification: 'fail_closed',
      field: 'contractVersion',
    })
  }
  const provider = parsed.provider
  if (!isPlainObject(provider) || provider.repository !== 'linktrend/LiNKskills') {
    closed('skills_lock_invalid', 'skills lock provider identity is malformed', { classification: 'fail_closed' })
  }
  if (typeof provider.commit !== 'string' || typeof provider.tree !== 'string' || !GIT_SHA.test(provider.commit) || !GIT_SHA.test(provider.tree)) {
    closed('skills_pin_invalid', 'skills lock provider pin is malformed', {
      classification: 'fail_closed',
      provider: 'skills',
    })
  }
  if (!Array.isArray(parsed.copies) || parsed.copies.length !== ACTIVE_COPY_COUNT) {
    closed('skills_lock_invalid', 'skills lock must inventory exactly 88 active copies', {
      classification: 'fail_closed',
      field: 'copies',
    })
  }
  if (!Array.isArray(parsed.skills) || parsed.skills.length === 0) {
    closed('skills_lock_invalid', 'skills lock has no unique skill rows', {
      classification: 'fail_closed',
      field: 'skills',
    })
  }
  for (const row of parsed.skills) {
    if (!isPlainObject(row) || typeof row.skillId !== 'string') {
      closed('skills_lock_invalid', 'skills lock skill row is malformed', { classification: 'fail_closed' })
    }
    if (row.decision !== 'qualified' && row.decision !== 'retired') {
      closed('skills_lock_invalid', `skill ${row.skillId} is neither qualified nor retired`, {
        classification: 'fail_closed',
        field: 'decision',
      })
    }
    if (row.decision === 'qualified' && row.authority === 'linkskills') {
      for (const field of ['releaseHash', 'bundleHash', 'manifestHash']) {
        if (typeof row[field] !== 'string' || !SHA256.test(row[field])) {
          closed('skills_digest_invalid', `skills lock digest is malformed: ${field}`, {
            classification: 'fail_closed',
            field,
          })
        }
      }
    }
  }
  if (parsed.rollbackCommit !== V24_ROLLBACK_COMMIT || parsed.rollbackTree !== V24_ROLLBACK_TREE) {
    closed('skills_lock_invalid', 'atomic v2.4 rollback identity is missing from the lock', {
      classification: 'fail_closed',
      field: 'rollbackCommit',
    })
  }
  return Object.freeze(parsed)
}

/**
 * @param {Readonly<Record<string, unknown>>} lock
 * @param {string} skillId
 */
function skillRow(lock, skillId) {
  const rows = /** @type {Array<Record<string, unknown>>} */ (lock.skills)
  const row = rows.find((item) => item.skillId === skillId)
  if (!row) {
    closed('skills_not_in_lock', `skill is not in the ISS-04 lock: ${skillId}`, {
      classification: 'denied',
      field: 'skillId',
    })
  }
  return row
}

/**
 * Retrieve a bounded lock fragment for Codex or Cursor.
 *
 * Local SKILL.md copies are never used as a provider substitute. Required
 * GitOps adapters may load from the lock when the provider is unavailable.
 *
 * @param {{
 *   platform: 'codex' | 'cursor',
 *   skillId: string,
 *   fragmentLevel?: number,
 *   providerStatus: string,
 *   lockPath?: string,
 *   lock?: Readonly<Record<string, unknown>>,
 * }} input
 */
export function retrieveSkillFragment(input) {
  if (!isPlainObject(input)) {
    closed('invalid_object', 'retrieveSkillFragment requires a plain object', { classification: 'fail_closed' })
  }
  if (!PLATFORMS.has(input.platform)) {
    closed('skills_platform_invalid', 'platform must be codex or cursor', {
      classification: 'fail_closed',
      field: 'platform',
    })
  }
  const lock = input.lock || loadSkillsLock(input.lockPath)
  const row = skillRow(lock, input.skillId)
  const fragmentLevel = input.fragmentLevel === undefined ? 0 : input.fragmentLevel
  if (!Number.isInteger(fragmentLevel) || fragmentLevel < 0 || fragmentLevel > 6) {
    closed('skills_fragment_invalid', 'fragmentLevel must be an integer in 0..6', {
      classification: 'fail_closed',
      field: 'fragmentLevel',
    })
  }

  const providerStatus = input.providerStatus
  if (typeof providerStatus !== 'string' || providerStatus === '') {
    closed('skills_availability_invalid', 'providerStatus is malformed', {
      classification: 'fail_closed',
      field: 'providerStatus',
    })
  }

  if (row.decision === 'retired') {
    closed('skills_not_qualified', 'skills qualification is not qualified', {
      classification: 'denied',
      field: 'qualification',
    })
  }

  const requiresProvider = row.authority === 'linkskills'
  if (requiresProvider && (providerStatus !== 'available' || UNAVAILABLE.has(providerStatus))) {
    closed('skills_release_unavailable', 'skills provider is not available', {
      classification: 'unavailable',
      provider: 'skills',
      field: 'availability',
    })
  }

  const addressing = ADDRESSING[/** @type {0|1|2|3|4|5|6} */ (fragmentLevel)]
  const fragments = Array.isArray(row.fragments) ? row.fragments : []
  const matched = fragments.find((item) => isPlainObject(item) && item.fragmentLevel === fragmentLevel)
  const digest = matched && typeof matched.digest === 'string'
    ? matched.digest
    : typeof row.entrypointDigest === 'string'
      ? row.entrypointDigest
      : typeof row.releaseHash === 'string'
        ? row.releaseHash
        : `sha256:${createHash('sha256').update(`${row.skillId}:${fragmentLevel}`).digest('hex')}`

  return Object.freeze({
    platform: input.platform,
    skillId: row.skillId,
    version: row.version,
    fragmentLevel,
    addressing,
    digest,
    authority: row.authority,
    source: 'skills-lock',
    providerCommit: /** @type {Record<string, string>} */ (lock.provider).commit,
    providerTree: /** @type {Record<string, string>} */ (lock.provider).tree,
  })
}

/**
 * @param {unknown} value
 */
export function recordSkillsTelemetry(value) {
  return validateSkillsTelemetry(value)
}

/**
 * Removal stays blocked until Codex and Cursor retrieval are both proven.
 * This function never deletes files.
 *
 * @param {{
 *   dualAppProof?: { codex?: unknown, cursor?: unknown },
 *   lockPath?: string,
 *   lock?: Readonly<Record<string, unknown>>,
 * }} [input]
 */
export function planPhysicalSkillRemoval(input = {}) {
  const lock = input.lock || loadSkillsLock(input.lockPath)
  const proof = isPlainObject(input.dualAppProof) ? input.dualAppProof : lock.dualAppProof
  const codex = isPlainObject(proof) ? proof.codex : undefined
  const cursor = isPlainObject(proof) ? proof.cursor : undefined
  const authorized = codex === true && cursor === true && lock.physicalRemovalAuthorized === true
  if (!authorized) {
    return Object.freeze({
      authorized: false,
      reason: 'dual_app_proof_hold',
      rollbackCommit: lock.rollbackCommit,
      copiesRetained: ACTIVE_COPY_COUNT,
      dualAppProof: Object.freeze({
        codex: codex === true ? true : 'HOLD',
        cursor: cursor === true ? true : 'HOLD',
      }),
    })
  }
  closed('skills_removal_not_armed', 'physical skill removal is not authorized on this packet', {
    classification: 'fail_closed',
    field: 'physicalRemovalAuthorized',
  })
}
