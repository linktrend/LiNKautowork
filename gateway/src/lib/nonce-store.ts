export class NonceStore {
  private readonly ttlMs: number;
  private readonly seen = new Map<string, number>();

  constructor(ttlSeconds: number) {
    this.ttlMs = ttlSeconds * 1000;
  }

  isReplay(nonce: string, nowMs = Date.now()): boolean {
    this.cleanup(nowMs);
    if (this.seen.has(nonce)) return true;
    this.seen.set(nonce, nowMs + this.ttlMs);
    return false;
  }

  private cleanup(nowMs: number): void {
    for (const [nonce, expiresAt] of this.seen) {
      if (expiresAt <= nowMs) {
        this.seen.delete(nonce);
      }
    }
  }
}
