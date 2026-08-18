import { describe, expect, it } from 'vitest';
import { NonceStore } from '../src/lib/nonce-store.js';
import { computeLinkSignature, verifyLinkSignature } from '../src/lib/signing.js';

describe('verifyLinkSignature', () => {
  it('accepts a valid signed request', () => {
    const nowMs = Date.UTC(2026, 2, 19, 0, 0, 0);
    const timestamp = String(Math.floor(nowMs / 1000));
    const nonce = 'nonce-1';
    const rawBody = JSON.stringify({ hello: 'world' });
    const signature = computeLinkSignature('ltfx.signing.test.ts.secret.67.0.v1', timestamp, nonce, rawBody);

    const result = verifyLinkSignature({
      secret: 'ltfx.signing.test.ts.secret.67.0.v1',
      timestamp,
      nonce,
      signature,
      rawBody,
      replayWindowSeconds: 300,
      nonceStore: new NonceStore(300),
      nowMs,
    });

    expect(result).toEqual({ ok: true });
  });

  it('rejects stale timestamps', () => {
    const nowMs = Date.UTC(2026, 2, 19, 0, 10, 0);
    const oldTimestamp = String(Math.floor((nowMs - 301_000) / 1000));
    const nonce = 'nonce-2';
    const rawBody = '{}';

    const result = verifyLinkSignature({
      secret: 'ltfx.signing.test.ts.secret.67.0.v1',
      timestamp: oldTimestamp,
      nonce,
      signature: computeLinkSignature('ltfx.signing.test.ts.secret.67.0.v1', oldTimestamp, nonce, rawBody),
      rawBody,
      replayWindowSeconds: 300,
      nonceStore: new NonceStore(300),
      nowMs,
    });

    expect(result).toEqual({ ok: false, reason: 'timestamp outside replay window' });
  });

  it('rejects replayed nonces', () => {
    const nowMs = Date.UTC(2026, 2, 19, 0, 0, 0);
    const timestamp = String(Math.floor(nowMs / 1000));
    const nonce = 'nonce-3';
    const rawBody = '{}';
    const signature = computeLinkSignature('ltfx.signing.test.ts.secret.67.0.v1', timestamp, nonce, rawBody);
    const nonceStore = new NonceStore(300);

    const first = verifyLinkSignature({
      secret: 'ltfx.signing.test.ts.secret.67.0.v1',
      timestamp,
      nonce,
      signature,
      rawBody,
      replayWindowSeconds: 300,
      nonceStore,
      nowMs,
    });

    const second = verifyLinkSignature({
      secret: 'ltfx.signing.test.ts.secret.67.0.v1',
      timestamp,
      nonce,
      signature,
      rawBody,
      replayWindowSeconds: 300,
      nonceStore,
      nowMs,
    });

    expect(first).toEqual({ ok: true });
    expect(second).toEqual({ ok: false, reason: 'replayed nonce' });
  });
});
