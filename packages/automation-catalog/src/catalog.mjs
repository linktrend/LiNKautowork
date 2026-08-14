import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const SCHEMA_FILES = {
  package: 'automation-package-v0.1.schema.json',
  intake: 'automation-intake-v0.1.schema.json',
  provenance: 'provenance-sources-v0.1.schema.json',
  eval: 'automation-eval-suite-v0.1.schema.json',
  monitoring: 'monitoring-profile-v0.1.schema.json',
  maintenance: 'maintenance-policy-v0.1.schema.json',
  deployment: 'deployment-profile-v0.1.schema.json',
};

const REQUIRED_REFERENCES = [
  ['contracts.input_schema_ref', ['contracts', 'input_schema_ref']],
  ['contracts.output_schema_ref', ['contracts', 'output_schema_ref']],
  ['contracts.configuration_schema_ref', ['contracts', 'configuration_schema_ref']],
  ['evaluation.suite_ref', ['evaluation', 'suite_ref']],
  ['operations.monitoring_ref', ['operations', 'monitoring_ref']],
  ['operations.maintenance_ref', ['operations', 'maintenance_ref']],
  ['operations.deployment_ref', ['operations', 'deployment_ref']],
  ['operations.runbook_ref', ['operations', 'runbook_ref']],
  ['provenance.sources_ref', ['provenance', 'sources_ref']],
  ['runtime.workflow_ref', ['runtime', 'workflow_ref']],
];

const JSON_SCHEMA_REFS = new Set([
  'contracts.input_schema_ref',
  'contracts.output_schema_ref',
  'contracts.configuration_schema_ref',
]);

const TRIGGER_NODES = {
  webhook: new Set(['n8n-nodes-base.webhook']),
  schedule: new Set(['n8n-nodes-base.scheduleTrigger', 'n8n-nodes-base.cron']),
  manual: new Set(['n8n-nodes-base.manualTrigger']),
  event: new Set(['n8n-nodes-base.natsTrigger', 'n8n-nodes-base.rabbitmqTrigger']),
};

// GAP v0.1 has a concrete, inspectable graph contract for synchronous webhook
// responses only. Generic HTTP/NATS nodes are not accepted as callback/event
// emitters because their destinations and completion semantics are not governed.
const CLOSED_RESULT_MODES = new Map([
  ['callback', 'callback result_mode is unavailable in GAP v0.1 until a controlled callback emitter and parameter contract exist'],
  ['event', 'event result_mode is unavailable in GAP v0.1 until a controlled event emitter and parameter contract exist'],
]);

const SECRET_VALUE_PATTERNS = [
  /-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----/i,
  /(?:postgres|postgresql|mysql|mongodb(?:\+srv)?):\/\/[^\s/:]+:[^\s@]+@/i,
  /\bBearer\s+[A-Za-z0-9._~+\/-]{12,}\b/,
  /\bAKIA[0-9A-Z]{16}\b/,
];

const FORBIDDEN_VALUE_KEYS = new Set([
  'credential', 'credentials', 'password', 'passphrase', 'access_token',
  'accessToken', 'refresh_token', 'refreshToken', 'api_key', 'apiKey',
  'private_key', 'privateKey', 'secret_value', 'secretValue',
]);

function issue(code, file, message) {
  return { code, file, message };
}

function readJson(file) {
  try {
    return { value: JSON.parse(fs.readFileSync(file, 'utf8')), errors: [] };
  } catch {
    return { value: undefined, errors: [issue('invalid_json', file, 'must contain valid JSON')] };
  }
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

/** Returns bounded, authorization-filtered catalogue metadata; it never exposes workflow or package payloads. */
export function listProviderCatalogue(entries, { orgId, capabilities = [] }) {
  const granted = new Set(capabilities);
  return entries.filter((entry) => entry.org_id === orgId && granted.has(entry.capability) && entry.lifecycle === 'available')
    .map(({ automation_id, version, digest, owner, lifecycle, capability, purpose }) => ({ automation_id, version, digest, owner, lifecycle, capability, purpose }));
}

/** Resolves one caller-selected immutable version and rejects implicit latest/deprecated substitutions. */
export function getProviderCatalogueDetail(entries, { orgId, capability, automationId, version }) {
  if (!version) throw new Error('exact automation version is required');
  const entry = entries.find((candidate) => candidate.org_id === orgId && candidate.capability === capability && candidate.automation_id === automationId && candidate.version === version);
  if (!entry) throw new Error('automation version is unavailable');
  if (entry.lifecycle !== 'available') throw new Error(`automation version is ${entry.lifecycle}`);
  const { workflow, payload, logs, ...detail } = entry;
  return detail;
}

export function isSafeRelativePath(reference) {
  if (typeof reference !== 'string' || !reference || path.isAbsolute(reference)) return false;
  const normalized = path.posix.normalize(reference.replace(/\\/g, '/'));
  return normalized !== '..' && !normalized.startsWith('../') && !normalized.includes('/../');
}

function resolveReference(packageDir, reference) {
  if (!isSafeRelativePath(reference)) return undefined;
  const root = fs.realpathSync(packageDir);
  const resolved = path.resolve(root, reference);
  if (!(resolved.startsWith(`${root}${path.sep}`) || resolved === root)) return undefined;
  // A lexically safe path can still escape through a symlink. Resolve the real
  // target whenever it exists so only files physically inside the package count.
  if (!fs.existsSync(resolved)) return resolved;
  const real = fs.realpathSync(resolved);
  return real.startsWith(`${root}${path.sep}`) || real === root ? real : undefined;
}

function nestedValue(object, keys) {
  return keys.reduce((current, key) => current?.[key], object);
}

function listFiles(dir, relative = '') {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true })
    .flatMap((entry) => {
      const rel = path.posix.join(relative, entry.name);
      const full = path.join(dir, entry.name);
      return entry.isDirectory() ? listFiles(full, rel) : [rel];
    })
    .sort();
}

function packageGovernedPaths(packageDir) {
  const candidates = [
    'automation.json',
    'workflow.json',
    ...listFiles(path.join(packageDir, 'contracts'), 'contracts').filter((file) => file.endsWith('.json')),
    ...listFiles(path.join(packageDir, 'evals'), 'evals').filter((file) => file.endsWith('.json')),
    'operations/monitoring.json',
    'operations/maintenance.json',
    'operations/deployment.json',
    'provenance/sources.json',
  ];
  return [...new Set(candidates)]
    .filter((file) => !file.startsWith('evals/evidence/') && !file.startsWith('evals/receipts/') && file !== 'evals/certification-receipt.json')
    .sort();
}

/** Returns the WP-01 defined digest over governed package inputs. */
export function calculatePackageDigest(packageDir) {
  const stream = crypto.createHash('sha256');
  for (const relative of packageGovernedPaths(packageDir)) {
    const full = path.join(packageDir, relative);
    if (!fs.existsSync(full)) throw new Error(`missing governed file ${relative}`);
    const parsed = readJson(full);
    if (parsed.errors.length) throw new Error(`invalid JSON in governed file ${relative}`);
    if (relative === 'automation.json') {
      parsed.value.release ??= {};
      parsed.value.release.identity ??= {};
      parsed.value.release.identity.package_digest = 'sha256:__excluded__';
    }
    stream.update(relative);
    stream.update('\0');
    stream.update(sha256(`${canonicalJson(parsed.value)}\n`));
    stream.update('\0');
  }
  return `sha256:${stream.digest('hex')}`;
}

export function calculateWorkflowDigest(packageDir, workflowRef = 'workflow.json') {
  const workflow = resolveReference(packageDir, workflowRef);
  if (!workflow || !fs.existsSync(workflow)) throw new Error('missing workflow source');
  return `sha256:${sha256(fs.readFileSync(workflow))}`;
}

export function createSchemaValidator(repoRoot) {
  const schemaDir = path.join(repoRoot, 'automations', 'schemas');
  const ajv = new Ajv2020({ allErrors: true, strict: true, validateFormats: true });
  addFormats(ajv);
  for (const filename of Object.values(SCHEMA_FILES)) {
    const loaded = readJson(path.join(schemaDir, filename));
    if (loaded.errors.length) throw new Error(`unable to load schema ${filename}`);
    ajv.addSchema(loaded.value);
  }
  return ajv;
}

function schemaId(kind) {
  return `https://linktrend.dev/schemas/linkautowork/${SCHEMA_FILES[kind]}`;
}

function validateWithSchema(ajv, kind, value, file) {
  const validate = ajv.getSchema(schemaId(kind));
  if (!validate) throw new Error(`schema was not loaded: ${kind}`);
  if (validate(value)) return [];
  return (validate.errors ?? []).map((error) => issue(
    'schema_validation',
    file,
    `${error.instancePath || '/'} ${error.message ?? 'fails schema validation'}`,
  ));
}

function validateSchemaDocument(ajv, value, file) {
  if (ajv.validateSchema(value)) return [];
  return (ajv.errors ?? []).map((error) => issue('invalid_contract_schema', file, `${error.instancePath || '/'} ${error.message ?? 'is not valid JSON Schema'}`));
}

function scanValue(value, file, pointer = '', parentKey = '') {
  const errors = [];
  if (typeof value === 'string') {
    if (SECRET_VALUE_PATTERNS.some((pattern) => pattern.test(value))) {
      errors.push(issue('secret_like_content', file, `${pointer || '/'} contains prohibited secret-like content`));
    }
    return errors;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => errors.push(...scanValue(item, file, `${pointer}/${index}`, parentKey)));
    return errors;
  }
  if (!value || typeof value !== 'object') return errors;
  for (const [key, child] of Object.entries(value)) {
    const childPointer = `${pointer}/${key}`;
    if (FORBIDDEN_VALUE_KEYS.has(key)) {
      errors.push(issue('secret_like_field', file, `${childPointer} is not permitted in a package source document`));
      continue;
    }
    errors.push(...scanValue(child, file, childPointer, key));
  }
  return errors;
}

function scanPackageSources(packageDir) {
  const errors = [];
  for (const relative of listFiles(packageDir).filter((file) => file.endsWith('.json'))) {
    const full = path.join(packageDir, relative);
    const loaded = readJson(full);
    if (loaded.errors.length) {
      errors.push(...loaded.errors);
      continue;
    }
    errors.push(...scanValue(loaded.value, relative));
  }
  return errors;
}

function validateReferences(packageDir, manifest, ajv) {
  const errors = [];
  for (const [label, keys] of REQUIRED_REFERENCES) {
    const reference = nestedValue(manifest, keys);
    const full = resolveReference(packageDir, reference);
    if (!full || !fs.existsSync(full)) {
      errors.push(issue('missing_reference', 'automation.json', `${label} must resolve to an existing package file`));
      continue;
    }
    if (JSON_SCHEMA_REFS.has(label)) {
      const loaded = readJson(full);
      errors.push(...loaded.errors.map((entry) => ({ ...entry, file: label })));
      if (!loaded.errors.length) errors.push(...validateSchemaDocument(ajv, loaded.value, label));
    }
  }
  const suiteRef = manifest.evaluation?.suite_ref;
  const suitePath = resolveReference(packageDir, suiteRef);
  if (suitePath && fs.existsSync(suitePath)) {
    const suite = readJson(suitePath);
    errors.push(...suite.errors.map((entry) => ({ ...entry, file: suiteRef })));
    if (!suite.errors.length) {
      errors.push(...validateWithSchema(ajv, 'eval', suite.value, suiteRef));
      for (const testCase of suite.value.cases ?? []) {
        const fixture = resolveReference(path.dirname(suitePath), testCase.fixture_ref);
        if (!fixture || !fs.existsSync(fixture)) errors.push(issue('missing_fixture', suiteRef, `eval case ${testCase.case_id} has an unresolved fixture_ref`));
      }
    }
  }
  const documentRefs = [
    ['monitoring', manifest.operations?.monitoring_ref],
    ['maintenance', manifest.operations?.maintenance_ref],
    ['deployment', manifest.operations?.deployment_ref],
    ['provenance', manifest.provenance?.sources_ref],
  ];
  for (const [kind, reference] of documentRefs) {
    const full = resolveReference(packageDir, reference);
    if (!full || !fs.existsSync(full)) continue;
    const loaded = readJson(full);
    errors.push(...loaded.errors.map((entry) => ({ ...entry, file: reference })));
    if (!loaded.errors.length) errors.push(...validateWithSchema(ajv, kind, loaded.value, reference));
  }
  return errors;
}

function validateProvenance(packageDir, manifest) {
  const errors = [];
  const sourceFile = resolveReference(packageDir, manifest.provenance?.sources_ref);
  if (!sourceFile || !fs.existsSync(sourceFile)) return errors;
  const source = readJson(sourceFile);
  if (source.errors.length) return source.errors;
  const provenance = source.value;
  if (provenance.automation_id !== manifest.automation_id) {
    errors.push(issue('provenance_identity_mismatch', manifest.provenance.sources_ref, 'provenance automation_id must match automation.json'));
  }
  if (provenance.automation_version !== manifest.release?.version) {
    errors.push(issue('provenance_identity_mismatch', manifest.provenance.sources_ref, 'provenance automation_version must match automation.json release.version'));
  }
  if (provenance.required_runtime?.engine !== manifest.runtime?.engine || provenance.required_runtime?.n8n_version !== manifest.release?.identity?.n8n_version) {
    errors.push(issue('provenance_runtime_mismatch', manifest.provenance.sources_ref, 'provenance required_runtime must match the package runtime identity'));
  }
  const sourcesById = new Map((provenance.sources ?? []).map((entry) => [entry.source_id, entry]));
  const mapKeys = new Set();
  for (const mapping of provenance.source_to_target_map ?? []) {
    const sourceRecord = sourcesById.get(mapping.source_id);
    const mapKey = `${mapping.source_id}\u0000${mapping.source_component_ref}\u0000${mapping.target_component_ref}`;
    if (mapKeys.has(mapKey)) errors.push(issue('duplicate_source_target_mapping', manifest.provenance.sources_ref, 'source-to-target mappings must be unique'));
    mapKeys.add(mapKey);
    if (!sourceRecord) {
      errors.push(issue('unknown_mapping_source', manifest.provenance.sources_ref, 'each source-to-target mapping must name a declared source'));
    } else if (sourceRecord.content_digest !== mapping.source_content_digest) {
      errors.push(issue('source_hash_mismatch', manifest.provenance.sources_ref, 'mapping source_content_digest must exactly match the declared source hash'));
    }
  }
  for (const sourceRecord of provenance.sources ?? []) {
    if (!(provenance.source_to_target_map ?? []).some((mapping) => mapping.source_id === sourceRecord.source_id)) {
      errors.push(issue('unmapped_provenance_source', manifest.provenance.sources_ref, 'every declared source requires at least one source-to-target mapping'));
    }
  }
  const commercial = manifest.ownership?.classification === 'commercial_capable';
  if (commercial && manifest.provenance?.commercial_use_clearance !== 'cleared') {
    errors.push(issue('commercial_clearance_required', 'automation.json', 'commercial-capable automation requires commercial_use_clearance=cleared'));
  }
  if (commercial && (provenance.sources ?? []).some((entry) => entry.commercial_use !== 'allowed')) {
    errors.push(issue('commercial_source_not_cleared', manifest.provenance.sources_ref, 'commercial-capable automation requires all source records to allow commercial use'));
  }
  if (!['cleared', 'not_applicable'].includes(provenance.review?.status)) {
    errors.push(issue('unresolved_provenance', manifest.provenance.sources_ref, 'source review must be cleared or not_applicable'));
  }
  return errors;
}

function validateWorkflowGraph(packageDir, manifest) {
  const errors = [];
  const workflowRef = manifest.runtime?.workflow_ref;
  const full = resolveReference(packageDir, workflowRef);
  if (!full || !fs.existsSync(full)) return errors;
  const loaded = readJson(full);
  if (loaded.errors.length) return loaded.errors.map((entry) => ({ ...entry, file: workflowRef }));
  const workflow = loaded.value;
  if (!Array.isArray(workflow.nodes) || workflow.nodes.length === 0) {
    return [issue('invalid_workflow_graph', workflowRef, 'workflow must contain at least one node')];
  }
  const ids = new Set();
  const names = new Set();
  for (const node of workflow.nodes) {
    if (typeof node?.id !== 'string' || !node.id || ids.has(node.id)) errors.push(issue('duplicate_or_missing_node_id', workflowRef, 'workflow node IDs must be present and unique'));
    if (typeof node?.name !== 'string' || !node.name || names.has(node.name)) errors.push(issue('duplicate_or_missing_node_name', workflowRef, 'workflow node names must be present and unique'));
    if (node?.id) ids.add(node.id);
    if (node?.name) names.add(node.name);
    if (manifest.runtime?.approved_node_policy === 'n8n-core-only-v0.1' && typeof node?.type === 'string' && !node.type.startsWith('n8n-nodes-base.')) {
      errors.push(issue('unsupported_node_policy', workflowRef, 'workflow contains a node outside n8n-core-only-v0.1 policy'));
    }
  }
  for (const [sourceName, channels] of Object.entries(workflow.connections ?? {})) {
    if (!names.has(sourceName)) errors.push(issue('invalid_workflow_connection', workflowRef, 'connection source must name an existing node'));
    for (const channel of Object.values(channels ?? {})) {
      for (const branch of channel ?? []) {
        for (const edge of branch ?? []) {
          if (!names.has(edge?.node)) errors.push(issue('invalid_workflow_connection', workflowRef, 'connection target must name an existing node'));
        }
      }
    }
  }
  const mode = manifest.runtime?.trigger_mode;
  if (mode !== 'hybrid' && TRIGGER_NODES[mode]) {
    const hasTrigger = workflow.nodes.some((node) => TRIGGER_NODES[mode].has(node.type));
    if (!hasTrigger) errors.push(issue('missing_declared_trigger', workflowRef, `workflow must contain a ${mode} trigger node`));
  }
  const hasWebhookTrigger = workflow.nodes.some((node) => TRIGGER_NODES.webhook.has(node.type));
  const respondNodes = workflow.nodes.filter((node) => node.type === 'n8n-nodes-base.respondToWebhook');
  const resultMode = manifest.runtime?.result_mode;
  if (resultMode === 'synchronous_response' && (!hasWebhookTrigger || respondNodes.length !== 1)) {
    errors.push(issue('declared_result_behavior_mismatch', workflowRef, 'synchronous_response requires one webhook trigger and exactly one Respond to Webhook node'));
  }
  if (resultMode !== 'synchronous_response' && respondNodes.length > 0) {
    errors.push(issue('declared_result_behavior_mismatch', workflowRef, 'only synchronous_response packages may contain Respond to Webhook nodes'));
  }
  if (CLOSED_RESULT_MODES.has(resultMode)) {
    errors.push(issue('unsupported_result_behavior', workflowRef, CLOSED_RESULT_MODES.get(resultMode)));
  }
  return errors;
}

function validateIdentity(packageDir, manifest) {
  const errors = [];
  try {
    const packageDigest = calculatePackageDigest(packageDir);
    if (packageDigest !== manifest.release?.identity?.package_digest) errors.push(issue('package_digest_mismatch', 'automation.json', 'declared package_digest does not match governed package inputs'));
    const workflowDigest = calculateWorkflowDigest(packageDir, manifest.runtime?.workflow_ref);
    if (workflowDigest !== manifest.release?.identity?.workflow_digest) errors.push(issue('workflow_digest_mismatch', 'automation.json', 'declared workflow_digest does not match workflow source'));
  } catch (error) {
    errors.push(issue('identity_calculation_failed', 'automation.json', error instanceof Error ? error.message : 'unable to calculate release identity'));
  }
  return errors;
}

function validateCertificationReceipt(packageDir, manifest) {
  if (manifest.release?.lifecycle === 'certified') {
    return [issue('certification_receipt_unavailable', 'automation.json', 'certified releases are rejected until WP-06 provides a verifiable independent evaluation receipt')];
  }
  return [];
}

function validateCrossDocumentIdentity(packageDir, manifest) {
  const errors = [];
  const suiteRef = manifest.evaluation?.suite_ref;
  const suiteFile = resolveReference(packageDir, suiteRef);
  if (!suiteFile || !fs.existsSync(suiteFile)) return errors;
  const suite = readJson(suiteFile);
  if (suite.errors.length) return suite.errors.map((entry) => ({ ...entry, file: suiteRef }));
  if (suite.value.automation_id !== manifest.automation_id || suite.value.automation_version !== manifest.release?.version) {
    errors.push(issue('evaluation_identity_mismatch', suiteRef, 'evaluation automation_id and automation_version must match automation.json'));
  }
  if (suite.value.required_runtime?.engine !== manifest.runtime?.engine || suite.value.required_runtime?.n8n_version !== manifest.release?.identity?.n8n_version) {
    errors.push(issue('evaluation_runtime_mismatch', suiteRef, 'evaluation required_runtime must match the package runtime identity'));
  }
  return errors;
}

function validateDirectoryIdentity(repoRoot, packageDir, manifest) {
  const catalogRoot = path.join(repoRoot, 'automations', 'catalog');
  const relative = path.relative(catalogRoot, packageDir).split(path.sep);
  if (relative.length !== 2 || relative.some((part) => !part || part === '..')) return [];
  const [automationId, version] = relative;
  const errors = [];
  if (automationId !== manifest.automation_id) errors.push(issue('directory_automation_identity_mismatch', 'automation.json', 'catalogue directory automation ID must match automation.json'));
  if (version !== manifest.release?.version) errors.push(issue('directory_version_identity_mismatch', 'automation.json', 'catalogue directory version must match automation.json release.version'));
  return errors;
}

export function validatePackageDirectory({ repoRoot, packageDir, ajv = createSchemaValidator(repoRoot) }) {
  const manifestFile = path.join(packageDir, 'automation.json');
  const loaded = readJson(manifestFile);
  if (loaded.errors.length) return { packageDir, manifest: undefined, errors: loaded.errors };
  const manifest = loaded.value;
  const errors = [
    ...validateWithSchema(ajv, 'package', manifest, 'automation.json'),
    ...validateReferences(packageDir, manifest, ajv),
    ...validateWorkflowGraph(packageDir, manifest),
    ...validateProvenance(packageDir, manifest),
    ...validateCrossDocumentIdentity(packageDir, manifest),
    ...scanPackageSources(packageDir),
    ...validateIdentity(packageDir, manifest),
    ...validateCertificationReceipt(packageDir, manifest),
    ...validateDirectoryIdentity(repoRoot, packageDir, manifest),
  ];
  return { packageDir, manifest, errors };
}

export function discoverReleaseDirectories(repoRoot) {
  const root = path.join(repoRoot, 'automations', 'catalog');
  if (!fs.existsSync(root)) return [];
  return fs.readdirSync(root, { withFileTypes: true })
    .filter((definition) => definition.isDirectory())
    .flatMap((definition) => fs.readdirSync(path.join(root, definition.name), { withFileTypes: true })
      .filter((release) => release.isDirectory())
      .map((release) => path.join(root, definition.name, release.name)))
    .sort();
}

/** Validates every checked-in intake record, including the inactive intake template. */
export function validateIntakeRecords(repoRoot, ajv = createSchemaValidator(repoRoot)) {
  const root = path.join(repoRoot, 'automations', 'intake');
  const records = listFiles(root)
    .filter((file) => file.endsWith('.json'))
    .map((relative) => {
      const file = path.join(root, relative);
      const loaded = readJson(file);
      const errors = loaded.errors.length
        ? loaded.errors
        : validateWithSchema(ajv, 'intake', loaded.value, path.posix.join('automations/intake', relative));
      return { file: path.posix.join('automations/intake', relative), errors };
    });
  return { records, errors: records.flatMap((record) => record.errors.map((entry) => ({ ...entry, packageDir: record.file }))) };
}

export function validateCatalog(repoRoot) {
  const ajv = createSchemaValidator(repoRoot);
  const results = discoverReleaseDirectories(repoRoot).map((packageDir) => validatePackageDirectory({ repoRoot, packageDir, ajv }));
  const intake = validateIntakeRecords(repoRoot, ajv);
  const errors = [
    ...results.flatMap((result) => result.errors.map((entry) => ({ ...entry, packageDir: path.relative(repoRoot, result.packageDir) }))),
    ...intake.errors,
  ];
  const keys = new Set();
  for (const result of results.filter((entry) => entry.manifest)) {
    const key = `${result.manifest.automation_id}@${result.manifest.release.version}`;
    if (keys.has(key)) errors.push(issue('duplicate_release', path.relative(repoRoot, result.packageDir), 'automation ID and version must be unique in the catalogue'));
    keys.add(key);
  }
  return { results, intake: intake.records, errors };
}

function semverCompare(left, right) {
  const a = left.split(/[+-]/)[0].split('.').map(Number);
  const b = right.split(/[+-]/)[0].split('.').map(Number);
  return a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || left.localeCompare(right);
}

export function buildCatalogIndex(repoRoot) {
  const validation = validateCatalog(repoRoot);
  if (validation.errors.length) {
    const first = validation.errors[0];
    throw new Error(`${first.packageDir ?? ''} ${first.file}: ${first.code} ${first.message}`.trim());
  }
  const releases = validation.results.map(({ packageDir, manifest }) => ({
    automation_id: manifest.automation_id,
    version: manifest.release.version,
    lifecycle: manifest.release.lifecycle,
    channel: manifest.release.channel,
    display_name: manifest.display_name,
    summary: manifest.summary,
    owning_program: manifest.ownership.owning_program,
    classification: manifest.ownership.classification,
    binding_operations: [...manifest.ownership.binding_operations].sort(),
    runtime: { engine: manifest.runtime.engine, n8n_version: manifest.release.identity.n8n_version },
    package_digest: manifest.release.identity.package_digest,
    workflow_digest: manifest.release.identity.workflow_digest,
    path: path.relative(repoRoot, packageDir).split(path.sep).join('/'),
  })).sort((a, b) => a.automation_id.localeCompare(b.automation_id) || semverCompare(a.version, b.version));
  return {
    schema_version: '0.1',
    catalogue_kind: 'operator_metadata_index',
    source_packages_root: 'automations/catalog',
    release_count: releases.length,
    releases,
  };
}

export function indexBytes(index) {
  return `${JSON.stringify(index, null, 2)}\n`;
}

export function canCreateNewInstance(lifecycle) {
  return lifecycle === 'certified';
}
