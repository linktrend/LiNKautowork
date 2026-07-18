#!/usr/bin/env node
/**
 * LiNKdev — gh CLI wrapper with rate-limit backoff and in-run response cache.
 */
import { execSync, spawnSync } from 'node:child_process';

const RATE_LIMIT_RE = /rate limit|403|429/i;
const DEFAULT_RETRIES = 3;
const BACKOFF_MS = [5000, 15000, 45000];

function sleep(ms) {
  execSync(`sleep ${Math.max(1, Math.ceil(ms / 1000))}`);
}

export function isRateLimitError(text) {
  return RATE_LIMIT_RE.test(text ?? '');
}

/**
 * @param {string[]} args
 * @param {{ retries?: number, cache?: Map<string, string> }} [opts]
 * @returns {string}
 */
export function gh(args, opts = {}) {
  const { retries = DEFAULT_RETRIES, cache } = opts;
  const key = cache ? JSON.stringify(args) : null;
  if (key && cache.has(key)) return cache.get(key);

  let lastErr = '';
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const r = spawnSync('gh', args, { encoding: 'utf8' });
    if (r.status === 0) {
      const out = r.stdout ?? '';
      if (key) cache.set(key, out);
      return out;
    }
    lastErr = r.stderr || r.stdout || `exit ${r.status}`;
    if (!isRateLimitError(lastErr) || attempt >= retries) {
      throw new Error(`gh ${args.join(' ')} failed: ${lastErr}`);
    }
    const wait = BACKOFF_MS[attempt] ?? BACKOFF_MS[BACKOFF_MS.length - 1];
    console.warn(`gh rate limit (attempt ${attempt + 1}/${retries + 1}), waiting ${wait}ms…`);
    sleep(wait);
  }
  throw new Error(`gh ${args.join(' ')} failed: ${lastErr}`);
}

/** @param {{ retries?: number }} [opts] */
export function createGhClient(opts = {}) {
  const cache = new Map();
  const retries = opts.retries ?? DEFAULT_RETRIES;
  return {
    cache,
    /** @param {string[]} args */
    call(args) {
      return gh(args, { retries, cache });
    },
    /** @param {string} repo @param {number} issueNum */
    issueView(repo, issueNum) {
      const raw = gh(
        ['issue', 'view', String(issueNum), '--repo', repo, '--json', 'state,labels,comments'],
        { retries, cache },
      );
      return JSON.parse(raw);
    },
    /** @param {string} repo @param {number} prNum */
    prView(repo, prNum, fields = 'title,headRefName,body,labels') {
      const raw = gh(['pr', 'view', String(prNum), '--repo', repo, '--json', fields], {
        retries,
        cache,
      });
      return JSON.parse(raw);
    },
  };
}
