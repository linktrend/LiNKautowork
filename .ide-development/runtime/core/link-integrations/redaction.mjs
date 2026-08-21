/**
 * Bounded redaction for provider diagnostics.
 *
 * This is deliberately independent of transport and provider validators so every
 * runtime error path can sanitize values before they are retained or displayed.
 * It never returns credentials, raw provider bodies, prompts, or transcripts.
 */

const MAX_DEPTH = 5
const MAX_KEYS = 64
const MAX_ITEMS = 32
const MAX_STRING = 2048
const SENSITIVE_KEY = /(?:secret|password|token|authorization|credential|private.?key|prompt|transcript|conversation|raw(?:_|$)|full.?content|^body$)/i

function boundedString(value) {
  if (value.length <= MAX_STRING) return value
  return `${value.slice(0, MAX_STRING - 11)}[TRUNCATED]`
}

function redactValue(value, depth, seen) {
  if (typeof value === 'string') return boundedString(value)
  if (value === null || typeof value === 'number' || typeof value === 'boolean') return value
  if (typeof value === 'bigint') return `${value}n`
  if (typeof value === 'undefined') return undefined
  if (typeof value === 'function' || typeof value === 'symbol') return '[OMITTED]'
  if (depth >= MAX_DEPTH) return '[TRUNCATED]'
  if (seen.has(value)) return '[CIRCULAR]'
  seen.add(value)

  if (Array.isArray(value)) {
    const descriptors = Object.getOwnPropertyDescriptors(value)
    const result = []
    for (let index = 0; index < Math.min(value.length, MAX_ITEMS); index += 1) {
      const descriptor = descriptors[String(index)]
      result.push(
        !descriptor || descriptor.get !== undefined || descriptor.set !== undefined
          ? '[REDACTED]'
          : redactValue(descriptor.value, depth + 1, seen),
      )
    }
    if (value.length > MAX_ITEMS) result.push('[TRUNCATED]')
    seen.delete(value)
    return result
  }

  const result = {}
  const descriptors = Object.getOwnPropertyDescriptors(value)
  const keys = Object.keys(descriptors).filter((key) => descriptors[key].enumerable)
  for (const key of keys.slice(0, MAX_KEYS)) {
    const descriptor = descriptors[key]
    result[key] = SENSITIVE_KEY.test(key) || descriptor.get !== undefined || descriptor.set !== undefined
      ? '[REDACTED]'
      : redactValue(descriptor.value, depth + 1, seen)
  }
  if (keys.length > MAX_KEYS) result._truncated = true
  seen.delete(value)
  return result
}

/**
 * Return a bounded, JSON-safe diagnostic projection.
 *
 * @param {unknown} value
 * @returns {unknown}
 */
export function redact(value) {
  return redactValue(value, 0, new WeakSet())
}

/**
 * Redact an Error without retaining its arbitrary enumerable properties.
 *
 * @param {unknown} error
 * @returns {{ name: string, message: string, code?: string }}
 */
export function redactError(error) {
  if (!error || typeof error !== 'object') {
    return { name: 'Error', message: boundedString(String(error)) }
  }
  const candidate = /** @type {Record<string, unknown>} */ (error)
  const result = {
    name: typeof candidate.name === 'string' ? boundedString(candidate.name) : 'Error',
    message: typeof candidate.message === 'string' ? boundedString(candidate.message) : 'provider request failed',
  }
  if (typeof candidate.code === 'string') result.code = candidate.code
  return result
}

export const REDACTION_LIMITS = Object.freeze({
  maxDepth: MAX_DEPTH,
  maxKeys: MAX_KEYS,
  maxItems: MAX_ITEMS,
  maxString: MAX_STRING,
})
