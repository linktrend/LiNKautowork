/** Deterministic notification admission; delivery transport is intentionally deferred. */
export function admitProviderNotification({ seen, recipientAuthorized, suppressed, quiet, deliveredInWindow, limit, body }: { seen: Set<string>; recipientAuthorized: boolean; suppressed: boolean; quiet: boolean; deliveredInWindow: number; limit: number; body: string }): 'accepted' | 'duplicate' | 'suppressed' | 'forbidden' | 'rate_limited' {
  const key = body.replace(/\s+/g, ' ').trim(); if (seen.has(key)) return 'duplicate'; if (!recipientAuthorized) return 'forbidden'; if (suppressed || quiet) return 'suppressed'; if (deliveredInWindow >= limit) return 'rate_limited'; seen.add(key); return 'accepted';
}
/** Produces a bounded redacted delivery receipt without message content. */
export function notificationReceipt(id: string, state: 'delivered' | 'failed', attempt: number) { return { id, state, attempt, redacted: true }; }
