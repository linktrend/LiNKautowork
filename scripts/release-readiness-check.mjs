import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const supportedRoots = [
  'README.md', 'deploy', 'docs/LINKAUTOWORK-INTENT.md', 'docs/LINKAUTOWORK-TECHNICAL-PRD.md',
  'docs/LINKAUTOWORK-OPERATIONS-MANUAL.md', 'docs/OPEN-ISSUES.md', 'docs/runbooks', 'gateway', 'apps', 'ops', 'scripts', 'automations/templates', '.github', 'AGENTS.md', 'package.json',
];
const retiredRuntimeMarker = /(?:\baios\b|link[-_ ]?aios|linktrend[-_ ]?system)/i;
const allowedHistorical = new Set([
  'docs/production-roadmap/work-packets/WP-12-RELEASE-READINESS.md',
  'docs/production-roadmap/evidence/WP-12-LEGACY-RETIREMENT-INVENTORY.md',
]);

function filesAt(relative) {
  const absolute = path.join(root, relative);
  if (!fs.existsSync(absolute)) return [];
  if (fs.statSync(absolute).isFile()) return [relative];
  return fs.readdirSync(absolute, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => path.relative(root, path.join(entry.parentPath, entry.name)));
}

const violations = [];

function serviceBlock(content, service) {
  const start = content.indexOf(`  ${service}:`);
  if (start === -1) return '';
  const remainder = content.slice(start);
  const nextService = remainder.slice(1).search(/\n  [A-Za-z0-9_-]+:/);
  return nextService === -1 ? remainder : remainder.slice(0, nextService + 1);
}

function assertPrivatePersistentNats(relative, volume) {
  const absolute = path.join(root, relative);
  if (!fs.existsSync(absolute)) return;
  const content = fs.readFileSync(absolute, 'utf8');
  const nats = serviceBlock(content, 'nats');
  if (!nats) {
    violations.push(`compose-missing-service:${relative}:nats`);
    return;
  }
  if (/\n    ports:/m.test(nats)) violations.push(`compose-nats-public:${relative}`);
  if (!nats.includes('command: ["-js", "-sd", "/data"]')) violations.push(`compose-nats-not-persistent:${relative}`);
  if (!nats.includes(`- ${volume}:/data`)) violations.push(`compose-nats-missing-volume:${relative}`);
}

for (const supportedRoot of supportedRoots) {
  for (const file of filesAt(supportedRoot)) {
    if (file === 'scripts/release-readiness-check.mjs' || allowedHistorical.has(file) || file.includes('/archive/') || file.startsWith('archive/')) continue;
    if (!/\.(?:md|mjs|ts|js|json|ya?ml|sh|Dockerfile|example)$/i.test(file) && !file.endsWith('Dockerfile')) continue;
    if (retiredRuntimeMarker.test(fs.readFileSync(path.join(root, file), 'utf8'))) violations.push(file);
  }
}

const required = [
  'docs/production-roadmap/evidence/WP-12-SUPPORTED-SURFACE-INVENTORY.md',
  'docs/production-roadmap/evidence/WP-12-RELEASE-CANDIDATE-MANIFEST.md',
  'docs/production-roadmap/evidence/WP-12-VPS-DEPLOYMENT-INPUT-REGISTER.md',
  'deploy/templates/traefik-dynamic.yml.example',
  'deploy/templates/tailscale-boundary.env.example',
  'deploy/dev/docker-compose.yml',
  'deploy/prod/docker-compose.yml',
  'ops/reconcile-disposable-eval-resources.sh',
  'ops/migration-preflight.sh',
  'ops/publish-certified-packages.sh',
  'ops/run-operations-scheduler.sh',
  'apps/product-api/Dockerfile',
  'apps/web/Dockerfile',
  'apps/operator-console/Dockerfile',
];
for (const file of required) if (!fs.existsSync(path.join(root, file))) violations.push(`missing:${file}`);

const productionCompose = path.join(root, 'deploy/prod/docker-compose.yml');
if (fs.existsSync(productionCompose)) {
  const content = fs.readFileSync(productionCompose, 'utf8');
  for (const service of ['nats', 'gateway', 'n8n', 'product-api', 'client-web', 'operator-console', 'migration-preflight', 'certified-package-publisher', 'operations-scheduler']) {
    if (!new RegExp(`^  ${service}:`, 'm').test(content)) violations.push(`compose-missing-service:${service}`);
  }
  if (!content.includes('nats_jetstream_prod:/data')) violations.push('compose-missing-persistent-jetstream');
  if (/traefik\.http\.routers\./.test(content)) violations.push('compose-has-inline-traefik-router');
  if (/image:\s*[^\n]*:latest\b/i.test(content)) violations.push('compose-uses-latest-image');
}

assertPrivatePersistentNats('deploy/dev/docker-compose.yml', 'nats_jetstream_dev');
assertPrivatePersistentNats('deploy/prod/docker-compose.yml', 'nats_jetstream_prod');

const traefikTemplate = path.join(root, 'deploy/templates/traefik-dynamic.yml.example');
const tailscaleTemplate = path.join(root, 'deploy/templates/tailscale-boundary.env.example');
if (fs.existsSync(traefikTemplate) && fs.existsSync(tailscaleTemplate)) {
  const traefik = fs.readFileSync(traefikTemplate, 'utf8');
  const tailscale = fs.readFileSync(tailscaleTemplate, 'utf8');
  for (const route of ['linkautowork-operator-n8n', 'linkautowork-operator-console']) {
    if (!new RegExp(`^    ${route}:`, 'm').test(traefik)) violations.push(`private-ingress-missing-route:${route}`);
  }
  for (const marker of [
    'middlewares: [linkautowork-tailscale-only]',
    'linkautowork-tailscale-only:',
    'ipAllowList:',
    'sourceRange: ["<TAILSCALE_CIDR>"]',
    'http://<N8N_PRIVATE_ADDRESS>:5678',
    'http://<OPERATOR_CONSOLE_PRIVATE_ADDRESS>:8080',
  ]) {
    if (!traefik.includes(marker)) violations.push(`private-ingress-template-missing:${marker}`);
  }
  for (const marker of [
    'TAILSCALE_AUTH_KEY_SECRET_NAME=<APPROVED_GSM_SECRET_NAME>',
    'TAILSCALE_OPERATOR_CIDR=<TAILSCALE_CIDR>',
    'N8N_PRIVATE_ADDRESS=<N8N_PRIVATE_ADDRESS>',
  ]) {
    if (!tailscale.includes(marker)) violations.push(`private-ingress-input-missing:${marker}`);
  }
  if (/linkautowork-nats|4222|8222/.test(traefik)) violations.push('private-ingress-exposes-nats');
}

if (violations.length) {
  console.error(`Release-readiness check failed:\n${violations.map((item) => `- ${item}`).join('\n')}`);
  process.exit(1);
}
console.log('Release-readiness check passed: supported surfaces have no retired runtime path and required release artifacts exist.');
