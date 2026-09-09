import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import yaml from 'js-yaml';

const supportedRoots = [
  'README.md', 'deploy', 'docs/LINKAUTOWORK-INTENT.md', 'docs/LINKAUTOWORK-TECHNICAL-PRD.md',
  'docs/LINKAUTOWORK-OPERATIONS-MANUAL.md', 'docs/OPEN-ISSUES.md', 'docs/runbooks', 'gateway', 'apps', 'ops', 'scripts', 'automations/templates', '.github', 'AGENTS.md', 'package.json',
];
const retiredRuntimeMarker = /(?:\baios\b|link[-_ ]?aios|linktrend[-_ ]?system)/i;
const allowedHistorical = new Set([
  'docs/production-roadmap/work-packets/WP-12-RELEASE-READINESS.md',
  'docs/production-roadmap/evidence/WP-12-LEGACY-RETIREMENT-INVENTORY.md',
]);

const privateRoutes = {
  'linkautowork-operator-n8n': {
    dns: '<OPERATOR_N8N_DNS_NAME>', service: 'linkautowork-n8n', url: 'http://<N8N_PRIVATE_ADDRESS>:5678',
  },
  'linkautowork-operator-console': {
    dns: '<OPERATOR_CONSOLE_DNS_NAME>', service: 'linkautowork-operator-console', url: 'http://<OPERATOR_CONSOLE_PRIVATE_ADDRESS>:8080',
  },
};

const publicRoutes = {
  'linkautowork-client-web': {
    dns: '<PUBLIC_CLIENT_DNS_NAME>', service: 'linkautowork-client-web', url: 'http://<CLIENT_WEB_PRIVATE_ADDRESS>:8080',
  },
  'linkautowork-product-api': {
    dns: '<PUBLIC_PRODUCT_API_DNS_NAME>', service: 'linkautowork-product-api', url: 'http://<PRODUCT_API_PRIVATE_ADDRESS>:8080',
  },
};

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function exactly(value, expected) {
  return JSON.stringify(value) === JSON.stringify(expected);
}

function parseYamlDocument(content, label, violations) {
  try {
    const document = yaml.load(content);
    if (!isRecord(document)) violations.push(`${label}-not-a-mapping`);
    return document;
  } catch (error) {
    violations.push(`${label}-invalid-yaml:${error instanceof Error ? error.message : 'parse error'}`);
    return null;
  }
}

function validateRoute(routers, routeName, specification, violations, privateRoute) {
  const route = routers?.[routeName];
  if (!isRecord(route)) {
    violations.push(`private-ingress-missing-route:${routeName}`);
    return;
  }
  if (route.rule !== `Host(\`${specification.dns}\`)`) violations.push(`private-ingress-route-authority:${routeName}`);
  if (!exactly(route.entryPoints, ['websecure'])) violations.push(`private-ingress-route-entrypoint:${routeName}`);
  if (privateRoute && !exactly(route.middlewares, ['linkautowork-tailscale-only'])) violations.push(`private-ingress-route-middleware:${routeName}`);
  if (!privateRoute && route.middlewares !== undefined) violations.push(`private-ingress-public-route-middleware:${routeName}`);
  if (route.service !== specification.service) violations.push(`private-ingress-route-service:${routeName}`);
  if (!isRecord(route.tls) || route.tls.certResolver !== '<APPROVED_TLS_RESOLVER>') violations.push(`private-ingress-route-tls:${routeName}`);
}

function validateService(services, serviceName, expectedUrl, violations) {
  const service = services?.[serviceName];
  const servers = service?.loadBalancer?.servers;
  if (!isRecord(service) || !isRecord(service.loadBalancer) || !Array.isArray(servers) || servers.length !== 1) {
    violations.push(`private-ingress-service-shape:${serviceName}`);
    return;
  }
  if (!isRecord(servers[0]) || servers[0].url !== expectedUrl) violations.push(`private-ingress-service-upstream:${serviceName}`);
}

function parseEnvTemplate(content, violations) {
  const values = {};
  for (const [index, line] of content.split(/\r?\n/).entries()) {
    if (!line.trim() || line.trim().startsWith('#')) continue;
    const separator = line.indexOf('=');
    if (separator < 1) {
      violations.push(`private-ingress-input-invalid-line:${index + 1}`);
      continue;
    }
    values[line.slice(0, separator)] = line.slice(separator + 1);
  }
  return values;
}

function exposesNatsPort(server) {
  if (!isRecord(server) || typeof server.url !== 'string' || !server.url || server.url.trim() !== server.url || /[\u0000-\u0020\u007f]/.test(server.url)) return true;
  const parseableUrl = server.url.replace(/<[A-Za-z0-9_.-]+>/g, 'placeholder');
  try {
    const upstream = new URL(parseableUrl);
    if (!upstream.hostname) return true;
    return upstream.port === '4222' || upstream.port === '8222';
  } catch {
    return true;
  }
}

/** Validate the provider-neutral Traefik and Tailscale ingress topology. */
export function validatePrivateIngressTemplates(traefikContent, tailscaleContent) {
  const violations = [];
  const traefik = parseYamlDocument(traefikContent, 'private-ingress-template', violations);
  const tailscale = parseEnvTemplate(tailscaleContent, violations);
  if (!traefik) return violations;

  const routers = traefik.http?.routers;
  const services = traefik.http?.services;
  const middleware = traefik.http?.middlewares?.['linkautowork-tailscale-only'];
  if (!isRecord(routers)) violations.push('private-ingress-routers-not-a-mapping');
  if (!isRecord(services)) violations.push('private-ingress-services-not-a-mapping');
  if (!isRecord(middleware) || !isRecord(middleware.ipAllowList) || !exactly(middleware.ipAllowList.sourceRange, ['<TAILSCALE_CIDR>'])) violations.push('private-ingress-tailscale-policy');

  for (const [routeName, specification] of Object.entries(privateRoutes)) {
    validateRoute(routers, routeName, specification, violations, true);
    validateService(services, specification.service, specification.url, violations);
  }
  for (const [routeName, specification] of Object.entries(publicRoutes)) {
    validateRoute(routers, routeName, specification, violations, false);
    validateService(services, specification.service, specification.url, violations);
  }

  const serviceNames = isRecord(services) ? Object.keys(services) : [];
  if (serviceNames.some((name) => /nats/i.test(name))) violations.push('private-ingress-exposes-nats');
  for (const service of Object.values(isRecord(services) ? services : {})) {
    const urls = service?.loadBalancer?.servers;
    if (urls !== undefined && (!Array.isArray(urls) || urls.some(exposesNatsPort))) violations.push('private-ingress-exposes-nats');
  }

  const expectedInputs = {
    TAILSCALE_AUTH_KEY_SECRET_NAME: '<APPROVED_GSM_SECRET_NAME>',
    TAILSCALE_OPERATOR_CIDR: '<TAILSCALE_CIDR>',
    TRAEFIK_OPERATOR_DNS_NAME: '<OPERATOR_N8N_DNS_NAME>',
    TRAEFIK_OPERATOR_CONSOLE_DNS_NAME: '<OPERATOR_CONSOLE_DNS_NAME>',
    TRAEFIK_PUBLIC_CLIENT_DNS_NAME: '<PUBLIC_CLIENT_DNS_NAME>',
    PUBLIC_PRODUCT_API_DNS_NAME: '<PUBLIC_PRODUCT_API_DNS_NAME_OR_NOT_EXPOSED>',
    GATEWAY_PRIVATE_ADDRESS: '<GATEWAY_PRIVATE_ADDRESS>',
    N8N_PRIVATE_ADDRESS: '<N8N_PRIVATE_ADDRESS>',
  };
  for (const [key, expected] of Object.entries(expectedInputs)) if (tailscale[key] !== expected) violations.push(`private-ingress-input-authority:${key}`);
  return violations;
}

/** Validate a Compose document's private, persistent NATS contract. */
export function validatePrivatePersistentNats(relative, content, volume) {
  const violations = [];
  const compose = parseYamlDocument(content, `compose:${relative}`, violations);
  const nats = compose?.services?.nats;
  if (!isRecord(nats)) {
    violations.push(`compose-missing-service:${relative}:nats`);
    return violations;
  }
  if (nats.ports !== undefined) violations.push(`compose-nats-public:${relative}`);
  if (!exactly(nats.command, ['-js', '-sd', '/data'])) violations.push(`compose-nats-not-persistent:${relative}`);
  if (!Array.isArray(nats.volumes) || !nats.volumes.includes(`${volume}:/data`)) violations.push(`compose-nats-missing-volume:${relative}`);
  return violations;
}

function filesAt(root, relative) {
  const absolute = path.join(root, relative);
  if (!fs.existsSync(absolute)) return [];
  if (fs.statSync(absolute).isFile()) return [relative];
  return fs.readdirSync(absolute, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => path.relative(root, path.join(entry.parentPath, entry.name)));
}

/** Collect deterministic source-level release-readiness violations. */
export function collectReleaseReadinessViolations(root = process.cwd()) {
  const violations = [];
  for (const supportedRoot of supportedRoots) {
    for (const file of filesAt(root, supportedRoot)) {
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
    const compose = parseYamlDocument(content, 'compose:deploy/prod/docker-compose.yml', violations);
    const services = compose?.services;
    for (const service of ['nats', 'gateway', 'n8n', 'product-api', 'client-web', 'operator-console', 'migration-preflight', 'certified-package-publisher', 'operations-scheduler']) if (!isRecord(services?.[service])) violations.push(`compose-missing-service:${service}`);
    if (isRecord(services) && !services.nats?.volumes?.includes('nats_jetstream_prod:/data')) violations.push('compose-missing-persistent-jetstream');
    if (/traefik\.http\.routers\./.test(content)) violations.push('compose-has-inline-traefik-router');
    if (/image:\s*[^\n]*:latest\b/i.test(content)) violations.push('compose-uses-latest-image');
  }

  for (const [relative, volume] of [['deploy/dev/docker-compose.yml', 'nats_jetstream_dev'], ['deploy/prod/docker-compose.yml', 'nats_jetstream_prod']]) {
    const absolute = path.join(root, relative);
    if (fs.existsSync(absolute)) violations.push(...validatePrivatePersistentNats(relative, fs.readFileSync(absolute, 'utf8'), volume));
  }

  const traefikTemplate = path.join(root, 'deploy/templates/traefik-dynamic.yml.example');
  const tailscaleTemplate = path.join(root, 'deploy/templates/tailscale-boundary.env.example');
  if (fs.existsSync(traefikTemplate) && fs.existsSync(tailscaleTemplate)) violations.push(...validatePrivateIngressTemplates(fs.readFileSync(traefikTemplate, 'utf8'), fs.readFileSync(tailscaleTemplate, 'utf8')));
  return violations;
}

function main() {
  const violations = collectReleaseReadinessViolations();
  if (violations.length) {
    console.error(`Release-readiness check failed:\n${violations.map((item) => `- ${item}`).join('\n')}`);
    process.exitCode = 1;
    return;
  }
  console.log('Release-readiness check passed: supported surfaces have no retired runtime path and required release artifacts exist.');
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) main();
