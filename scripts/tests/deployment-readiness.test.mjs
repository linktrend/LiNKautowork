import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const composePath = path.join(root, 'deploy/prod/docker-compose.yml');
const envExample = path.join(root, 'deploy/prod/.env.example');
const gatewayDocker = path.join(root, 'deploy/common/gateway.Dockerfile');
const releaseJobsDocker = path.join(root, 'deploy/common/release-jobs.Dockerfile');
const identityPath = path.join(root, 'deploy/prod/release-identity.json');
const traefikPath = path.join(root, 'deploy/templates/traefik-dynamic.yml.example');
const renderGsm = path.join(root, 'ops/render-env-from-gsm.sh');
const renderRuntime = path.join(root, 'ops/render-runtime-env-from-gsm.sh');
const verify = path.join(root, 'ops/verify-server01-acceptance.sh');
const deployStack = path.join(root, 'ops/deploy-stack.sh');

function read(rel) {
  return fs.readFileSync(path.join(root, rel), 'utf8');
}

describe('AW-05 Server01 deployment readiness', () => {
  const compose = fs.readFileSync(composePath, 'utf8');
  const env = fs.readFileSync(envExample, 'utf8');
  const gateway = fs.readFileSync(gatewayDocker, 'utf8');
  const releaseJobs = fs.readFileSync(releaseJobsDocker, 'utf8');
  const identity = JSON.parse(fs.readFileSync(identityPath, 'utf8'));
  const traefik = fs.readFileSync(traefikPath, 'utf8');

  it('keeps protected ports private and does not use host networking', () => {
    expect(compose).not.toMatch(/^\s+ports:/m);
    expect(compose).not.toMatch(/network_mode:\s*host/);
    expect(compose).not.toMatch(/0\.0\.0\.0/);
    expect(compose).not.toMatch(/^\s+image:\s*\S+:latest\b/im);
  });

  it('attaches persistent NATS to autowork-events only', () => {
    expect(compose).toMatch(/nats_jetstream_prod:\/data/);
    expect(compose).toMatch(/^  autowork-events:/m);
    const natsBlock = compose.split(/^  nats:\n/m)[1]?.split(/^  [a-z].*:$/m)[0] ?? '';
    expect(natsBlock).toMatch(/autowork-events/);
    expect(natsBlock).not.toMatch(/autowork-edge/);
    expect(natsBlock).not.toMatch(/autowork-runtime/);
  });

  it('declares settled networks, resource limits, and in-process dispatcher', () => {
    for (const net of ['autowork-edge', 'autowork-runtime', 'autowork-events']) {
      expect(compose).toMatch(new RegExp(`^  ${net}:`, 'm'));
    }
    expect(compose).toMatch(/deploy:\n\s+resources:\n\s+limits:/);
    expect(compose).not.toMatch(/^  runtime-dispatch/m);
    expect(compose).toMatch(/profiles: \["retained-images"\]/);
  });

  it('pins reproducible gateway and release-job build inputs', () => {
    expect(gateway).toMatch(/FROM node:22\.13\.1-alpine/);
    expect(gateway).toMatch(/COPY package\.json package-lock\.json/);
    expect(gateway).toMatch(/npm ci/);
    expect(releaseJobs).toMatch(/FROM node:22\.13\.1-alpine/);
    expect(releaseJobs).toMatch(/COPY package\.json package-lock\.json/);
    expect(fs.existsSync(path.join(root, 'package-lock.json'))).toBe(true);
  });

  it('refuses live migration apply in production Compose', () => {
    expect(compose).toMatch(/LINKAUTOWORK_MIGRATION_MODE: dry-run/);
    expect(compose).not.toMatch(/apply-authorized/);
    const preflight = read('ops/migration-preflight.sh');
    expect(preflight).toMatch(/MODE="\$\{LINKAUTOWORK_MIGRATION_MODE:-dry-run\}"/);
  });

  it('carries AW-01 role names as placeholders only', () => {
    for (const role of [
      'svc_lautowork_gateway',
      'svc_lautowork_product_api',
      'svc_lautowork_runtime_dispatch',
      'svc_lautowork_n8n',
      'svc_observer',
      'svc_lautowork_migration_backup',
    ]) {
      expect(env).toContain(role);
    }
    expect(identity.aw01Roles.liveGrants).toBe('HOLD');
  });

  it('keeps Traefik initial-release routes private (no public client-web)', () => {
    expect(traefik).toMatch(/linkautowork-tailscale-only/);
    expect(traefik).toMatch(/linkautowork-gateway/);
    expect(traefik).not.toMatch(/linkautowork-client-web/);
  });

  it('renders GSM placeholders without resolving secrets or writing into git', () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aw05-runtime-'));
    const out = path.join(tmp, 'prod.env.runtime');
    const validate = spawnSync('bash', [renderGsm, 'prod', '--placeholders'], { encoding: 'utf8' });
    expect(validate.status, validate.stderr).toBe(0);
    const inside = spawnSync('bash', [renderRuntime, 'prod', '--placeholders', '--output', path.join(root, 'deploy/prod/.env.runtime')], { encoding: 'utf8' });
    expect(inside.status).not.toBe(0);
    const live = spawnSync('bash', [renderRuntime, 'prod', '--resolve-gsm', '--output', out], { encoding: 'utf8' });
    expect(live.status).toBe(2);
    const rendered = spawnSync('bash', [renderRuntime, 'prod', '--placeholders', '--output', out], { encoding: 'utf8' });
    expect(rendered.status, rendered.stderr).toBe(0);
    const body = fs.readFileSync(out, 'utf8');
    expect(body).toMatch(/<GSM_PLACEHOLDER:LINKAUTOWORK_/);
    expect(fs.statSync(out).mode & 0o777).toBe(0o600);
    fs.rmSync(tmp, { recursive: true, force: true });
  });

  it('keeps deploy-stack and acceptance verifier off live Server01', () => {
    const up = spawnSync('bash', [deployStack, 'prod', '--up'], { encoding: 'utf8' });
    expect(up.status).toBe(2);
    expect(up.stderr).toMatch(/HOLD:/);
    const verifier = spawnSync('bash', [verify, '--environment', 'prod'], { encoding: 'utf8' });
    expect(verifier.status, verifier.stderr + verifier.stdout).toBe(0);
    expect(verifier.stdout).toMatch(/Live\/provider boundaries remain HOLD/);
    expect(verifier.stdout).toMatch(/PASS with \d+ HOLD row\(s\)/);
  });

  it('documents npx vitest as the public source-topology acceptance command', () => {
    const operations = read('docs/runbooks/OPERATIONS.md');
    const tailscale = read('docs/runbooks/TAILSCALE_HARDENING.md');
    const documented = 'npx vitest run scripts/tests/deployment-readiness.test.mjs';
    expect(operations).toContain(documented);
    expect(tailscale).toContain(documented);
    expect(operations).not.toMatch(/Those exit HOLD/);
  });

  it('prints canary HOLD and still exits 0 (read-only, no n8n mutation)', () => {
    const canary = spawnSync('bash', [verify, '--environment', 'prod', '--canary', 'aw05-not-live'], { encoding: 'utf8' });
    expect(canary.status, canary.stderr + canary.stdout).toBe(0);
    expect(canary.stdout).toMatch(/HOLD: canary 'aw05-not-live' supplied but live n8n activation is AW-08 HOLD; no binding mutated/);
    expect(canary.stdout).toMatch(/PASS with \d+ HOLD row\(s\)/);
    expect(canary.stdout + canary.stderr).not.toMatch(/activat(?:ed|ing) canary/i);
  });

  it('reconciles Product API port 8080 across env, Compose, and Traefik', () => {
    expect(env).toMatch(/^PRODUCT_API_PORT=8080$/m);
    expect(env).not.toMatch(/PRODUCT_API_PORT=8090/);
    const productApi = compose.split(/^  product-api:\n/m)[1]?.split(/^  [a-z].*:$/m)[0] ?? '';
    expect(productApi).toMatch(/PORT: \$\{PRODUCT_API_PORT:-8080\}/);
    expect(productApi).toMatch(/127\.0\.0\.1:\$\{PRODUCT_API_PORT:-8080\}/);
    expect(productApi).not.toMatch(/^\s+ports:/m);
    expect(traefik).toMatch(/http:\/\/<PRODUCT_API_PRIVATE_ADDRESS>:8080/);
    expect(traefik).not.toMatch(/PRODUCT_API_PRIVATE_ADDRESS>:8090/);
  });

  it('fails the verifier when NATS is attached beyond autowork-events', () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aw05-nats-'));
    const polluted = path.join(tmp, 'docker-compose.yml');
    const extraNets = compose.replace(
      /(  nats:[\s\S]*?networks:\n)(      - autowork-events\n)/,
      '$1$2      - autowork-edge\n',
    );
    expect(extraNets).toContain('      - autowork-edge');
    expect(extraNets).not.toBe(compose);
    fs.writeFileSync(polluted, extraNets);
    const exclusive = spawnSync('bash', [verify, '--environment', 'prod', '--compose-file', polluted], { encoding: 'utf8' });
    expect(exclusive.status, exclusive.stderr + exclusive.stdout).toBe(1);
    expect(exclusive.stderr + exclusive.stdout).toMatch(/NATS is not attached only through autowork-events/);
    fs.rmSync(tmp, { recursive: true, force: true });
  });
});
