/**
 * Shared modern MCP negotiation and optional OKF v0.2 mapping for Item 6.
 *
 * Providers that advertise MCP `2026-07-28` sessionless semantics must negotiate
 * only the modern era. Legacy or session `initialize` negotiation fails closed
 * with no silent downgrade. OKF `0.2` is an optional field mapping only — never
 * a second source of truth and never an authority or Brain execution bridge.
 *
 * Public options and OKF fieldMappings are snapshotted as own enumerable plain
 * data before allowlist checks, matching S1–S5 fail-closed doctrine.
 *
 * This module has no transport, credentials, Git write, Ledger, Gate mutation,
 * or MCP server runtime.
 */

import { fail } from './errors.mjs'

/** Modern sessionless MCP protocol version advertised by Brain / Skills. */
export const MCP_PROTOCOL_VERSION = '2026-07-28'

/** OKF mapping format and version accepted by this consumer. */
export const OKF_FORMAT = 'OKF'
export const OKF_VERSION = '0.2'

/**
 * Strict allowlist of negotiateMcp options keys. Unknown keys fail closed.
 * Present keys are still validated: session/initialize signals and non-modern
 * era values are refused (no silent downgrade).
 */
export const MCP_OPTION_KEYS = Object.freeze([
  'method',
  'session',
  'sessionRequired',
  'sessionReliance',
  'era',
  'sessionless',
])

const MCP_OPTION_KEY_SET = new Set(MCP_OPTION_KEYS)

const OKF_EXCHANGE_KINDS = Object.freeze([
  'canonical_knowledge',
  'canonical_projection',
  'task_state',
  'auth',
  'private_memory',
  'raw_capture',
  'binary',
])

const OKF_ELIGIBLE = new Set(['canonical_knowledge', 'canonical_projection'])

const OKF_KEYS = new Set([
  'format',
  'version',
  'exchangeKind',
  'applicable',
  'fieldMappings',
  'nonApplicabilityReason',
])

/**
 * Authority / execution vocabulary. Comparison uses conservative
 * canonicalization (lowercase + strip `_` / `-` / `.` / whitespace only) so
 * snake/kebab/dotted/spaced/camel variants match without collapsing unrelated
 * names such as `toolbox` or `executionPlan`.
 */
const AUTHORITY_BRIDGE_NAMES = Object.freeze([
  'authority',
  'executionAuthority',
  'execute',
  'execution',
  'tools',
  'tool',
  'toolRequest',
  'toolCalls',
  'skills_run',
  'grant',
  'capability',
  'permittedOperations',
])

/**
 * @param {string} name
 * @returns {string}
 */
function canonicalizeAuthorityToken(name) {
  return name.toLowerCase().replace(/[_\-.\s]+/g, '')
}

const AUTHORITY_BRIDGE_CANONICAL = new Set(AUTHORITY_BRIDGE_NAMES.map((name) => canonicalizeAuthorityToken(name)))

const SENSITIVE = /(?:secret|password|token|authorization|private.?key|prompt|transcript|conversation|raw(?:_|$)|full.?content|^body$)/i
const FIELD_NAME = /^[A-Za-z][A-Za-z0-9_.-]{0,63}$/
const REASON_MAX = 400
const FIELD_MAP_MAX = 32

/**
 * @param {unknown} value
 * @param {string} [code]
 * @returns {Record<string, unknown>}
 */
function object(value, code = 'invalid_object') {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    fail(code, 'expected a plain object', { classification: 'fail_closed' })
  }
  return /** @type {Record<string, unknown>} */ (value)
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
 * Copy own enumerable plain data properties before any semantic read.
 * Rejects inherited, prototype, accessor, getter, setter, and TOCTOU inputs.
 *
 * @param {unknown} value
 * @param {string} [code]
 * @param {string} [label]
 * @returns {Record<string, unknown>}
 */
function snapshotOwnEnumerablePlainData(value, code = 'invalid_object', label = 'input') {
  const record = object(value, code)
  const proto = Object.getPrototypeOf(record)
  const descriptors = Object.getOwnPropertyDescriptors(record)
  if (proto !== Object.prototype && proto !== null) {
    fail('inherited_property', `${label} must be a plain object`, {
      classification: 'fail_closed',
    })
  }
  if (proto === Object.prototype) {
    rejectInheritedEnumerable(proto, label)
  }
  const snapshot = Object.create(null)
  for (const key of Reflect.ownKeys(descriptors)) {
    const desc = descriptors[key]
    if (typeof key !== 'string') {
      if (desc.get !== undefined || desc.set !== undefined) {
        fail('accessor_property', `${label} has an accessor`, {
          classification: 'fail_closed',
        })
      }
      if (desc.enumerable) {
        fail('unknown_field', `${label} has a non-string property key`, {
          classification: 'fail_closed',
        })
      }
      continue
    }
    if (desc.get !== undefined || desc.set !== undefined) {
      fail('accessor_property', `${label} has an accessor: ${key}`, {
        classification: 'fail_closed',
        field: key,
      })
    }
    if (!desc.enumerable) continue
    snapshot[key] = desc.value
  }
  return snapshot
}

/**
 * @param {Record<string, unknown>} value
 * @param {Set<string>} allowed
 * @param {string} label
 */
function rejectUnknown(value, allowed, label) {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) {
      fail('unknown_field', `${label} contains unknown field ${key}`, {
        classification: 'fail_closed',
        field: key,
        surface: label,
      })
    }
  }
}

/**
 * @param {string} name
 * @returns {boolean}
 */
function isAuthorityBridgeName(name) {
  if (typeof name !== 'string') return true
  if (AUTHORITY_BRIDGE_CANONICAL.has(canonicalizeAuthorityToken(name))) return true
  return SENSITIVE.test(name)
}

/**
 * @param {Record<string, unknown>} value
 * @param {string} label
 */
function rejectAuthorityBridge(value, label) {
  for (const key of Object.keys(value)) {
    if (isAuthorityBridgeName(key)) {
      fail('okf_authority_bridge_forbidden', `${label} cannot carry authority or execution fields`, {
        classification: 'fail_closed',
        field: key,
        surface: label,
      })
    }
  }
}

/**
 * Any non-explicit-false value is treated as a session signal.
 * Strings/numbers/objects that encode session intent fail closed.
 *
 * @param {unknown} value
 * @returns {boolean}
 */
function isSessionSignal(value) {
  if (value === false) return false
  if (value === true) return true
  if (value === null || value === undefined) return false
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'bigint') return value !== 0n
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (normalized === '' || normalized === '0' || normalized === 'false' || normalized === 'no' || normalized === 'off') {
      return false
    }
    return true
  }
  return true
}

/**
 * @param {unknown} method
 * @returns {string}
 */
function normalizeMethod(method) {
  if (typeof method !== 'string' || method.trim() === '') {
    fail('mcp_negotiation_failed', 'MCP method must be a non-empty string when provided', {
      classification: 'fail_closed',
      field: 'method',
      method,
    })
  }
  return method.trim().toLowerCase()
}

/**
 * @param {string} method
 * @returns {boolean}
 */
function isInitializeMethod(method) {
  return method === 'initialize' || method.includes('initialize')
}

/**
 * @param {unknown} era
 * @returns {string}
 */
function normalizeEraOption(era) {
  if (typeof era !== 'string' || era.trim() === '') {
    fail('mcp_negotiation_failed', 'MCP options era must be a non-empty string when provided', {
      classification: 'fail_closed',
      field: 'era',
      era,
    })
  }
  return era.trim().toLowerCase()
}

/**
 * Negotiate the shared modern MCP boundary.
 *
 * Only `version === '2026-07-28'` with `era === 'modern'` succeeds. Options, when
 * present, are snapshotted as own enumerable plain data, then checked against
 * the strict allowlist. Legacy/session/`initialize` encodings fail closed.
 *
 * @param {unknown} version
 * @param {unknown} era
 * @param {unknown} [options]
 * @returns {typeof MCP_PROTOCOL_VERSION}
 */
export function negotiateMcp(version, era, options = undefined) {
  if (version !== MCP_PROTOCOL_VERSION || era !== 'modern') {
    fail('mcp_negotiation_failed', 'MCP negotiation requires 2026-07-28 modern sessionless', {
      classification: 'fail_closed',
      version,
      era,
      requiredVersion: MCP_PROTOCOL_VERSION,
      requiredEra: 'modern',
    })
  }

  if (options === undefined || options === null) {
    return MCP_PROTOCOL_VERSION
  }

  const opts = snapshotOwnEnumerablePlainData(options, 'mcp_options_invalid', 'mcp options')
  rejectUnknown(opts, MCP_OPTION_KEY_SET, 'mcp options')

  if (opts.method !== undefined) {
    const method = normalizeMethod(opts.method)
    if (isInitializeMethod(method)) {
      fail('mcp_negotiation_failed', 'legacy or session initialize negotiation is refused', {
        classification: 'fail_closed',
        field: 'method',
        method: opts.method,
      })
    }
  }

  for (const field of ['session', 'sessionRequired', 'sessionReliance']) {
    if (opts[field] !== undefined && isSessionSignal(opts[field])) {
      fail('mcp_negotiation_failed', 'legacy or session initialize negotiation is refused', {
        classification: 'fail_closed',
        field,
        [field]: opts[field],
      })
    }
  }

  if (opts.era !== undefined) {
    const optionEra = normalizeEraOption(opts.era)
    if (optionEra !== 'modern') {
      fail('mcp_negotiation_failed', 'legacy or session initialize negotiation is refused', {
        classification: 'fail_closed',
        field: 'era',
        era: opts.era,
      })
    }
  }

  if (opts.sessionless !== undefined && opts.sessionless !== true) {
    fail('mcp_negotiation_failed', 'MCP sessionless affirmation must be exactly true when provided', {
      classification: 'fail_closed',
      field: 'sessionless',
      sessionless: opts.sessionless,
    })
  }

  return MCP_PROTOCOL_VERSION
}

/**
 * Validate optional OKF v0.2 mapping. Returns a frozen mapping summary.
 *
 * Applicable only for canonical knowledge/projection exchange kinds. Never
 * grants Brain execution authority or overrides provider authority fields.
 * Authority/execution vocabulary in fieldMappings keys or values is rejected
 * after conservative separator-aware canonicalization.
 *
 * @param {unknown} value
 * @returns {Readonly<{ format: 'OKF', version: '0.2', exchangeKind: string, applicable: boolean }>}
 */
export function validateOkfMapping(value) {
  if (value === undefined) {
    fail('okf_mapping_required', 'OKF mapping value is required when validating OKF', {
      classification: 'fail_closed',
    })
  }

  const mapping = snapshotOwnEnumerablePlainData(value, 'okf_mapping_invalid', 'okf mapping')
  rejectAuthorityBridge(mapping, 'okf mapping')
  rejectUnknown(mapping, OKF_KEYS, 'okf mapping')

  if (mapping.format !== OKF_FORMAT || mapping.version !== OKF_VERSION) {
    fail('okf_version_invalid', 'OKF mapping must be format OKF version 0.2', {
      classification: 'fail_closed',
      format: mapping.format,
      version: mapping.version,
    })
  }

  if (typeof mapping.exchangeKind !== 'string' || !OKF_EXCHANGE_KINDS.includes(mapping.exchangeKind)) {
    fail('okf_exchange_kind_invalid', 'OKF exchangeKind is not a known v0.2 kind', {
      classification: 'fail_closed',
      field: 'exchangeKind',
      exchangeKind: mapping.exchangeKind,
    })
  }

  if (typeof mapping.applicable !== 'boolean') {
    fail('okf_applicability_invalid', 'OKF applicable must be a boolean', {
      classification: 'fail_closed',
      field: 'applicable',
    })
  }

  const eligible = OKF_ELIGIBLE.has(mapping.exchangeKind)
  if (mapping.applicable !== eligible) {
    fail('okf_applicability_invalid', 'OKF v0.2 applies only to canonical knowledge and projections', {
      classification: 'fail_closed',
      field: 'applicable',
      exchangeKind: mapping.exchangeKind,
      applicable: mapping.applicable,
    })
  }

  if (!eligible) {
    if (typeof mapping.nonApplicabilityReason !== 'string' || mapping.nonApplicabilityReason.trim() === '') {
      fail('okf_reason_required', 'non-applicable OKF exchange kinds require an explicit reason', {
        classification: 'fail_closed',
        field: 'nonApplicabilityReason',
      })
    }
    if (mapping.nonApplicabilityReason.length > REASON_MAX) {
      fail('okf_reason_invalid', 'nonApplicabilityReason exceeds the bounded size', {
        classification: 'fail_closed',
        field: 'nonApplicabilityReason',
      })
    }
  } else if (mapping.nonApplicabilityReason !== undefined) {
    fail('okf_reason_forbidden', 'eligible OKF exchange kinds must not carry a non-applicability reason', {
      classification: 'fail_closed',
      field: 'nonApplicabilityReason',
    })
  }

  if (mapping.fieldMappings !== undefined) {
    const fields = snapshotOwnEnumerablePlainData(
      mapping.fieldMappings,
      'okf_field_mappings_invalid',
      'okf fieldMappings',
    )
    rejectAuthorityBridge(fields, 'okf fieldMappings')
    const keys = Object.keys(fields)
    if (keys.length > FIELD_MAP_MAX) {
      fail('okf_field_mappings_invalid', 'OKF fieldMappings exceed the bounded size', {
        classification: 'fail_closed',
        field: 'fieldMappings',
      })
    }
    for (const key of keys) {
      const authorityKey = isAuthorityBridgeName(key)
      if (!FIELD_NAME.test(key) || SENSITIVE.test(key) || authorityKey) {
        fail(
          authorityKey ? 'okf_authority_bridge_forbidden' : 'okf_field_mappings_invalid',
          authorityKey
            ? 'OKF fieldMappings key cannot carry authority or execution vocabulary'
            : 'OKF fieldMappings key is invalid or sensitive',
          {
            classification: 'fail_closed',
            field: key,
            surface: 'okf fieldMappings',
          },
        )
      }
      const target = fields[key]
      if (typeof target !== 'string') {
        fail('okf_field_mappings_invalid', 'OKF fieldMappings value is invalid or sensitive', {
          classification: 'fail_closed',
          field: key,
          surface: 'okf fieldMappings',
        })
      }
      if (isAuthorityBridgeName(target)) {
        fail('okf_authority_bridge_forbidden', 'OKF fieldMappings value cannot carry authority or execution vocabulary', {
          classification: 'fail_closed',
          field: key,
          value: target,
          surface: 'okf fieldMappings',
        })
      }
      if (!FIELD_NAME.test(target) || SENSITIVE.test(target)) {
        fail('okf_field_mappings_invalid', 'OKF fieldMappings value is invalid or sensitive', {
          classification: 'fail_closed',
          field: key,
          surface: 'okf fieldMappings',
        })
      }
    }
  }

  return Object.freeze({
    format: OKF_FORMAT,
    version: OKF_VERSION,
    exchangeKind: /** @type {string} */ (mapping.exchangeKind),
    applicable: /** @type {boolean} */ (mapping.applicable),
  })
}
