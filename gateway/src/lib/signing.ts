import { createHmac, timingSafeEqual } from 'node:crypto';
import { NonceStore } from './nonce-store.js';

export function computeLinkSignature(secret: string, timestamp: string, nonce: string, rawBody: string): string {
  const payload = `${timestamp}.${nonce}.${rawBody}`;
  const digest = createHmac('sha256', secret).update(payload).digest('hex');
  return `sha256=${digest}`;
}

function normalizeSignature(signature: string): string {
  return signature.startsWith('sha256=') ? signature : `sha256=${signature}`;
}

export function verifyLinkSignature(args: {
  secret: string;
  timestamp: string;
  nonce: string;
  signature: string;
  rawBody: string;
  replayWindowSeconds: number;
  nonceStore: NonceStore;
  nowMs?: number;
}): { ok: true } | { ok: false; reason: string } {
  const nowMs = args.nowMs ?? Date.now();
  const timestampMs = Number(args.timestamp) * 1000;
  if (Number.isNaN(timestampMs)) {
    return { ok: false, reason: 'invalid timestamp' };
  }

  const age = Math.abs(nowMs - timestampMs);
  if (age > args.replayWindowSeconds * 1000) {
    return { ok: false, reason: 'timestamp outside replay window' };
  }

  if (args.nonceStore.isReplay(args.nonce, nowMs)) {
    return { ok: false, reason: 'replayed nonce' };
  }

  const expected = computeLinkSignature(args.secret, args.timestamp, args.nonce, args.rawBody);
  const provided = normalizeSignature(args.signature);

  const expectedBuf = Buffer.from(expected);
  const providedBuf = Buffer.from(provided);
  if (expectedBuf.length !== providedBuf.length) {
    return { ok: false, reason: 'invalid signature length' };
  }

  if (!timingSafeEqual(expectedBuf, providedBuf)) {
    return { ok: false, reason: 'signature mismatch' };
  }

  return { ok: true };
}
