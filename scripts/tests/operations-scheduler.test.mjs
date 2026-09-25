import { spawnSync } from 'node:child_process';
import { generateKeyPairSync } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const scheduler = fs.readFileSync(path.join(root, 'ops/run-operations-scheduler.sh'), 'utf8');
const compose = fs.readFileSync(path.join(root, 'deploy/prod/docker-compose.yml'), 'utf8');
const mint = path.join(root, 'ops/mint-platform-token.mjs');

function runMint(env) {
  return spawnSync(process.execPath, [mint], { env: { PATH: process.env.PATH, ...env }, encoding: 'utf8' });
}

describe('operations scheduler Platform authentication', () => {
  it('mints a fresh Platform token per run and never reads a static invocation token', () => {
    expect(scheduler).toMatch(/run_once\(\) \{[\s\S]*mint-platform-token\.mjs[\s\S]*\}/);
    expect(scheduler).not.toMatch(/PLATFORM_INVOCATION_TOKEN/);
    expect(compose).not.toMatch(/PLATFORM_INVOCATION_TOKEN/);
  });

  it('announces the gateway service-token name operations by default', () => {
    expect(scheduler).toMatch(/SERVICE_NAME="\$\{LINK_SERVICE_NAME_OPERATIONS:-operations\}"/);
    expect(scheduler).toMatch(/x-link-service: \$\{SERVICE_NAME\}/);
    expect(scheduler).not.toMatch(/operations-scheduler'/);
  });

  it('refuses a non-https issuer or a missing client key without printing secrets', () => {
    expect(runMint({ PLATFORM_JWT_ISSUER: 'http://paci.example' }).status).toBe(1);
    const missing = runMint({ PLATFORM_JWT_ISSUER: 'https://paci.example' });
    expect(missing.status).toBe(1);
    expect(missing.stdout).toBe('');
    expect(missing.stderr).toMatch(/KEY_FILE or .*SECRET_RESOURCE is required/);
  });

  it('rejects a client key that is not P-256', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mint-'));
    const file = path.join(dir, 'key.pem');
    const { privateKey } = generateKeyPairSync('ec', { namedCurve: 'secp384r1' });
    fs.writeFileSync(file, privateKey.export({ type: 'pkcs8', format: 'pem' }), { mode: 0o600 });
    const result = runMint({ PLATFORM_JWT_ISSUER: 'https://paci.example', OPERATIONS_PLATFORM_CLIENT_KEY_FILE: file });
    expect(result.status).toBe(1);
    expect(result.stderr).toMatch(/P-256/);
    expect(result.stdout).toBe('');
  });
});
