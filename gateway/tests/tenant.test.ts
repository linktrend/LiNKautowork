import { describe, expect, it } from 'vitest';
import { assertCanonicalTenant } from '../src/lib/tenant.js';

describe('assertCanonicalTenant', () => {
  it('accepts canonical UUID', () => {
    expect(() =>
      assertCanonicalTenant(
        '00000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000001',
      ),
    ).not.toThrow();
  });

  it('rejects mismatched tenant UUID', () => {
    expect(() =>
      assertCanonicalTenant(
        '11111111-1111-1111-1111-111111111111',
        '00000000-0000-0000-0000-000000000001',
      ),
    ).toThrow(/tenant mismatch/);
  });
});
