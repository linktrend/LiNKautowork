/**
 * Canonical provider/runtime registry for the pre-installed runtime boundary.
 *
 * This registry contains only public contract metadata. It is the single
 * source for provider identity, operation allowlists, timeout/retry policy, and
 * redaction policy. No entry grants execution authority.
 */

import { fail } from './errors.mjs'
import { FROZEN_PROVIDERS } from './pins.mjs'

export const PROVIDER_REGISTRY_VERSION = 'provider-registry/v1'

const provider = (id, contractVersion, tools) => ({
  id,
  ownerRepository: FROZEN_PROVIDERS[id].repository,
  contractVersion,
  providerCommit: FROZEN_PROVIDERS[id].commit,
  providerTree: FROZEN_PROVIDERS[id].tree,
  executionAuthority: 'none',
  transport: 'https-json',
  timeouts: Object.freeze({ requestMs: 15000, totalMs: 30000 }),
  retryPolicy: Object.freeze({ maxAttempts: 2, retryableStatuses: Object.freeze([408, 429, 500, 502, 503, 504]) }),
  redactionPolicy: Object.freeze({
    allowRawBody: false,
    sensitiveFields: Object.freeze(['secret', 'password', 'token', 'authorization', 'private_key', 'prompt', 'transcript', 'raw_body']),
  }),
  tools: Object.freeze(tools.map((tool) => Object.freeze({
    ...tool,
    provider: id,
    executionAuthority: 'none',
  }))),
})

const read = (name, path, capability) => ({
  name,
  method: 'GET',
  path,
  capability,
  readOnly: true,
})

const write = (name, path, capability) => ({
  name,
  method: 'POST',
  path,
  capability,
  readOnly: false,
})

const REGISTRY_KEYS = new Set(['schemaVersion', 'providers'])
const PROVIDER_KEYS = new Set([
  'id',
  'ownerRepository',
  'contractVersion',
  'providerCommit',
  'providerTree',
  'executionAuthority',
  'transport',
  'timeouts',
  'retryPolicy',
  'redactionPolicy',
  'tools',
])
const TOOL_KEYS = new Set(['name', 'method', 'path', 'capability', 'readOnly', 'provider', 'executionAuthority'])
const TIMEOUT_KEYS = new Set(['requestMs', 'totalMs'])
const RETRY_KEYS = new Set(['maxAttempts', 'retryableStatuses'])
const REDACTION_KEYS = new Set(['allowRawBody', 'sensitiveFields'])

export const PROVIDER_REGISTRY = Object.freeze({
  schemaVersion: PROVIDER_REGISTRY_VERSION,
  providers: Object.freeze({
    platform: provider('platform', 'platform.auth-claims/1.1.0', [
      read('platform.identity.resolve', '/v1/identity', 'platform.identity.resolve'),
      read('platform.capabilities.read', '/v1/capabilities', 'platform.capabilities.read'),
    ]),
    brain: provider('brain', '2.0.0', [
      write('brain.projection.search', '/v2/projections/search', 'brain.projection.read'),
      read('brain.projection.read', '/v2/projections/{projectionRef}', 'brain.projection.read'),
      write('brain.handoff.create', '/v2/handoffs', 'brain.handoff.create'),
      read('brain.handoff.read', '/v2/handoffs/{handoffRef}', 'brain.handoff.read'),
      write('brain.handoff.accept', '/v2/handoffs/{handoffRef}/accept', 'brain.handoff.accept'),
      read('brain.handoff.status', '/v2/handoffs/{handoffRef}/status', 'brain.handoff.read'),
      write('brain.handoff.close', '/v2/handoffs/{handoffRef}/close', 'brain.handoff.close'),
    ]),
    skills: provider('skills', 'skills.api.v0.2', [
      read('skills.release.search', '/v2/releases/search', 'skills.release.read'),
      read('skills.release.read', '/v2/releases/{skillId}/{version}', 'skills.release.read'),
      read('skills.release.fragment.read', '/v2/releases/{skillId}/{version}/fragments/{fragmentLevel}', 'skills.release.read'),
      write('skills.telemetry.submit', '/v2/telemetry', 'skills.telemetry.write'),
    ]),
    libraries: provider('libraries', 'libraries.revision-2', [
      read('libraries.catalogue.search', '/v2/catalogue/search', 'libraries.catalogue.read'),
      read('libraries.entry.read', '/v2/entries/{entryId}/{version}', 'libraries.entry.read'),
    ]),
    autowork: provider('autowork', '2026-08-13.v1', [
      write('autowork.request.submit', '/v1/requests', 'autowork.request.submit'),
      read('autowork.status.read', '/v1/requests/{requestId}/status', 'autowork.status.read'),
      read('autowork.handoff.read', '/v1/requests/{requestId}/handoff', 'autowork.handoff.read'),
      read('autowork.receipt.read', '/v1/requests/{requestId}/receipt', 'autowork.receipt.read'),
    ]),
  }),
})

function closed(code, message, details = {}) {
  fail(code, message, { classification: 'fail_closed', ...details })
}

function plain(value, label) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) closed('registry_invalid', `${label} must be an object`)
  const proto = Object.getPrototypeOf(value)
  if (proto !== Object.prototype && proto !== null) closed('registry_prototype_forbidden', `${label} must be plain`)
  return value
}

function exactKeys(value, allowed, label) {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) closed('registry_unknown_field', `${label} contains an unknown field`, { field: key })
  }
}

function freeze(value) {
  if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value
  for (const child of Object.values(value)) freeze(child)
  return Object.freeze(value)
}

/**
 * Validate a registry before it is used to authorize transport operations.
 *
 * @param {unknown} value
 * @returns {Readonly<Record<string, unknown>>}
 */
export function validateProviderRegistry(value) {
  const registry = plain(value, 'registry')
  exactKeys(registry, REGISTRY_KEYS, 'registry')
  if (registry.schemaVersion !== PROVIDER_REGISTRY_VERSION) closed('registry_contract_incompatible', 'registry schemaVersion is incompatible')
  const providers = plain(registry.providers, 'registry providers')
  const expectedIds = Object.keys(FROZEN_PROVIDERS).sort()
  if (JSON.stringify(Object.keys(providers).sort()) !== JSON.stringify(expectedIds)) {
    closed('registry_provider_set_invalid', 'registry must contain exactly the five frozen providers')
  }
  for (const [id, entry] of Object.entries(providers)) {
    const item = plain(entry, `${id} provider`)
    exactKeys(item, PROVIDER_KEYS, `${id} provider`)
    if (item.id !== id || item.ownerRepository !== FROZEN_PROVIDERS[id].repository) closed('registry_identity_invalid', 'registry provider identity is invalid', { provider: id })
    if (item.providerCommit !== FROZEN_PROVIDERS[id].commit || item.providerTree !== FROZEN_PROVIDERS[id].tree) closed('registry_pin_invalid', 'registry provider pin is stale', { provider: id })
    if (item.executionAuthority !== 'none') closed('registry_execution_authority_forbidden', 'provider execution authority must remain none', { provider: id })
    if (!item.redactionPolicy || item.redactionPolicy.allowRawBody !== false) closed('registry_redaction_invalid', 'raw provider bodies are forbidden', { provider: id })
    exactKeys(plain(item.timeouts, `${id} timeouts`), TIMEOUT_KEYS, `${id} timeouts`)
    if (!item.timeouts || !Number.isInteger(item.timeouts.requestMs) || !Number.isInteger(item.timeouts.totalMs)) closed('registry_timeout_invalid', 'provider timeouts are invalid', { provider: id })
    exactKeys(plain(item.retryPolicy, `${id} retry policy`), RETRY_KEYS, `${id} retry policy`)
    if (!item.retryPolicy || item.retryPolicy.maxAttempts !== 2) closed('registry_retry_invalid', 'provider retry policy must be bounded to two attempts', { provider: id })
    exactKeys(plain(item.redactionPolicy, `${id} redaction policy`), REDACTION_KEYS, `${id} redaction policy`)
    if (!Array.isArray(item.tools) || item.tools.length === 0) closed('registry_tools_invalid', 'provider must define tools', { provider: id })
    for (const tool of item.tools) {
      exactKeys(plain(tool, `${id} tool`), TOOL_KEYS, `${id} tool`)
      if (tool.provider !== id || tool.executionAuthority !== 'none' || typeof tool.name !== 'string' || typeof tool.path !== 'string') {
        closed('registry_tool_invalid', 'provider tool is invalid or grants authority', { provider: id })
      }
    }
  }
  return freeze(registry)
}

export function getProviderDefinition(providerId) {
  if (typeof providerId !== 'string' || !PROVIDER_REGISTRY.providers[providerId]) {
    closed('provider_unknown', 'provider is not registered', { provider: providerId })
  }
  return PROVIDER_REGISTRY.providers[providerId]
}

export function getProviderTool(providerId, operation) {
  const definition = getProviderDefinition(providerId)
  const tool = definition.tools.find((candidate) => candidate.name === operation)
  if (!tool) closed('operation_not_allowed', 'provider operation is not registered', { provider: providerId, operation })
  return tool
}
