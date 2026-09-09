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

const N8N_CODE = 'doc-contract-n8n-host-port-fallback';
const TOPOLOGY_CODE = 'doc-contract-shared-three-services';
const NATS_DOC_CODE = 'doc-contract-nats-http-monitor';
const NATS_COMPOSE_CODE = 'compose-nats-http-monitor';
const OPERATIONS = 'docs/runbooks/OPERATIONS.md';
const HARDENING = 'docs/runbooks/TAILSCALE_HARDENING.md';
const PRD = 'docs/LINKAUTOWORK-TECHNICAL-PRD.md';

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
  if (!/^[a-z0-9-]{1,80}$/.test(label)) throw new Error(`unsafe isolate label: ${label}`);
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

const n8nPositiveFixtures = [
  { label: 'n8n-fallback', file: OPERATIONS, text: '\nOptional N8N_TAILSCALE_IP keeps direct :5678 fallback when Traefik is unavailable.\n' },
  { label: 'n8n-paraphrase', file: HARDENING, text: '\nIf Traefik is down, operators may use a direct n8n fallback on 5678 via the tailnet IP.\n' },
  { label: 'n8n-browse-alias', file: OPERATIONS, text: '\nOperators may browse n8n at http://N8N_TAILSCALE_IP:5678.\n' },
  { label: 'n8n-host-publish', file: HARDENING, text: '\nPublish n8n on host port 5678\n' },
  { label: 'n8n-ipv4-open', file: OPERATIONS, text: '\nOperators may open http://100.64.1.10:5678.\n' },
  { label: 'n8n-ipv4-bare', file: HARDENING, text: '\nReach n8n at 100.64.1.10:5678 for recovery.\n' },
  { label: 'n8n-ipv6-visit', file: OPERATIONS, text: '\nVisit https://[fd7a:115c:a1e0::1]:5678 to recover the editor.\n' },
  { label: 'n8n-ipv6-browse', file: HARDENING, text: '\nOperators may browse n8n at http://[2001:db8::1]:5678.\n' },
  { label: 'n8n-container-browse', file: OPERATIONS, text: '\nOperators may browse n8n at http://n8n:5678.\n' },
  { label: 'n8n-tailnet-host', file: HARDENING, text: '\nOpen https://n8n.tailnet.ts.net:5678 when Traefik is down.\n' },
  { label: 'n8n-placeholder-browse', file: OPERATIONS, text: '\nOperators may browse n8n at http://<N8N_TAILSCALE_IP>:5678.\n' },
  { label: 'n8n-placeholder-open', file: HARDENING, text: '\nOpen http://<OPERATOR_N8N_DNS_NAME>:5678 in the office.\n' },
  { label: 'n8n-bare-host-port', file: OPERATIONS, text: '\nVisit n8n.example.ts.net:5678 during an outage.\n' },
  { label: 'n8n-editor-browser', file: HARDENING, text: '\nOpen the n8n editor in a browser on :5678.\n' },
  { label: 'n8n-host-at-port', file: OPERATIONS, text: '\nBind n8n host at port 5678 for recovery.\n' },
  { label: 'n8n-host-on-port', file: HARDENING, text: '\nExpose the n8n host on port 5678.\n' },
  { label: 'n8n-host-comma-on', file: OPERATIONS, text: '\nPublish the n8n host, on port 5678.\n' },
  { label: 'n8n-host-colon-on', file: HARDENING, text: '\nPublish the n8n host: on port 5678.\n' },
  { label: 'n8n-host-at-slash-on', file: OPERATIONS, text: '\nOperators still use n8n host at/on port 5678.\n' },
  { label: 'n8n-unspecified-bind', file: HARDENING, text: '\nBind n8n to 0.0.0.0:5678.\n' },
  { label: 'n8n-host-published-on', file: OPERATIONS, text: '\nThe n8n UI is host-published on :5678.\n' },
  { label: 'n8n-host-published-on-port', file: HARDENING, text: '\nKeep n8n host published on port 5678.\n' },
];

const n8nNegativeFixtures = [
  { label: 'n8n-internal-url', file: OPERATIONS, text: '\nTraefik forwards to http://n8n:5678 on the overlay network.\n' },
  { label: 'n8n-private-url', file: HARDENING, text: '\nThe approved upstream remains http://<N8N_PRIVATE_ADDRESS>:5678.\n' },
  { label: 'n8n-callback', file: OPERATIONS, text: '\nThe automation callback remains http://n8n:5678/webhook.\n' },
  { label: 'n8n-base-url', file: HARDENING, text: '\nSet N8N_BASE_URL=http://n8n:5678 for in-stack publisher calls.\n' },
  { label: 'n8n-publisher', file: OPERATIONS, text: '\nThe certified-package-publisher posts to http://n8n:5678.\n' },
  { label: 'n8n-health', file: HARDENING, text: '\nIn-stack health uses http://n8n:5678/healthz on the overlay.\n' },
  { label: 'n8n-stage-workstation', file: PRD, text: '\nStage Compose is a three-service local subset: nats, gateway, and n8n, with host-published 8080 and 5678 for workstation use.\n' },
];

const topologyPositiveFixtures = [
  { label: 'three-services', file: PRD, text: '\nBoth environments share the same three services.\n', code: TOPOLOGY_CODE },
  { label: 'three-services-ws', file: PRD, text: '\nBoth environments share the same  three  services.\n', code: TOPOLOGY_CODE },
  { label: 'three-services-num', file: PRD, text: '\nBoth environments share the same 3 services.\n', code: TOPOLOGY_CODE },
];

const natsDocPositiveFixtures = [
  { label: 'nats-monitor', file: PRD, text: '\nNATS (:4222, prod also :8222 monitor)\n', code: NATS_DOC_CODE },
];

const natsComposePositiveFixtures = [
  { label: 'nats-cmd-scalar', command: "'-js -sd /data -m=8222'" },
  { label: 'nats-cmd-array-m', command: '["-js", "-sd", "/data", "-m", "8222"]' },
  { label: 'nats-cmd-http-port', command: '["-js", "-sd", "/data", "--http_port", "8222"]' },
  { label: 'nats-cmd-http-port-eq', command: '["-js", "-sd", "/data", "--http_port=8222"]' },
  { label: 'nats-cmd-m-attached', command: '["-js", "-sd", "/data", "-m8222"]' },
  { label: 'nats-cmd-m-attached-scalar', command: "'-js -sd /data -m8222'" },
  { label: 'nats-cmd-http-hyphen', command: '["-js", "-sd", "/data", "--http-port", "8222"]' },
  { label: 'nats-cmd-http-hyphen-eq', command: '["-js", "-sd", "/data", "--http-port=8222"]' },
  { label: 'nats-cmd-http-hyphen-scalar', command: "'-js -sd /data --http-port 8222'" },
];

function main() {
  const failures = [];
  const repoViolations = collectReleaseReadinessViolations(repoRoot);
  assert(repoViolations.length === 0, `corrected repository must pass release-readiness; got ${JSON.stringify(repoViolations)}`, failures);
  assert(
    validateProductionComposeDocContract(repoRoot).length === 0,
    'corrected repository must pass the production Compose doc contract',
    failures,
  );

  for (const fixture of n8nPositiveFixtures) {
    const violations = isolate(fixture.label, (root) => {
      append(root, fixture.file, fixture.text);
    });
    assert(hasCode(violations, N8N_CODE), `${fixture.label} must fail closed: ${JSON.stringify(violations)}`, failures);
    assert(!hasCode(violations, TOPOLOGY_CODE), `${fixture.label} must not trip unrelated topology: ${JSON.stringify(violations)}`, failures);
  }

  for (const fixture of n8nNegativeFixtures) {
    const violations = isolate(fixture.label, (root) => {
      append(root, fixture.file, fixture.text);
    });
    assert(!hasCode(violations, N8N_CODE), `${fixture.label} must remain allowed: ${JSON.stringify(violations)}`, failures);
  }

  for (const fixture of topologyPositiveFixtures) {
    const violations = isolate(fixture.label, (root) => {
      append(root, fixture.file, fixture.text);
    });
    assert(hasCode(violations, fixture.code), `${fixture.label} must fail closed: ${JSON.stringify(violations)}`, failures);
  }

  for (const fixture of natsDocPositiveFixtures) {
    const violations = isolate(fixture.label, (root) => {
      append(root, fixture.file, fixture.text);
    });
    assert(hasCode(violations, fixture.code), `${fixture.label} must fail closed: ${JSON.stringify(violations)}`, failures);
  }

  for (const fixture of natsComposePositiveFixtures) {
    const violations = isolate(fixture.label, (root) => {
      rewriteNatsCommand(root, fixture.command);
    });
    assert(hasCode(violations, NATS_COMPOSE_CODE), `${fixture.label} must fail closed: ${JSON.stringify(violations)}`, failures);
  }

  if (failures.length) {
    console.error(`Release-readiness doc contract test failed:\n${failures.map((item) => `- ${item}`).join('\n')}`);
    process.exitCode = 1;
    return;
  }
  console.log('Release-readiness doc contract test passed: corrected repository is clean and each planted contradiction fails closed.');
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) main();
