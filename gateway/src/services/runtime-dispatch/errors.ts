/** Fail-closed runtime-dispatch error whose category is safe to return from a route. */
export class RuntimeDispatchError extends Error {
  constructor(
    readonly category:
      | 'conflict'
      | 'forbidden'
      | 'blocked'
      | 'invalid_state'
      | 'not_found'
      | 'invalid_callback'
      | 'hold'
      | 'unavailable'
      | 'rejected',
    message: string,
  ) {
    super(message);
  }
}

/** Maps a runtime-dispatch error category to an HTTP status without leaking internals. */
export function runtimeDispatchStatus(category: RuntimeDispatchError['category']): number {
  if (category === 'not_found') return 404;
  if (category === 'conflict') return 409;
  if (category === 'blocked' || category === 'hold' || category === 'unavailable') return 503;
  if (category === 'forbidden' || category === 'rejected') return 403;
  return 400;
}
