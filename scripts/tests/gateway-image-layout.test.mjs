import { spawnSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';

const image = `linkautowork-gateway-layout-proof:${process.pid}`;

function docker(args, options = {}) {
  return spawnSync('docker', args, {
    cwd: process.cwd(),
    encoding: 'utf8',
    maxBuffer: 16 * 1024 * 1024,
    ...options,
  });
}

describe('gateway production image layout', () => {
  const dockerAvailable = docker(['version']).status === 0;

  it.skipIf(!dockerAvailable)('contains and loads the checked-in provider catalogue at the gateway startup import path', () => {
    const build = docker(['build', '--file', 'deploy/common/gateway.Dockerfile', '--tag', image, '.']);
    try {
      expect(build.status, build.stderr || build.stdout).toBe(0);

      const probe = docker([
        'run', '--rm', '--entrypoint', 'node', image,
        '-e',
        "import('./dist/gateway/src/services/provider-route-service.js').then(() => process.stdout.write('provider-catalogue-loaded\\n'))",
      ]);
      expect(probe.status, probe.stderr || probe.stdout).toBe(0);
      expect(probe.stdout).toContain('provider-catalogue-loaded');
    } finally {
      docker(['rmi', '--force', image]);
    }
  }, 180_000);
});
