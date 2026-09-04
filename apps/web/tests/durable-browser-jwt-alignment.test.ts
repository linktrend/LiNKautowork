import { createHmac } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';

describe('durable browser e2e JWT alignment', () => {
  it('signs the audit fixture with the scanner-safe disposable PostgREST secret from compose', async () => {
    const [compose, harness, verify] = await Promise.all([
      readFile(new URL('../../../packages/automation-contracts/disposable-db/docker-compose.yml', import.meta.url), 'utf8'),
      readFile(new URL('../e2e/run-durable-browser-e2e.sh', import.meta.url), 'utf8'),
      readFile(new URL('../../../packages/automation-contracts/disposable-db/postgrest-verify.sh', import.meta.url), 'utf8'),
    ]);
    const composeSecret = compose.match(/PGRST_JWT_SECRET:\s*(\S+)/)?.[1];
    expect(composeSecret).toBeTruthy();
    expect(verify).toContain(`jwt_secret='${composeSecret}'`);
    expect(harness).toContain("sed -n 's/^[[:space:]]*PGRST_JWT_SECRET:[[:space:]]*//p' \"$COMPOSE_FILE\"");
    expect(harness).toContain('DURABLE_POSTGREST_JWT_SECRET="$DISPOSABLE_POSTGREST_JWT_SECRET"');
    expect(harness).not.toContain(['linkautowork-disposable-postgrest', 'secret-2026'].join('-'));
    const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
    const payload = Buffer.from(JSON.stringify({ role: 'service_role' })).toString('base64url');
    const signedWithCompose = createHmac('sha256', composeSecret!).update(`${header}.${payload}`).digest('base64url');
    const retiredLiteral = ['linkautowork-disposable-postgrest', 'secret-2026'].join('-');
    const truncatedPlaceholder = composeSecret!.replace(/\.disposable-postgrest-jwt$/, '');
    const signedWithRetiredLiteral = createHmac('sha256', retiredLiteral).update(`${header}.${payload}`).digest('base64url');
    const signedWithTruncatedPlaceholder = createHmac('sha256', truncatedPlaceholder).update(`${header}.${payload}`).digest('base64url');
    expect(signedWithCompose).not.toBe(signedWithRetiredLiteral);
    expect(signedWithCompose).not.toBe(signedWithTruncatedPlaceholder);
  });
});
