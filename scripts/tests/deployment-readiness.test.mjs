import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';
import {
  collectReleaseReadinessViolations,
  validatePrivateIngressTemplates,
  validatePrivatePersistentNats,
} from '../release-readiness-check.mjs';

const repoRoot = path.resolve(import.meta.dirname, '../..');
const read = (relative) => fs.readFileSync(path.join(repoRoot, relative), 'utf8');
const run = (command, args, extraEnv = {}) => spawnSync(command, args, {
  cwd: repoRoot,
  encoding: 'utf8',
  env: { ...process.env, ...extraEnv },
});

describe('deployment readiness source checks', () => {
  it('keeps the release check positive for both persistent private NATS Compose services', () => {
    expect(collectReleaseReadinessViolations(repoRoot)).toEqual([]);
    expect(validatePrivatePersistentNats('dev', read('deploy/dev/docker-compose.yml'), 'nats_jetstream_dev')).toEqual([]);
    expect(validatePrivatePersistentNats('prod', read('deploy/prod/docker-compose.yml'), 'nats_jetstream_prod')).toEqual([]);
  });

  it('rejects malformed YAML, wrong route bindings, resolved authority, and NATS exposure', () => {
    const traefik = read('deploy/templates/traefik-dynamic.yml.example');
    const tailscale = read('deploy/templates/tailscale-boundary.env.example');
    expect(validatePrivateIngressTemplates('http:\n  routers: [', tailscale).join('\n')).toMatch(/invalid-yaml/);
    expect(validatePrivateIngressTemplates(traefik.replace('middlewares: [linkautowork-tailscale-only]\n      service: linkautowork-n8n', 'service: linkautowork-n8n'), tailscale)).toContain('private-ingress-route-middleware:linkautowork-operator-n8n');
    expect(validatePrivateIngressTemplates(traefik.replace('service: linkautowork-n8n', 'service: wrong-service'), tailscale)).toContain('private-ingress-route-service:linkautowork-operator-n8n');
    expect(validatePrivateIngressTemplates(traefik.replace('<OPERATOR_N8N_DNS_NAME>', 'n8n.example.com'), tailscale)).toContain('private-ingress-route-authority:linkautowork-operator-n8n');
    expect(validatePrivateIngressTemplates(`${traefik}\n    linkautowork-nats:\n      loadBalancer:\n        servers: [{ url: "nats://nats:4222" }]`, tailscale)).toContain('private-ingress-exposes-nats');
    expect(validatePrivateIngressTemplates(traefik, tailscale.replace('<TAILSCALE_CIDR>', '10.0.0.0/8'))).toContain('private-ingress-input-authority:TAILSCALE_OPERATOR_CIDR');
  });

  it('rejects exposed or non-persistent NATS in either Compose contract', () => {
    const compose = read('deploy/dev/docker-compose.yml');
    expect(validatePrivatePersistentNats('dev', compose.replace('    volumes:\n      - nats_jetstream_dev:/data', '    ports:\n      - "4222:4222"\n    volumes:\n      - nats_jetstream_dev:/data'), 'nats_jetstream_dev')).toContain('compose-nats-public:dev');
    expect(validatePrivatePersistentNats('dev', compose.replace('command: ["-js", "-sd", "/data"]', 'command: ["-js"]'), 'nats_jetstream_dev')).toContain('compose-nats-not-persistent:dev');
    expect(validatePrivatePersistentNats('prod', read('deploy/prod/docker-compose.yml').replace('nats_jetstream_prod:/data', 'other_volume:/data'), 'nats_jetstream_prod')).toContain('compose-nats-missing-volume:prod');
  });
});

describe('migration preflight portability and fail-closed modes', () => {
  const script = path.join(repoRoot, 'ops/migration-preflight.sh');

  it('is valid under both POSIX sh and Bash syntax parsers', () => {
    expect(run('sh', ['-n', script]).status).toBe(0);
    expect(run('bash', ['-n', script]).status).toBe(0);
  });

  it('keeps dry-run as the safe default and rejects unknown or unauthorised apply modes', () => {
    const dryRun = run('sh', [script], { LINKAUTOWORK_MIGRATION_MODE: '', LINKAUTOWORK_APPROVED_MIGRATION_COMMAND: '' });
    expect(dryRun.status).toBe(0);
    expect(dryRun.stdout).toContain('no database connection or apply attempted');

    const invalid = run('sh', [script], { LINKAUTOWORK_MIGRATION_MODE: 'unexpected' });
    expect(invalid.status).not.toBe(0);
    expect(`${invalid.stdout}${invalid.stderr}`).toContain('must be dry-run or apply-authorized');

    const unauthorised = run('sh', [script], { LINKAUTOWORK_MIGRATION_MODE: 'apply-authorized', LINKAUTOWORK_APPROVED_MIGRATION_COMMAND: '' });
    expect(unauthorised.status).not.toBe(0);
    expect(`${unauthorised.stdout}${unauthorised.stderr}`).toContain('authorised migration command required');
  });

  it('executes only an explicitly supplied authorised command path', () => {
    const result = run('sh', [script], {
      LINKAUTOWORK_MIGRATION_MODE: 'apply-authorized',
      LINKAUTOWORK_APPROVED_MIGRATION_COMMAND: 'printf authorized-command-path',
    });
    expect(result.status).toBe(0);
    expect(result.stdout).toContain('authorized-command-path');
  });
});

describe('SBOM command configuration and reproducibility', () => {
  it('retains separate generation and reproducibility-check commands', () => {
    const packageJson = JSON.parse(read('package.json'));
    expect(packageJson.scripts.sbom).toBe('node scripts/generate-sbom.mjs');
    expect(packageJson.scripts['sbom:check']).toBe('node scripts/generate-sbom.mjs --check');
    expect(read('.github/workflows/ci.yml')).toContain('npm run sbom:check');
  });

  it('passes the lockfile-based reproducibility check', () => {
    const result = run('npm', ['run', 'sbom:check', '--silent']);
    expect(result.status).toBe(0);
    expect(`${result.stdout}${result.stderr}`).toMatch(/reproducible \d+ byte document/);
  });
});

describe('CI shell syntax coverage', () => {
  it('explicitly covers Bash and POSIX sh for portable ops scripts', () => {
    const workflow = read('.github/workflows/ci.yml');
    expect(workflow).toMatch(/bash -n "\$f"/);
    expect(workflow.match(/^\s+bash -n "\$f"$/gm)).toHaveLength(2);
    expect(workflow).toContain('sh -n ops/migration-preflight.sh');
  });
});
