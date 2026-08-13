/** Deterministic provider-run transition guard; persistence is owned by AW-02. */
export const terminalProviderStates = new Set(['succeeded', 'failed', 'expired', 'cancelled', 'timed_out', 'rejected', 'quarantined', 'unavailable', 'contract_incompatible']);
const allowed: Record<string, string[]> = { accepted: ['queued', 'rejected', 'expired', 'cancelled', 'blocked'], queued: ['running', 'cancelled', 'expired', 'blocked'], running: ['succeeded', 'failed', 'cancelled', 'timed_out', 'blocked'], failed: ['queued'], blocked: ['queued', 'cancelled'] };
/** Validates CAS, terminal state, idempotency, and kill-switch rules before a durable transition. */
export function transitionProviderRun({ current, next, expectedVersion, actualVersion, existingFingerprint, incomingFingerprint, killSwitch = false }: { current: string; next: string; expectedVersion: number; actualVersion: number; existingFingerprint: string; incomingFingerprint: string; killSwitch?: boolean }): { replay: boolean } {
  if (existingFingerprint !== incomingFingerprint) throw new Error('idempotency conflict');
  if (expectedVersion !== actualVersion) throw new Error('expected version conflict');
  if (terminalProviderStates.has(current)) throw new Error('terminal state');
  if (killSwitch && next === 'running') throw new Error('kill switch blocks new starts');
  if (!allowed[current]?.includes(next)) throw new Error('invalid provider transition');
  return { replay: current === next };
}
