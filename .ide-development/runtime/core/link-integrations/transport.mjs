/**
 * Authenticated, bounded provider transport.
 *
 * Transport owns only HTTP mechanics. Provider modules own contract validation.
 * Credentials are resolved per request, used only in the Authorization header,
 * and never included in errors or diagnostics.
 */

import { ConsumerContractError } from './errors.mjs'
import { redactError } from './redaction.mjs'
import { getProviderDefinition, getProviderTool, PROVIDER_REGISTRY } from './registry.mjs'

const MAX_BODY_BYTES = 1_000_000
const MAX_TIMEOUT_MS = 60_000
const SENSITIVE_KEY = /(?:secret|password|token|authorization|credential|private.?key|prompt|transcript|conversation|raw(?:_|$)|full.?content|^body$)/i

export class ProviderTransportError extends ConsumerContractError {
  constructor(code, message, details = {}) {
    super(code, message, details)
    this.name = 'ProviderTransportError'
  }
}

function failTransport(code, message, details = {}) {
  throw new ProviderTransportError(code, message, { classification: 'fail_closed', ...details })
}

function assertEndpoint(endpoint) {
  if (typeof endpoint !== 'string') failTransport('transport_config_invalid', 'provider endpoint must be a string')
  let url
  try {
    url = new URL(endpoint)
  } catch {
    failTransport('transport_config_invalid', 'provider endpoint is not a URL')
  }
  if (url.protocol !== 'https:' || url.username || url.password || url.hash || url.search) {
    failTransport('transport_config_invalid', 'provider endpoint must be https without embedded credentials or queries')
  }
  return url.origin
}

function assertSafeData(value, depth = 0) {
  if (depth > 5) failTransport('payload_too_deep', 'provider request exceeded bounded depth')
  if (typeof value === 'string') {
    if (value.length > 4096) failTransport('payload_too_large', 'provider request string exceeded bounded size')
    return value
  }
  if (value === null || typeof value !== 'object') return value
  if (Array.isArray(value)) {
    if (value.length > 32) failTransport('payload_too_large', 'provider request array exceeded bounded size')
    const descriptors = Object.getOwnPropertyDescriptors(value)
    const copy = []
    for (const key of Reflect.ownKeys(descriptors)) {
      if (key === 'length') continue
      const descriptor = descriptors[key]
      if (typeof key !== 'string' || !/^(0|[1-9]\d*)$/.test(key)) {
        if (descriptor.enumerable) failTransport('unknown_field', 'provider request array has a non-index field')
      }
    }
    for (let index = 0; index < value.length; index += 1) {
      const descriptor = descriptors[String(index)]
      if (!descriptor || descriptor.get !== undefined || descriptor.set !== undefined) {
        failTransport('accessor_property', 'provider request arrays must contain data properties')
      }
      copy.push(assertSafeData(descriptor.value, depth + 1))
    }
    return copy
  }
  const proto = Object.getPrototypeOf(value)
  if (proto !== Object.prototype && proto !== null) failTransport('inherited_property', 'provider request objects must be plain')
  const descriptors = Object.getOwnPropertyDescriptors(value)
  const copy = {}
  for (const key of Reflect.ownKeys(descriptors)) {
    const descriptor = descriptors[key]
    if (typeof key !== 'string') {
      if (descriptor.enumerable) failTransport('unknown_field', 'provider request has a non-string key')
      continue
    }
    if (!descriptor.enumerable) continue
    if (descriptor.get !== undefined || descriptor.set !== undefined) {
      failTransport('accessor_property', 'provider request objects must contain data properties', { field: key })
    }
    if (SENSITIVE_KEY.test(key)) failTransport('sensitive_field', 'provider request contains a sensitive field', { field: key })
    copy[key] = assertSafeData(descriptor.value, depth + 1)
  }
  return copy
}

function requestPath(path, operation) {
  if (path === undefined) return getProviderTool(operation.split('.')[0], operation).path
  if (typeof path !== 'string' || !path.startsWith('/') || path.includes('..') || path.includes('\\') || path.includes('{')) {
    failTransport('transport_path_invalid', 'provider request path is invalid')
  }
  return path
}

function classifyStatus(status, provider) {
  if (status === 401 || status === 403) return ['provider_denied', 'provider denied the authenticated operation', 'denied']
  if (status === 409 || status === 422) return ['provider_incompatible', 'provider rejected an incompatible contract', 'incompatible']
  if (status === 400) return ['provider_malformed', 'provider rejected a malformed request', 'fail_closed']
  if (status === 404) return ['provider_unavailable', 'provider operation is unavailable', 'unavailable']
  if (status === 408 || status === 429 || status >= 500) return ['provider_unavailable', 'provider runtime is unavailable', 'unavailable']
  return ['provider_http_error', 'provider returned an unexpected HTTP status', 'fail_closed']
}

async function parseResponse(response) {
  if (response.status === 204) return null
  if (typeof response.text !== 'function') failTransport('provider_malformed', 'provider response has no readable body')
  const text = await response.text()
  if (text.length > MAX_BODY_BYTES) failTransport('provider_response_too_large', 'provider response exceeded bounded size')
  if (text === '') return null
  try {
    return JSON.parse(text)
  } catch {
    failTransport('provider_malformed', 'provider response was not valid JSON')
  }
}

function retryable(error) {
  return error instanceof ProviderTransportError && ['provider_timeout', 'provider_unavailable'].includes(error.code)
}

/**
 * Create an authenticated transport for one registered provider.
 *
 * @param {{
 *   provider: string,
 *   endpoint: string,
 *   getAccessToken: (provider: string, operation: string) => string|Promise<string>,
 *   fetchImpl?: typeof globalThis.fetch,
 *   timeoutMs?: number,
 *   sleep?: (ms: number) => Promise<void>,
 * }} options
 */
export function createAuthenticatedTransport(options) {
  if (!options || typeof options !== 'object') failTransport('transport_config_invalid', 'transport options are required')
  const provider = options.provider
  const definition = getProviderDefinition(provider)
  const endpoint = assertEndpoint(options.endpoint)
  if (typeof options.getAccessToken !== 'function') failTransport('credential_unavailable', 'provider credential resolver is unavailable', { provider })
  const fetchImpl = options.fetchImpl ?? globalThis.fetch
  if (typeof fetchImpl !== 'function') failTransport('transport_unavailable', 'fetch implementation is unavailable', { provider })
  const timeoutMs = options.timeoutMs ?? definition.timeouts.requestMs
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > MAX_TIMEOUT_MS) {
    failTransport('transport_timeout_invalid', 'provider timeout is outside the bounded range', { provider })
  }
  const sleep = options.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)))

  return Object.freeze({
    provider,
    /**
     * @param {string} operation
     * @param {{ path?: string, method?: string, body?: unknown, signal?: AbortSignal }} [request]
     */
    async request(operation, request = {}) {
      const tool = getProviderTool(provider, operation)
      if (!request || typeof request !== 'object' || Array.isArray(request)) {
        failTransport('transport_request_invalid', 'provider request options are invalid')
      }
      const method = request.method ?? tool.method
      if (method !== tool.method) failTransport('operation_method_invalid', 'provider operation method is fixed by the registry', { provider, operation })
      const path = requestPath(request.path, operation)
      const body = request.body === undefined ? undefined : assertSafeData(request.body)
      let token
      try {
        token = await options.getAccessToken(provider, operation)
      } catch (error) {
        const safe = redactError(error)
        failTransport('credential_unavailable', 'provider credential resolver failed', {
          provider,
          cause: safe.code ?? safe.name,
        })
      }
      if (typeof token !== 'string' || token.length < 1 || token.length > 4096) {
        failTransport('credential_unavailable', 'provider credential resolver returned no usable credential', { provider })
      }
      const headers = new Headers({
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      })
      if (body !== undefined) headers.set('Content-Type', 'application/json')
      const url = `${endpoint}${path}`
      const attempts = definition.retryPolicy.maxAttempts
      for (let attempt = 1; attempt <= attempts; attempt += 1) {
        const controller = new AbortController()
        let timedOut = false
        const timeout = setTimeout(() => {
          timedOut = true
          controller.abort()
        }, timeoutMs)
        const callerSignal = request.signal
        const abortCaller = () => controller.abort()
        callerSignal?.addEventListener('abort', abortCaller, { once: true })
        try {
          const response = await fetchImpl(url, {
            method,
            headers,
            signal: controller.signal,
            ...(body === undefined ? {} : { body: JSON.stringify(body) }),
          })
          clearTimeout(timeout)
          callerSignal?.removeEventListener('abort', abortCaller)
          if (!response || typeof response.status !== 'number') failTransport('provider_malformed', 'provider response is invalid', { provider })
          if (response.status >= 200 && response.status < 300) return parseResponse(response)
          const [code, message, classification] = classifyStatus(response.status, provider)
          throw new ProviderTransportError(code, message, { classification, provider, status: response.status })
        } catch (error) {
          clearTimeout(timeout)
          callerSignal?.removeEventListener('abort', abortCaller)
          if (callerSignal?.aborted) {
            failTransport('provider_cancelled', 'provider request was cancelled', { provider })
          }
          if (timedOut) {
            if (attempt < attempts) {
              await sleep(0)
              continue
            }
            failTransport('provider_timeout', 'provider request exceeded its timeout', { provider, timeoutMs })
          }
          if (error instanceof ProviderTransportError) {
            if (retryable(error) && attempt < attempts) {
              await sleep(0)
              continue
            }
            throw error
          }
          if (attempt < attempts) {
            await sleep(0)
            continue
          }
          const safe = redactError(error)
          failTransport('provider_unavailable', 'provider request could not be completed', {
            provider,
            cause: safe.code ?? safe.name,
          })
        }
      }
      failTransport('provider_unavailable', 'provider request could not be completed', { provider })
    },
  })
}

/**
 * Build transports for all configured providers.
 *
 * @param {{providers: Record<string, {endpoint: string, credentialRef: string}>}} config
 * @param {{getAccessToken: (provider: string, operation: string) => string|Promise<string>, fetchImpl?: typeof globalThis.fetch, sleep?: (ms: number) => Promise<void>}} options
 */
export function createTransports(config, options = {}) {
  const transports = {}
  for (const [provider, binding] of Object.entries(config.providers)) {
    if (binding.availability === 'unavailable' || binding.availability === 'incompatible') {
      const code = binding.availability === 'unavailable' ? 'provider_unavailable' : 'provider_incompatible'
      const classification = binding.availability === 'unavailable' ? 'unavailable' : 'incompatible'
      transports[provider] = Object.freeze({
        provider,
        async request() {
          throw new ProviderTransportError(code, `provider ${binding.availability}`, {
            provider,
            classification,
          })
        },
      })
      continue
    }
    transports[provider] = createAuthenticatedTransport({
      provider,
      endpoint: binding.endpoint,
      getAccessToken: options.getAccessToken,
      fetchImpl: options.fetchImpl,
      sleep: options.sleep,
    })
  }
  return Object.freeze(transports)
}

export { MAX_BODY_BYTES, PROVIDER_REGISTRY }
export const createProviderTransport = createAuthenticatedTransport
