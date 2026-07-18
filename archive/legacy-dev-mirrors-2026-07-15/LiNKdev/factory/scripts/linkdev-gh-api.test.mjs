import assert from 'node:assert/strict';
import { isRateLimitError } from './linkdev-gh-api.mjs';

assert.equal(isRateLimitError('GraphQL: API rate limit already exceeded'), true);
assert.equal(isRateLimitError('HTTP 403: Forbidden'), true);
assert.equal(isRateLimitError('missing label'), false);
console.log('linkdev-gh-api.test.mjs ok');
