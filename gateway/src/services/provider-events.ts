/** In-memory deterministic event/outbox guards; AW-02 owns durable storage. */
export function acceptProviderEvent(seen: Set<string>, eventId: string): boolean { if (seen.has(eventId)) return false; seen.add(eventId); return true; }
/** Returns a bounded ordered page and next cursor without exposing event payloads. */
export function pageProviderEvents<T extends { id: string }>(events: T[], cursor: string | undefined, limit = 100): { events: T[]; nextCursor: string | undefined } { const start = cursor ? Math.max(0, events.findIndex((event) => event.id === cursor) + 1) : 0; const page = events.slice(start, start + Math.min(limit, 100)); return { events: page, nextCursor: page.length === Math.min(limit, 100) ? page.at(-1)?.id : undefined }; }
/** Event delivery retries are isolated from job retries; exhausted delivery enters DLQ. */
export function advanceOutbox(state: 'pending' | 'delivered' | 'dlq', deliveryAttempts: number, jobAttempts: number): 'pending' | 'delivered' | 'dlq' { if (state !== 'pending') return state; if (jobAttempts < 0) throw new Error('invalid job attempts'); return deliveryAttempts >= 3 ? 'dlq' : 'pending'; }
