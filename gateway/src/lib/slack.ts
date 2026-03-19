import { createHmac, timingSafeEqual } from 'node:crypto';

export function verifySlackSignature(args: {
  signingSecret: string;
  timestamp: string;
  signature: string;
  rawBody: string;
  nowSec?: number;
}): boolean {
  const nowSec = args.nowSec ?? Math.floor(Date.now() / 1000);
  const ts = Number(args.timestamp);
  if (Number.isNaN(ts)) return false;

  if (Math.abs(nowSec - ts) > 60 * 5) {
    return false;
  }

  const base = `v0:${args.timestamp}:${args.rawBody}`;
  const expected = `v0=${createHmac('sha256', args.signingSecret).update(base).digest('hex')}`;

  const expectedBuf = Buffer.from(expected);
  const providedBuf = Buffer.from(args.signature);
  if (expectedBuf.length !== providedBuf.length) return false;
  return timingSafeEqual(expectedBuf, providedBuf);
}
