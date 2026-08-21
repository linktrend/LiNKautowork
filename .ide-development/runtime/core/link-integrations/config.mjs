/**
 * Non-secret provider runtime configuration.
 *
 * Configuration contains endpoint and secret-reference names only. Secret
 * values are supplied by the caller's credential resolver at request time and
 * are never accepted, stored, or returned by this module.
 */

import { fail } from './errors.mjs'
import { PROVIDER_REGISTRY } from './registry.mjs'

export const PROVIDER_RUNTIME_CONFIG_VERSION = 'provider-runtime-config/v1'

const ROOT_KEYS = new Set(['schemaVersion', 'consumerRepository', 'environment', 'providers'])
const PROVIDER_KEYS = new Set(['endpoint', 'credentialRef', 'enabledCapabilities', 'availability', 'contractVersion'])
const PROVIDERS = new Set(Object.keys(PROVIDER_REGISTRY.providers))
const ENVIRONMENTS = new Set(['test', 'development', 'staging', 'production'])
const AVAILABILITY = new Set(['available', 'unavailable', 'incompatible'])
const REPOSITORY = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/
const CREDENTIAL_REF = /^[A-Z][A-Z0-9_]{2,127}$/
const SENSITIVE_KEY = /(?:secret|password|token|authorization|private.?key|credential.?value|raw.?body)/i

function closed(code, message, details = {}) {
  fail(code, message, { classification: 'fail_closed', ...details })
}

function assertPlainObject(value, code = 'config_invalid_object') {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) closed(code, 'configuration must be a plain object')
  const proto = Object.getPrototypeOf(value)
  if (proto !== Object.prototype && proto !== null) closed('config_prototype_forbidden', 'configuration prototypes are not accepted')
  const descriptors = Object.getOwnPropertyDescriptors(value)
  for (const [key, descriptor] of Object.entries(descriptors)) {
    if (descriptor.get !== undefined || descriptor.set !== undefined) {
      closed('config_accessor_forbidden', 'configuration accessors are not accepted', { field: key })
    }
  }
  for (const key of Reflect.ownKeys(descriptors)) {
    if (typeof key !== 'string' || descriptors[key].enumerable === false) {
      if (typeof key !== 'string' && descriptors[key].enumerable) closed('config_unknown_field', 'configuration has a non-string key')
      continue
    }
    if (SENSITIVE_KEY.test(key)) closed('config_sensitive_field', 'configuration contains a sensitive field', { field: key })
  }
  return value
}

function exactKeys(value, allowed, label) {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) closed('config_unknown_field', `${label} contains an unknown field`, { field: key })
  }
}

function deepFreeze(value) {
  if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value
  for (const child of Object.values(value)) deepFreeze(child)
  return Object.freeze(value)
}

function providerConfig(providerId, value) {
  const provider = assertPlainObject(value)
  exactKeys(provider, PROVIDER_KEYS, `${providerId} provider`)
  if (typeof provider.endpoint !== 'string') closed('config_endpoint_invalid', 'provider endpoint must be a string', { provider: providerId })
  let endpoint
  try {
    endpoint = new URL(provider.endpoint)
  } catch {
    closed('config_endpoint_invalid', 'provider endpoint is not a valid URL', { provider: providerId })
  }
  if (endpoint.protocol !== 'https:' || endpoint.username || endpoint.password || endpoint.hash) {
    closed('config_endpoint_invalid', 'provider endpoint must be an https URL without embedded credentials', { provider: providerId })
  }
  if (typeof provider.credentialRef !== 'string' || !CREDENTIAL_REF.test(provider.credentialRef)) {
    closed('config_credential_ref_invalid', 'provider credentialRef must name an external secret', { provider: providerId })
  }
  if (!Array.isArray(provider.enabledCapabilities) || provider.enabledCapabilities.length < 1 || provider.enabledCapabilities.length > 32) {
    closed('config_capabilities_invalid', 'provider enabledCapabilities must be a bounded non-empty array', { provider: providerId })
  }
  if (!provider.enabledCapabilities.every((item) => typeof item === 'string' && item.length > 0 && item.length < 128)) {
    closed('config_capabilities_invalid', 'provider capabilities must be non-empty strings', { provider: providerId })
  }
  const availability = provider.availability ?? 'available'
  if (!AVAILABILITY.has(availability)) closed('config_availability_invalid', 'provider availability is invalid', { provider: providerId })
  const expectedVersion = PROVIDER_REGISTRY.providers[providerId].contractVersion
  if (provider.contractVersion !== undefined && provider.contractVersion !== expectedVersion) {
    closed('config_contract_incompatible', 'provider contractVersion is incompatible', { provider: providerId })
  }
  return {
    endpoint: `${endpoint.origin}${endpoint.pathname.replace(/\/+$/, '')}`,
    credentialRef: provider.credentialRef,
    enabledCapabilities: [...new Set(provider.enabledCapabilities)],
    availability,
    contractVersion: expectedVersion,
  }
}

/**
 * Validate and return a deeply frozen runtime configuration.
 *
 * @param {unknown} value
 * @returns {Readonly<Record<string, unknown>>}
 */
export function validateProviderRuntimeConfig(value) {
  const config = assertPlainObject(value)
  exactKeys(config, ROOT_KEYS, 'runtime config')
  if (config.schemaVersion !== PROVIDER_RUNTIME_CONFIG_VERSION) {
    closed('config_contract_incompatible', 'runtime config schemaVersion is incompatible')
  }
  if (typeof config.consumerRepository !== 'string' || !REPOSITORY.test(config.consumerRepository)) {
    closed('config_repository_invalid', 'consumerRepository must be owner/repository')
  }
  if (typeof config.environment !== 'string' || !ENVIRONMENTS.has(config.environment)) {
    closed('config_environment_invalid', 'runtime environment is invalid')
  }
  const providers = assertPlainObject(config.providers)
  for (const key of Object.keys(providers)) {
    if (!PROVIDERS.has(key)) closed('config_provider_unknown', 'runtime config names an unknown provider', { provider: key })
  }
  for (const providerId of PROVIDERS) {
    if (!Object.hasOwn(providers, providerId)) {
      closed('config_provider_missing', 'runtime config is missing a provider binding', { provider: providerId })
    }
  }
  const accepted = {
    schemaVersion: PROVIDER_RUNTIME_CONFIG_VERSION,
    consumerRepository: config.consumerRepository,
    environment: config.environment,
    providers: Object.fromEntries([...PROVIDERS].map((providerId) => [providerId, providerConfig(providerId, providers[providerId])])),
  }
  return deepFreeze(accepted)
}

export const validateRuntimeConfig = validateProviderRuntimeConfig
