import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import {
  collectReleaseReadinessViolations,
  validateProductionComposeDocContract,
} from '../release-readiness-check.mjs';

const repoRoot = path.resolve(import.meta.dirname, '../..');
const contractFiles = [
  'deploy/prod/docker-compose.yml',
  'docs/runbooks/TAILSCALE_HARDENING.md',
  'docs/runbooks/OPERATIONS.md',
  'docs/LINKAUTOWORK-TECHNICAL-PRD.md',
];

function copyContractTree(dest) {
  for (const relative of contractFiles) {
    const target = path.join(dest, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(path.join(repoRoot, relative), target);
  }
}

function append(root, relative, text) {
  fs.appendFileSync(path.join(root, relative), text);
}

function hasCode(violations, code) {
  return violations.some((item) => item === code || item.startsWith(`${code}:`));
}

function assert(condition, message, failures) {
  if (!condition) failures.push(message);
}

function isolate(label, mutate) {
  const dest = fs.mkdtempSync(path.join(os.tmpdir(), `linkautowork-doc-contract-${label}-`));
  copyContractTree(dest);
  mutate(dest);
  try {
    return validateProductionComposeDocContract(dest);
  } finally {
    fs.rmSync(dest, { recursive: true, force: true });
  }
}

function main() {
  const failures = [];
  const repoViolations = collectReleaseReadinessViolations(repoRoot);
  assert(repoViolations.length === 0, `corrected repository must pass release-readiness; got ${JSON.stringify(repoViolations)}`, failures);
  assert(
    validateProductionComposeDocContract(repoRoot).length === 0,
    'corrected repository must pass the production Compose doc contract',
    failures,
  );

  const n8nFallback = isolate('n8n-fallback', (root) => {
    append(root, 'docs/runbooks/OPERATIONS.md', '\nOptional N8N_TAILSCALE_IP keeps direct :5678 fallback when Traefik is unavailable.\n');
  });
  assert(hasCode(n8nFallback, 'doc-contract-n8n-host-port-fallback'), `n8n fallback paraphrase must fail closed: ${JSON.stringify(n8nFallback)}`, failures);
  assert(!hasCode(n8nFallback, 'doc-contract-shared-three-services'), `n8n fallback must not trip unrelated topology: ${JSON.stringify(n8nFallback)}`, failures);

  const n8nParaphrase = isolate('n8n-paraphrase', (root) => {
    append(root, 'docs/runbooks/TAILSCALE_HARDENING.md', '\nIf Traefik is down, operators may use a direct n8n fallback on 5678 via the tailnet IP.\n');
  });
  assert(hasCode(n8nParaphrase, 'doc-contract-n8n-host-port-fallback'), `n8n fallback signal parse must fail closed: ${JSON.stringify(n8nParaphrase)}`, failures);

  const threeServices = isolate('three-services', (root) => {
    append(root, 'docs/LINKAUTOWORK-TECHNICAL-PRD.md', '\nBoth environments share the same three services.\n');
  });
  assert(hasCode(threeServices, 'doc-contract-shared-three-services'), `shared three-service claim must fail closed: ${JSON.stringify(threeServices)}`, failures);

  const natsMonitor = isolate('nats-monitor', (root) => {
    append(root, 'docs/LINKAUTOWORK-TECHNICAL-PRD.md', '\nNATS (:4222, prod also :8222 monitor)\n');
  });
  assert(hasCode(natsMonitor, 'doc-contract-nats-http-monitor'), `NATS :8222 monitor claim must fail closed: ${JSON.stringify(natsMonitor)}`, failures);

  if (failures.length) {
    console.error(`Release-readiness doc contract test failed:\n${failures.map((item) => `- ${item}`).join('\n')}`);
    process.exitCode = 1;
    return;
  }
  console.log('Release-readiness doc contract test passed: corrected repository is clean and each planted contradiction fails closed.');
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) main();
