import { HttpError } from './http-error.js';

export function assertCanonicalTenant(tenantId: string, expectedTenantId: string): void {
  if (tenantId !== expectedTenantId) {
    throw new HttpError(
      403,
      `tenant mismatch: expected ${expectedTenantId}, received ${tenantId}`,
    );
  }
}
