import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const defaultOutput = path.join(root, 'artifacts', 'sbom', 'cyclonedx.json');
const checkOnly = process.argv.includes('--check');
const outputArgumentIndex = process.argv.indexOf('--output');
const outputPath = outputArgumentIndex === -1
  ? defaultOutput
  : path.resolve(root, process.argv[outputArgumentIndex + 1] ?? '');
const cli = path.join(root, 'node_modules', '.bin', 'cyclonedx-npm');

if (!fs.existsSync(cli)) {
  console.error('CycloneDX CLI is missing; run npm ci before generating the SBOM.');
  process.exit(1);
}

const temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'linkautowork-sbom-'));
const firstOutput = path.join(temporaryDirectory, 'first.json');
const secondOutput = path.join(temporaryDirectory, 'second.json');

function generate(destination) {
  const result = spawnSync(cli, [
    '--package-lock-only',
    '--output-reproducible',
    '--output-format',
    'JSON',
    '--spec-version',
    '1.6',
    '--mc-type',
    'application',
    '--validate',
    '--output-file',
    destination,
  ], { cwd: root, encoding: 'utf8' });

  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  if (result.status !== 0) process.exit(result.status ?? 1);
}

try {
  generate(firstOutput);

  if (checkOnly) {
    generate(secondOutput);
    const first = fs.readFileSync(firstOutput);
    const second = fs.readFileSync(secondOutput);
    if (!first.equals(second)) {
      console.error('CycloneDX SBOM is not reproducible: repeated lockfile generations differ.');
      process.exit(1);
    }
    console.log(`CycloneDX SBOM check passed: reproducible ${first.length} byte document.`);
  } else {
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    fs.copyFileSync(firstOutput, outputPath);
    console.log(`CycloneDX SBOM generated: ${path.relative(root, outputPath)}`);
  }
} finally {
  fs.rmSync(temporaryDirectory, { recursive: true, force: true });
}
