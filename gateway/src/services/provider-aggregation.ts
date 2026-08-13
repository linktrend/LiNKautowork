/** Classifies cached provider observations without claiming authoritative current state. */
export function aggregationStatus({ observedAt, ttlMs, complete, available, now = Date.now() }: { observedAt: number; ttlMs: number; complete: boolean; available: boolean; now?: number }): 'fresh' | 'stale' | 'incomplete' | 'unavailable' { if (!available) return 'unavailable'; if (!complete) return 'incomplete'; return now - observedAt > ttlMs ? 'stale' : 'fresh'; }
/** Returns a bounded retry-after value for provider quota/backoff handling. */
export function aggregationBackoff(attempt: number): number { return Math.min(60_000, 1_000 * 2 ** Math.max(0, attempt)); }
