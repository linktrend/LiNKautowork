import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it } from 'vitest';

import { calculatePackageDigest, createWp02Validator, prepareCandidate, type ArchitectRequest } from '../src/index.js';

const temporaryRoots: string[] = [];
const repoRoot = fileURLToPath(new URL('../../../', import.meta.url));

afterEach(async () => {
  await Promise.all(temporaryRoots.splice(0).map((directory) => rm(directory, { recursive: true, force: true })));
});

function request(): ArchitectRequest {
  return {
    taskId: 'wp02-adapter-test', mode: 'create',
    target: { automationId: 'wp02-adapter-candidate', version: '0.1.0', displayName: 'WP-02 Adapter Candidate', owningProgram: 'linkautowork', classification: 'internal_only', ownerKind: 'shared_internal', bindingOperations: ['linkautowork.wp02-adapter-test'], sourceGitSha: 'c'.repeat(40) },
    approvedSources: [],
    requirements: { summary: 'Prepare a candidate that is structurally validated through the WP-02 package validation adapter.', expectedOutput: { description: 'A candidate contract result.', fields: ['status', 'automation_id'] }, triggerMode: 'manual', resultMode: 'none', sideEffects: ['none'], requiredCapabilities: [], requiredSecretReferences: [] },
    exclusions: [], runtime: { engine: 'n8n', n8nVersion: '2.30.0', supportedCapabilities: [] }, evidenceReferences: [],
  };
}

async function writeCandidate(root: string, packageRoot: string, files: Readonly<Record<string, string>>): Promise<string> {
  const destination = join(root, packageRoot.replace(/^automations\/catalog\//, ''));
  for (const [relative, content] of Object.entries(files)) {
    const file = join(destination, relative);
    await mkdir(resolve(file, '..'), { recursive: true });
    await writeFile(file, content, 'utf8');
  }
  return destination;
}

describe('WP-02 candidate validation adapter', () => {
  it('validates a generated candidate through the WP-02 package validator without a receipt forgery', async () => {
    const catalogModule = await import(new URL('../../automation-catalog/src/catalog.mjs', import.meta.url).href) as {
      validatePackageDirectory(input: { repoRoot: string; packageDir: string }): { errors: Array<{ code: string }> };
    };
    const validator = createWp02Validator({
      async run(packageRoot, files) {
        const temp = await mkdtemp(join(tmpdir(), 'linkautowork-architect-'));
        temporaryRoots.push(temp);
        const packageDir = await writeCandidate(temp, packageRoot, files);
        const result = catalogModule.validatePackageDirectory({ repoRoot, packageDir });
        return {
          status: result.errors.length ? 'failed' : 'passed',
          command: 'WP-02 validatePackageDirectory adapter',
          findings: result.errors.map((entry: { code: string }) => entry.code),
        };
      },
    });
    const report = await prepareCandidate(request(), validator);

    expect(report.status).toBe('candidate');
    expect(report.validation).toEqual({ status: 'passed', command: 'WP-02 validatePackageDirectory adapter', findings: [] });
  });

  it('uses the exact WP-01/WP-02 digest exclusions while retaining governed fixtures', async () => {
    const catalogModule = await import(new URL('../../automation-catalog/src/catalog.mjs', import.meta.url).href) as {
      calculatePackageDigest(packageDir: string): string;
    };
    const candidate = (await prepareCandidate(request())).candidate;
    expect(candidate).toBeDefined();
    const withExcludedEvidence = {
      ...candidate!.files,
      'evals/certification-receipt.json': JSON.stringify({ passed: true }),
      'evals/evidence/redacted-run.json': JSON.stringify({ redacted: true }),
      'evals/receipts/candidate-run.json': JSON.stringify({ status: 'passed' }),
    };
    const temp = await mkdtemp(join(tmpdir(), 'linkautowork-architect-digest-'));
    temporaryRoots.push(temp);
    const packageDir = await writeCandidate(temp, candidate!.root, withExcludedEvidence);

    expect(calculatePackageDigest(withExcludedEvidence)).toBe(candidate!.packageDigest);
    expect(catalogModule.calculatePackageDigest(packageDir)).toBe(candidate!.packageDigest);

    const governedChange = {
      ...withExcludedEvidence,
      'evals/fixtures/happy-path.json': JSON.stringify({ kind: 'redacted_fixture', changed: true }),
    };
    const governedTemp = await mkdtemp(join(tmpdir(), 'linkautowork-architect-governed-'));
    temporaryRoots.push(governedTemp);
    const governedDir = await writeCandidate(governedTemp, candidate!.root, governedChange);
    const architectChanged = calculatePackageDigest(governedChange);
    expect(architectChanged).not.toBe(candidate!.packageDigest);
    expect(catalogModule.calculatePackageDigest(governedDir)).toBe(architectChanged);
  });
});
