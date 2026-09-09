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

function rewriteNatsCommand(root, commandYaml) {
  const file = path.join(root, 'deploy/prod/docker-compose.yml');
  const current = fs.readFileSync(file, 'utf8');
  const next = current.replace(/command:\s*\["-js", "-sd", "\/data"\]/, `command: ${commandYaml}`);
  if (next === current) throw new Error(`failed to rewrite nats command to ${commandYaml}`);
  fs.writeFileSync(file, next);
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

  const n8nBrowseAlias = isolate('n8n-browse-alias', (root) => {
    append(root, 'docs/runbooks/OPERATIONS.md', '\nOperators may browse n8n at http://N8N_TAILSCALE_IP:5678.\n');
  });
  assert(hasCode(n8nBrowseAlias, 'doc-contract-n8n-host-port-fallback'), `n8n browse alias must fail closed: ${JSON.stringify(n8nBrowseAlias)}`, failures);

  const n8nHostPublish = isolate('n8n-host-publish', (root) => {
    append(root, 'docs/runbooks/TAILSCALE_HARDENING.md', '\nPublish n8n on host port 5678\n');
  });
  assert(hasCode(n8nHostPublish, 'doc-contract-n8n-host-port-fallback'), `explicit n8n host-publish claim must fail closed: ${JSON.stringify(n8nHostPublish)}`, failures);

  const internalN8nUrl = isolate('n8n-internal-url', (root) => {
    append(root, 'docs/runbooks/OPERATIONS.md', '\nTraefik forwards to http://n8n:5678 on the overlay network.\n');
  });
  assert(!hasCode(internalN8nUrl, 'doc-contract-n8n-host-port-fallback'), `ordinary internal n8n URL must not fail closed: ${JSON.stringify(internalN8nUrl)}`, failures);

  const privateN8nUrl = isolate('n8n-private-url', (root) => {
    append(root, 'docs/runbooks/TAILSCALE_HARDENING.md', '\nThe approved upstream remains http://<N8N_PRIVATE_ADDRESS>:5678.\n');
  });
  assert(!hasCode(privateN8nUrl, 'doc-contract-n8n-host-port-fallback'), `private n8n upstream URL must not fail closed: ${JSON.stringify(privateN8nUrl)}`, failures);

  const threeServices = isolate('three-services', (root) => {
    append(root, 'docs/LINKAUTOWORK-TECHNICAL-PRD.md', '\nBoth environments share the same three services.\n');
  });
  assert(hasCode(threeServices, 'doc-contract-shared-three-services'), `shared three-service claim must fail closed: ${JSON.stringify(threeServices)}`, failures);

  const threeServicesSpaced = isolate('three-services-ws', (root) => {
    append(root, 'docs/LINKAUTOWORK-TECHNICAL-PRD.md', '\nBoth environments share the same  three  services.\n');
  });
  assert(hasCode(threeServicesSpaced, 'doc-contract-shared-three-services'), `whitespace-flexible three-service claim must fail closed: ${JSON.stringify(threeServicesSpaced)}`, failures);

  const threeServicesNumeric = isolate('three-services-num', (root) => {
    append(root, 'docs/LINKAUTOWORK-TECHNICAL-PRD.md', '\nBoth environments share the same 3 services.\n');
  });
  assert(hasCode(threeServicesNumeric, 'doc-contract-shared-three-services'), `numeric three-service claim must fail closed: ${JSON.stringify(threeServicesNumeric)}`, failures);

  const natsMonitor = isolate('nats-monitor', (root) => {
    append(root, 'docs/LINKAUTOWORK-TECHNICAL-PRD.md', '\nNATS (:4222, prod also :8222 monitor)\n');
  });
  assert(hasCode(natsMonitor, 'doc-contract-nats-http-monitor'), `NATS :8222 monitor claim must fail closed: ${JSON.stringify(natsMonitor)}`, failures);

  const natsScalarMonitor = isolate('nats-cmd-scalar', (root) => {
    rewriteNatsCommand(root, "'-js -sd /data -m=8222'");
  });
  assert(hasCode(natsScalarMonitor, 'compose-nats-http-monitor'), `scalar -m=8222 command must fail closed: ${JSON.stringify(natsScalarMonitor)}`, failures);

  const natsArrayM = isolate('nats-cmd-array-m', (root) => {
    rewriteNatsCommand(root, '["-js", "-sd", "/data", "-m", "8222"]');
  });
  assert(hasCode(natsArrayM, 'compose-nats-http-monitor'), `array -m 8222 command must fail closed: ${JSON.stringify(natsArrayM)}`, failures);

  const natsArrayHttpPort = isolate('nats-cmd-http-port', (root) => {
    rewriteNatsCommand(root, '["-js", "-sd", "/data", "--http_port", "8222"]');
  });
  assert(hasCode(natsArrayHttpPort, 'compose-nats-http-monitor'), `array --http_port command must fail closed: ${JSON.stringify(natsArrayHttpPort)}`, failures);

  const natsEqualsHttpPort = isolate('nats-cmd-http-port-eq', (root) => {
    rewriteNatsCommand(root, '["-js", "-sd", "/data", "--http_port=8222"]');
  });
  assert(hasCode(natsEqualsHttpPort, 'compose-nats-http-monitor'), `array --http_port=8222 command must fail closed: ${JSON.stringify(natsEqualsHttpPort)}`, failures);

  if (failures.length) {
    console.error(`Release-readiness doc contract test failed:\n${failures.map((item) => `- ${item}`).join('\n')}`);
    process.exitCode = 1;
    return;
  }
  console.log('Release-readiness doc contract test passed: corrected repository is clean and each planted contradiction fails closed.');
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) main();
