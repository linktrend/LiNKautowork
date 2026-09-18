import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const repoRoot = join(import.meta.dirname, '../../..');
const packagePath = join(repoRoot, 'docs/contracts/server01/MIGRATION-PACKAGE.json');

type PackageManifest = {
  packageId: string;
  orderedSql: Array<{ order: number; path: string; sha256: string; bytes: number }>;
  contracts: Array<{ path: string; sha256: string; bytes: number }>;
  orderedSqlCanonicalSha256: string;
};

function sha256(rel: string): { sha256: string; bytes: number } {
  const bytes = readFileSync(join(repoRoot, rel));
  return { sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length };
}

function loadPackage(): PackageManifest {
  return JSON.parse(readFileSync(packagePath, 'utf8')) as PackageManifest;
}

describe('server01 migration package identity', () => {
  it('lists every current supabase/migrations SQL file exactly once in apply order', () => {
    const manifest = loadPackage();
    const disk = readdirSync(join(repoRoot, 'supabase/migrations'))
      .filter((name) => name.endsWith('.sql'))
      .sort();
    expect(manifest.orderedSql.map((entry) => entry.path.replace('supabase/migrations/', '')).sort()).toEqual(disk);
    expect(manifest.orderedSql.map((entry) => entry.order)).toEqual(
      manifest.orderedSql.map((_, index) => index + 1),
    );
  });

  it('matches SHA-256 bytes for every owned SQL and contract file', () => {
    const manifest = loadPackage();
    expect(manifest.packageId).toBe('lautowork.server01.migration-identity/1.0.0');
    for (const entry of [...manifest.orderedSql, ...manifest.contracts]) {
      expect(sha256(entry.path)).toEqual({ sha256: entry.sha256, bytes: entry.bytes });
    }
    const canonical = JSON.stringify({
      packageId: manifest.packageId,
      files: manifest.orderedSql,
    }, null, 0).replace(/\n/g, '');
    const compact = JSON.stringify({
      packageId: manifest.packageId,
      files: manifest.orderedSql,
    });
    const separatorCompact = JSON.stringify({
      packageId: manifest.packageId,
      files: manifest.orderedSql,
    }).replace(/,\s+/g, ',').replace(/:\s+/g, ':');
    const digest = (value: string) => createHash('sha256').update(value).digest('hex');
    expect([compact, separatorCompact, canonical].map(digest)).toContain(manifest.orderedSqlCanonicalSha256);
  });
});
