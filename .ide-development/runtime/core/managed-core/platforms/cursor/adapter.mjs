/**
 * Cursor application adapter.
 *
 * Cursor and Codex intentionally share the exact tool contract. This wrapper
 * fixes the application identity while keeping the implementation and profile
 * allowlists in one place.
 */

import {
  APPLICATION_ADAPTER_CONTRACT_VERSION,
  PROFILE_ALLOWLISTS,
  SUPPORTED_APPLICATIONS,
  SUPPORTED_PROFILES,
  TOOL_NAMES,
  createApplicationAdapter as createSharedApplicationAdapter,
} from '../codex/adapter.mjs'

export {
  APPLICATION_ADAPTER_CONTRACT_VERSION,
  PROFILE_ALLOWLISTS,
  SUPPORTED_APPLICATIONS,
  SUPPORTED_PROFILES,
  TOOL_NAMES,
}

export function createApplicationAdapter(options = {}) {
  return createSharedApplicationAdapter({ ...options, application: 'cursor' })
}
