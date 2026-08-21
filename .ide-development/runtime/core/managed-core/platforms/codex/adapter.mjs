/**
 * Shared Codex/Cursor application adapter contract.
 *
 * The application surface is deliberately smaller than the provider clients:
 * profiles select an explicit tool allowlist, inputs are copied before dispatch,
 * provider errors keep stable codes but lose arbitrary details, and every call
 * has a bounded timeout. The adapter never receives credentials or raw bodies.
 */

import { ConsumerContractError } from '../../../link-integrations/errors.mjs'

export const APPLICATION_ADAPTER_CONTRACT_VERSION = 'application-adapter/v1'
export const SUPPORTED_APPLICATIONS = Object.freeze(['codex', 'cursor'])
export const SUPPORTED_PROFILES = Object.freeze(['canary', 'release'])

const PROFILE_ALLOWLISTS = Object.freeze({
  canary: Object.freeze([
    'platform.identity.resolve',
    'brain.projection.read',
    'skills.release.read',
    'brain.handoff.create',
  ]),
  release: Object.freeze([
    'platform.identity.resolve',
    'platform.capabilities.read',
    'brain.projection.search',
    'brain.projection.read',
    'brain.handoff.create',
    'brain.handoff.read',
    'brain.handoff.accept',
    'brain.handoff.status',
    'brain.handoff.close',
    'skills.release.search',
    'skills.release.read',
    'skills.release.fragment.read',
  ]),
})

const TOOL_DEFINITIONS = Object.freeze({
  'platform.identity.resolve': {
    provider: 'platform',
    input: (value) => record(value, 'platform.identity.resolve'),
    invoke: (clients, value) => clients.platform.resolveIdentity(value),
  },
  'platform.capabilities.read': {
    provider: 'platform',
    input: (value) => emptyRecord(value, 'platform.capabilities.read'),
    invoke: (clients) => clients.platform.readCapabilities(),
  },
  'brain.projection.search': {
    provider: 'brain',
    input: (value) => record(value, 'brain.projection.search'),
    invoke: (clients, value) => clients.brain.search(value),
  },
  'brain.projection.read': {
    provider: 'brain',
    input: (value) => requiredRef(value, 'projectionRef', 'brain.projection.read'),
    invoke: (clients, value) => clients.brain.read(value.projectionRef),
  },
  'brain.handoff.create': {
    provider: 'brain',
    input: (value) => record(value, 'brain.handoff.create'),
    invoke: (clients, value) => clients.brain.createHandoff(value),
  },
  'brain.handoff.read': {
    provider: 'brain',
    input: (value) => requiredRef(value, 'handoffRef', 'brain.handoff.read'),
    invoke: (clients, value) => clients.brain.readHandoff(value.handoffRef),
  },
  'brain.handoff.accept': {
    provider: 'brain',
    input: (value) => requiredRef(value, 'handoffRef', 'brain.handoff.accept'),
    invoke: (clients, value) => clients.brain.acceptHandoff(value.handoffRef),
  },
  'brain.handoff.status': {
    provider: 'brain',
    input: (value) => requiredRef(value, 'handoffRef', 'brain.handoff.status'),
    invoke: (clients, value) => clients.brain.handoffStatus(value.handoffRef),
  },
  'brain.handoff.close': {
    provider: 'brain',
    input: (value) => requiredRef(value, 'handoffRef', 'brain.handoff.close'),
    invoke: (clients, value) => clients.brain.closeHandoff(value.handoffRef),
  },
  'skills.release.search': {
    provider: 'skills',
    input: (value) => record(value, 'skills.release.search'),
    invoke: (clients, value) => clients.skills.search(value),
  },
  'skills.release.read': {
    provider: 'skills',
    input: (value) => requiredObject(value, 'release', 'skills.release.read'),
    invoke: (clients, value) => clients.skills.read(value.release),
  },
  'skills.release.fragment.read': {
    provider: 'skills',
    input: (value) => requiredFragment(value, 'skills.release.fragment.read'),
    invoke: (clients, value) => clients.skills.readFragment(value.release, value.fragmentLevel),
  },
})

const TOOL_NAMES = Object.freeze(Object.keys(TOOL_DEFINITIONS))
const SENSITIVE_KEY = /(?:secret|password|token|authorization|credential|private.?key|prompt|transcript|conversation|raw(?:_|$)|full.?content|^body$)/i
const MAX_DEPTH = 5
const MAX_STRING = 4096

function fail(code, message, details = {}) {
  throw new ConsumerContractError(code, message, {
    classification: 'fail_closed',
    ...details,
  })
}

function isPlainObject(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const prototype = Object.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}

function snapshot(value, label, depth = 0) {
  if (depth > MAX_DEPTH) fail('tool_input_invalid', `${label} is too deep`)
  if (typeof value === 'string') {
    if (value.length > MAX_STRING) fail('tool_input_invalid', `${label} is too large`)
    return value
  }
  if (value === null || typeof value !== 'object') return value
  if (Array.isArray(value)) {
    if (value.length > 32) fail('tool_input_invalid', `${label} has too many items`)
    return Object.freeze(value.map((item) => snapshot(item, label, depth + 1)))
  }
  if (!isPlainObject(value)) fail('tool_input_invalid', `${label} must be a plain object`)
  const descriptors = Object.getOwnPropertyDescriptors(value)
  const result = {}
  for (const [key, descriptor] of Object.entries(descriptors)) {
    if (!descriptor.enumerable) continue
    if (descriptor.get !== undefined || descriptor.set !== undefined) {
      fail('tool_input_invalid', `${label} cannot contain accessors`, { field: key })
    }
    if (SENSITIVE_KEY.test(key)) fail('tool_input_invalid', `${label} contains a sensitive field`, { field: key })
    result[key] = snapshot(descriptor.value, `${label}.${key}`, depth + 1)
  }
  return Object.freeze(result)
}

function record(value, tool) {
  return snapshot(value ?? {}, `${tool} input`)
}

function emptyRecord(value, tool) {
  const result = record(value, tool)
  if (Object.keys(result).length > 0) fail('tool_input_invalid', `${tool} does not accept input`)
  return result
}

function exactRecord(value, keys, tool) {
  const result = record(value, tool)
  for (const key of Object.keys(result)) {
    if (!keys.includes(key)) fail('tool_input_invalid', `${tool} has an unknown input field`, { field: key })
  }
  return result
}

function requiredRef(value, key, tool) {
  const result = exactRecord(value, [key], tool)
  if (typeof result[key] !== 'string' || result[key].length === 0 || result[key].length > 256) {
    fail('tool_input_invalid', `${tool} requires a bounded ${key}`)
  }
  return result
}

function requiredObject(value, key, tool) {
  const result = exactRecord(value, [key], tool)
  if (!isPlainObject(result[key])) fail('tool_input_invalid', `${tool} requires a ${key} object`)
  return result
}

function requiredFragment(value, tool) {
  const result = exactRecord(value, ['release', 'fragmentLevel'], tool)
  if (!isPlainObject(result.release)) fail('tool_input_invalid', `${tool} requires a release object`)
  if (!Number.isInteger(result.fragmentLevel) || result.fragmentLevel < 0 || result.fragmentLevel > 6) {
    fail('tool_input_invalid', `${tool} requires a fragmentLevel in 0..6`)
  }
  return result
}

function safeProviderDetails(details) {
  if (!details || typeof details !== 'object') return {}
  const safe = {}
  for (const key of ['classification', 'provider', 'field', 'status']) {
    if (typeof details[key] === 'string' || typeof details[key] === 'number') safe[key] = details[key]
  }
  return safe
}

function callWithTimeout(operation, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new ConsumerContractError(
      'tool_timeout',
      'application tool exceeded its timeout',
      { classification: 'unavailable', timeoutMs },
    )), timeoutMs)
    Promise.resolve()
      .then(operation)
      .then(
        (value) => {
          clearTimeout(timer)
          resolve(value)
        },
        (error) => {
          clearTimeout(timer)
          reject(error)
        },
      )
  })
}

function validateOptions(options) {
  if (!isPlainObject(options)) fail('adapter_config_invalid', 'adapter options must be a plain object')
  const application = options.application ?? 'codex'
  const profile = options.profile ?? 'canary'
  if (!SUPPORTED_APPLICATIONS.includes(application)) {
    fail('adapter_application_invalid', 'application is not supported', { application })
  }
  if (!SUPPORTED_PROFILES.includes(profile)) {
    fail('adapter_profile_invalid', 'profile is not supported', { profile })
  }
  if (!isPlainObject(options.clients)) fail('adapter_clients_invalid', 'provider clients are required')
  if (!Number.isInteger(options.timeoutMs ?? 15000) || (options.timeoutMs ?? 15000) < 1 || (options.timeoutMs ?? 15000) > 60000) {
    fail('adapter_timeout_invalid', 'adapter timeout is outside the bounded range')
  }
  return Object.freeze({
    application,
    profile,
    clients: options.clients,
    timeoutMs: options.timeoutMs ?? 15000,
  })
}

export function createApplicationAdapter(options = {}) {
  const config = validateOptions(options)
  const allowed = new Set(PROFILE_ALLOWLISTS[config.profile])
  const metadata = Object.freeze(PROFILE_ALLOWLISTS[config.profile]
    .filter((name) => TOOL_DEFINITIONS[name])
    .map((name) => Object.freeze({
      name,
      provider: TOOL_DEFINITIONS[name].provider,
      timeoutMs: config.timeoutMs,
    })))

  const adapter = {
    contractVersion: APPLICATION_ADAPTER_CONTRACT_VERSION,
    application: config.application,
    profile: config.profile,
    listTools() {
      return metadata.map((tool) => tool.name)
    },
    listToolDefinitions() {
      return metadata
    },
    async callTool(name, input = {}) {
      if (typeof name !== 'string' || !allowed.has(name) || !TOOL_DEFINITIONS[name]) {
        fail('tool_not_allowed', 'tool is not enabled for this application profile', {
          application: config.application,
          profile: config.profile,
          tool: typeof name === 'string' ? name : 'invalid',
        })
      }
      const definition = TOOL_DEFINITIONS[name]
      const acceptedInput = definition.input(input)
      try {
        return await callWithTimeout(
          () => definition.invoke(config.clients, acceptedInput),
          config.timeoutMs,
        )
      } catch (error) {
        if (error instanceof ConsumerContractError) {
          throw new ConsumerContractError(error.code, 'application tool failed', {
            ...safeProviderDetails(error.details),
            application: config.application,
            profile: config.profile,
            tool: name,
          })
        }
        throw new ConsumerContractError('adapter_tool_failed', 'application tool failed', {
          classification: 'fail_closed',
          application: config.application,
          profile: config.profile,
          tool: name,
        })
      }
    },
  }
  adapter.getToolNames = adapter.listTools
  adapter.invokeTool = adapter.callTool
  return Object.freeze(adapter)
}

export { PROFILE_ALLOWLISTS, TOOL_NAMES }
