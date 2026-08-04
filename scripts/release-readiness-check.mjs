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

if (violations.length) {
  console.error(`Release-readiness check failed:\n${violations.map((item) => `- ${item}`).join('\n')}`);
  process.exit(1);
}
console.log('Release-readiness check passed: supported surfaces have no retired runtime path and required release artifacts exist.');
