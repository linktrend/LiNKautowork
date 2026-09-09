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

function rejectUnexpectedKeys(value, expected, violationPrefix, violations) {
  if (!isRecord(value)) return;
  for (const key of Object.keys(value)) {
    if (!expected.includes(key)) violations.push(`${violationPrefix}:${key}`);
  }
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
  rejectUnexpectedKeys(
    route,
    privateRoute ? ['rule', 'entryPoints', 'middlewares', 'service', 'tls'] : ['rule', 'entryPoints', 'service', 'tls'],
    `private-ingress-route-unexpected-key:${routeName}`,
    violations,
  );
  if (route.rule !== `Host(\`${specification.dns}\`)`) violations.push(`private-ingress-route-authority:${routeName}`);
  if (!exactly(route.entryPoints, ['websecure'])) violations.push(`private-ingress-route-entrypoint:${routeName}`);
  if (privateRoute && !exactly(route.middlewares, ['linkautowork-tailscale-only'])) violations.push(`private-ingress-route-middleware:${routeName}`);
  if (!privateRoute && route.middlewares !== undefined) violations.push(`private-ingress-public-route-middleware:${routeName}`);
  if (route.service !== specification.service) violations.push(`private-ingress-route-service:${routeName}`);
  if (!isRecord(route.tls) || route.tls.certResolver !== '<APPROVED_TLS_RESOLVER>') violations.push(`private-ingress-route-tls:${routeName}`);
  rejectUnexpectedKeys(route.tls, ['certResolver'], `private-ingress-route-tls-unexpected-key:${routeName}`, violations);
}

function validateService(services, serviceName, expectedUrl, violations) {
  const service = services?.[serviceName];
  const servers = service?.loadBalancer?.servers;
  if (!isRecord(service) || !isRecord(service.loadBalancer) || !Array.isArray(servers) || servers.length !== 1) {
    violations.push(`private-ingress-service-shape:${serviceName}`);
    return;
  }
  rejectUnexpectedKeys(service, ['loadBalancer'], `private-ingress-service-unexpected-key:${serviceName}`, violations);
  rejectUnexpectedKeys(service.loadBalancer, ['servers'], `private-ingress-load-balancer-unexpected-key:${serviceName}`, violations);
  rejectUnexpectedKeys(servers[0], ['url'], `private-ingress-upstream-unexpected-key:${serviceName}`, violations);
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

  for (const protocol of ['tcp', 'udp']) {
    if (Object.prototype.hasOwnProperty.call(traefik, protocol)) violations.push(`private-ingress-unexpected-protocol:${protocol}`);
  }
  const http = traefik.http;
  rejectUnexpectedKeys(http, ['routers', 'middlewares', 'services'], 'private-ingress-unexpected-http-section', violations);
  const routers = traefik.http?.routers;
  const services = traefik.http?.services;
  const middlewares = traefik.http?.middlewares;
  const middleware = traefik.http?.middlewares?.['linkautowork-tailscale-only'];
  if (!isRecord(routers)) violations.push('private-ingress-routers-not-a-mapping');
  if (!isRecord(services)) violations.push('private-ingress-services-not-a-mapping');
  if (!isRecord(middleware) || !isRecord(middleware.ipAllowList) || !exactly(middleware.ipAllowList.sourceRange, ['<TAILSCALE_CIDR>'])) violations.push('private-ingress-tailscale-policy');
  rejectUnexpectedKeys(middlewares, ['linkautowork-tailscale-only'], 'private-ingress-unexpected-middleware', violations);
  rejectUnexpectedKeys(middleware, ['ipAllowList'], 'private-ingress-middleware-unexpected-key', violations);
  rejectUnexpectedKeys(middleware?.ipAllowList, ['sourceRange'], 'private-ingress-ip-allow-list-unexpected-key', violations);

  const expectedRouterNames = [...Object.keys(privateRoutes), ...Object.keys(publicRoutes)];
  const expectedServiceNames = [...Object.values(privateRoutes), ...Object.values(publicRoutes)].map(({ service }) => service);
  rejectUnexpectedKeys(routers, expectedRouterNames, 'private-ingress-unexpected-router', violations);
  rejectUnexpectedKeys(services, expectedServiceNames, 'private-ingress-unexpected-service', violations);

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
  if (nats.network_mode !== undefined) violations.push(`compose-nats-host-network:${relative}`);
  if ((Array.isArray(nats.networks) && nats.networks.includes('host'))
    || (isRecord(nats.networks) && Object.prototype.hasOwnProperty.call(nats.networks, 'host'))
    || nats.networks === 'host') {
    violations.push(`compose-nats-host-network:${relative}`);
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

function commandTokens(command) {
  if (Array.isArray(command)) return command.map(String);
  if (typeof command === 'string') return command.trim().split(/\s+/).filter(Boolean);
  return [];
}

function publishesHostPorts(service) {
  if (!isRecord(service) || service.ports === undefined) return false;
  if (Array.isArray(service.ports)) return service.ports.length > 0;
  return true;
}

function portMappingMentions(ports, port) {
  const needle = String(port);
  if (!Array.isArray(ports)) return false;
  return ports.some((entry) => {
    if (typeof entry === 'string' || typeof entry === 'number') return String(entry).includes(needle);
    if (!isRecord(entry)) return false;
    return [entry.published, entry.target, entry.host_port].some((value) => String(value ?? '') === needle);
  });
}

function natsHttpMonitorEnabled(nats) {
  const tokens = commandTokens(nats?.command);
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === '-m' || token === '--http_port' || token.startsWith('--http_port=')) return true;
  }
  return portMappingMentions(nats?.ports, '8222');
}

/** Read the production Compose invariants the approved deployment docs must match. */
export function readProductionComposeDocContract(compose) {
  const services = isRecord(compose?.services) ? compose.services : {};
  const n8n = services.n8n;
  const nats = services.nats;
  return {
    serviceNames: Object.keys(services),
    n8nPublishesHostPort: publishesHostPorts(n8n),
    natsPublishesHostPort: publishesHostPorts(nats),
    natsHttpMonitorEnabled: natsHttpMonitorEnabled(nats),
  };
}

function splitProseUnits(text) {
  return String(text)
    .split(/\n+/)
    .flatMap((line) => line.split(/(?<=[.!?])\s+/))
    .map((unit) => unit.trim())
    .filter(Boolean);
}

function unitDeniesClaim(unit) {
  return /\b(?:is not|are not|does not|do not|did not|never|no longer|not a|not an|neither|nor)\b/i.test(unit)
    || /\b(?:publishes|publish|enable[sd]?)\s+no\b/i.test(unit)
    || /\bno\s+(?:host\s+port|n8n host|HTTP monitor|NATS host)\b/i.test(unit)
    || /\bnot enable(?:s|d)?\b/i.test(unit);
}

function claimsDirectN8nHostFallback(text) {
  const units = splitProseUnits(text);
  for (const unit of units) {
    if (!/(?<!\d)5678\b/.test(unit) || unitDeniesClaim(unit)) continue;
    const fallback = /\bfallbacks?\b/i.test(unit);
    const direct = /\bdirect\b/i.test(unit);
    const hostPublish = /\bhost(?:-|\s+)ports?\b|\bpublish(?:es|ed|ing)?\b/i.test(unit);
    if (fallback || (direct && (hostPublish || /\bN8N_TAILSCALE_IP\b/.test(unit)))) return true;
  }
  const positive = splitProseUnits(text).filter((unit) => !unitDeniesClaim(unit)).join(' ');
  return /direct[^.\n]{0,80}(?<!\d)5678\b[^.\n]{0,80}\bfallback/i.test(positive)
    || /\bfallback[^.\n]{0,80}(?<!\d)5678\b/i.test(positive);
}

function claimsSharedThreeServiceTopology(text) {
  const units = splitProseUnits(text).filter((unit) => !unitDeniesClaim(unit));
  const body = units.join('\n');
  if (/\bsame three services\b/i.test(body)) return true;
  if (/\bshare(?:s|d)? the same three\b/i.test(body)) return true;
  return /both environments[\s\S]{0,120}three services/i.test(body)
    || /three services[\s\S]{0,120}both environments/i.test(body);
}

function claimsProductionNatsHttpMonitor(text) {
  for (const unit of splitProseUnits(text)) {
    if (!/(?<!\d)8222\b/.test(unit) || unitDeniesClaim(unit)) continue;
    if (/\bmonitor\b|\bhttp_port\b|\bNATS\b/i.test(unit)) return true;
  }
  return false;
}

/**
 * Fail closed when approved deployment prose contradicts production Compose
 * on n8n host publish, service topology, or NATS HTTP monitor.
 */
export function validateProductionComposeDocContract(root = process.cwd()) {
  const violations = [];
  const composePath = path.join(root, 'deploy/prod/docker-compose.yml');
  const approvedDocs = {
    'docs/runbooks/TAILSCALE_HARDENING.md': path.join(root, 'docs/runbooks/TAILSCALE_HARDENING.md'),
    'docs/runbooks/OPERATIONS.md': path.join(root, 'docs/runbooks/OPERATIONS.md'),
    'docs/LINKAUTOWORK-TECHNICAL-PRD.md': path.join(root, 'docs/LINKAUTOWORK-TECHNICAL-PRD.md'),
  };
  for (const [relative, absolute] of Object.entries(approvedDocs)) {
    if (!fs.existsSync(absolute)) violations.push(`missing:${relative}`);
  }
  if (!fs.existsSync(composePath)) {
    violations.push('missing:deploy/prod/docker-compose.yml');
    return violations;
  }

  const compose = parseYamlDocument(fs.readFileSync(composePath, 'utf8'), 'compose:deploy/prod/docker-compose.yml', violations);
  const contract = readProductionComposeDocContract(compose);
  const texts = Object.fromEntries(
    Object.entries(approvedDocs)
      .filter(([, absolute]) => fs.existsSync(absolute))
      .map(([relative, absolute]) => [relative, fs.readFileSync(absolute, 'utf8')]),
  );
  const combinedRunbooks = `${texts['docs/runbooks/TAILSCALE_HARDENING.md'] ?? ''}\n${texts['docs/runbooks/OPERATIONS.md'] ?? ''}`;
  const prd = texts['docs/LINKAUTOWORK-TECHNICAL-PRD.md'] ?? '';
  const approvedProse = `${combinedRunbooks}\n${prd}`;

  if (contract.n8nPublishesHostPort) {
    violations.push('compose-n8n-public-host-port');
  } else if (claimsDirectN8nHostFallback(approvedProse)) {
    violations.push('doc-contract-n8n-host-port-fallback: production Compose publishes no n8n host port; deploy-stack only rewrites n8n URL variables');
  }

  if (contract.serviceNames.length !== 0 && claimsSharedThreeServiceTopology(prd) && contract.serviceNames.length !== 3) {
    violations.push(`doc-contract-shared-three-services: production Compose defines ${contract.serviceNames.length} services (${contract.serviceNames.join(', ')})`);
  }
  for (const service of contract.serviceNames) {
    const mentioned = new RegExp(`\\b${service.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`).test(prd);
    if (!mentioned) violations.push(`doc-contract-missing-production-service:${service}`);
  }

  if (contract.natsHttpMonitorEnabled || (contract.natsPublishesHostPort && portMappingMentions(compose?.services?.nats?.ports, '8222'))) {
    violations.push('compose-nats-http-monitor');
  } else if (claimsProductionNatsHttpMonitor(approvedProse)) {
    violations.push('doc-contract-nats-http-monitor: production Compose neither enables nor publishes the NATS HTTP monitor on :8222');
  }

  return violations;
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

  violations.push(...validateProductionComposeDocContract(root));

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
