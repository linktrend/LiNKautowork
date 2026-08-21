/**
 * Cursor non-skill skills loader. Packaged adjacent to skills-lock.json.
 * Implementation lives in the IDE consumer module until dual-app proof.
 */
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  ACTIVE_COPY_COUNT,
  SKILLS_LOCK_CONTRACT_VERSION,
  SKILLS_LOCK_PACKET,
  V24_ROLLBACK_COMMIT,
  V24_ROLLBACK_TREE,
  loadSkillsLock as loadCanonicalLock,
  planPhysicalSkillRemoval as planCanonicalRemoval,
  recordSkillsTelemetry,
  retrieveSkillFragment as retrieveCanonicalFragment,
} from '../../../link-integrations/skills-loader.mjs'

const LOCK = join(dirname(fileURLToPath(import.meta.url)), 'skills-lock.json')

export {
  ACTIVE_COPY_COUNT,
  SKILLS_LOCK_CONTRACT_VERSION,
  SKILLS_LOCK_PACKET,
  V24_ROLLBACK_COMMIT,
  V24_ROLLBACK_TREE,
  recordSkillsTelemetry,
}

export function loadSkillsLock(lockPath = LOCK) {
  return loadCanonicalLock(lockPath)
}

export function retrieveSkillFragment(input) {
  return retrieveCanonicalFragment({ ...input, lockPath: input.lockPath || LOCK })
}

export function planPhysicalSkillRemoval(input = {}) {
  return planCanonicalRemoval({ ...input, lockPath: input.lockPath || LOCK })
}
