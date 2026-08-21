/**
 * Typed fail-closed error for the IDE Development five-provider consumer.
 *
 * `code` is the stable machine-readable identifier. Callers must branch on
 * `code`, not on message text. The same failure class must keep the same code
 * (NFR-I6-08). This module has no transport, credentials, Git write, Ledger,
 * or Gate mutation APIs.
 */

export class ConsumerContractError extends Error {
  /**
   * @param {string} code Stable non-empty failure code.
   * @param {string} [message]
   * @param {Record<string, unknown>} [details]
   */
  constructor(code, message = code, details = {}) {
    if (typeof code !== 'string' || code.trim() === '') {
      throw new TypeError('ConsumerContractError requires a stable non-empty code')
    }
    super(typeof message === 'string' && message ? message : code)
    this.name = 'ConsumerContractError'
    Object.defineProperty(this, 'code', {
      value: code,
      enumerable: true,
      writable: false,
      configurable: false,
    })
    Object.defineProperty(this, 'details', {
      value: Object.freeze({ ...details }),
      enumerable: true,
      writable: false,
      configurable: false,
    })
  }
}

/**
 * Throw a ConsumerContractError with a stable code.
 *
 * @param {string} code
 * @param {string} [message]
 * @param {Record<string, unknown>} [details]
 * @returns {never}
 */
export function fail(code, message, details) {
  throw new ConsumerContractError(code, message, details)
}
