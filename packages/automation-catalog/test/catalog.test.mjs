import fs from 'node:fs';
import crypto from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import {
  buildCatalogIndex,
  canCreateNewInstance,
  createSchemaValidator,
  indexBytes,
  validateCatalog,
  validateIntakeRecords,
  validatePackageDirectory,
  listProviderCatalogue,
  getProviderCatalogueDetail,
} from '../src/catalog.mjs';

describe('provider catalogue progressive disclosure', () => {
  const entries = [{ org_id: 'org-a', capability: 'catalogue.read', automation_id: 'precheck', version: '1.0.0', digest: 'sha256:abc', owner: 'autowork', lifecycle: 'available', purpose: 'bounded check', workflow: { private: true }, payload: 'private', logs: 'private' }, { org_id: 'org-a', capability: 'catalogue.read', automation_id: 'precheck', version: '1.1.0', digest: 'sha256:def', owner: 'autowork', lifecycle: 'deprecated', purpose: 'old' }];
  it('filters metadata and requires an exact available version', () => {
    expect(listProviderCatalogue(entries, { orgId: 'org-a', capabilities: ['catalogue.read'] })).toHaveLength(1);
    expect(listProviderCatalogue(entries, { orgId: 'org-b', capabilities: ['catalogue.read'] })).toEqual([]);
    expect(() => getProviderCatalogueDetail(entries, { orgId: 'org-a', capability: 'catalogue.read', automationId: 'precheck' })).toThrow(/exact/);
    const detail = getProviderCatalogueDetail(entries, { orgId: 'org-a', capability: 'catalogue.read', automationId: 'precheck', version: '1.0.0' });
    expect(detail).not.toHaveProperty('workflow'); expect(detail).not.toHaveProperty('payload'); expect(detail).not.toHaveProperty('logs');
  });
});

const repoRoot = path.resolve(import.meta.dirname, '../../..');
const golden = path.join(repoRoot, 'automations/packages/_golden-template');
const contractFixtures = path.join(repoRoot, 'automations/fixtures/contracts');
const validatorFixtures = path.join(repoRoot, 'automations/fixtures/validator');
const temporaryDirectories = [];

function copiedGolden() {
  const target = fs.mkdtempSync(path.join(os.tmpdir(), 'lautowork-catalog-'));
  temporaryDirectories.push(target);
  fs.cpSync(golden, target, { recursive: true });
  return target;
}

function errorsFor(packageDir) {
  return validatePackageDirectory({ repoRoot, packageDir }).errors.map((error) => error.code);
}

afterEach(() => {
  while (temporaryDirectories.length) fs.rmSync(temporaryDirectories.pop(), { recursive: true, force: true });
});

describe('Golden Automation Package v0.1 schemas', () => {
  it('accepts the positive package fixture and rejects every declared negative fixture', () => {
    const ajv = createSchemaValidator(repoRoot);
    const matrix = JSON.parse(fs.readFileSync(path.join(contractFixtures, 'fixture-matrix.json'), 'utf8'));
    for (const fixture of matrix.fixtures) {
      const value = JSON.parse(fs.readFileSync(path.join(contractFixtures, fixture.path), 'utf8'));
      const schemaName = fixture.document === 'provenance-sources'
        ? 'provenance-sources-v0.1.schema.json'
        : 'automation-package-v0.1.schema.json';
      const validate = ajv.getSchema(`https://linktrend.dev/schemas/linkautowork/${schemaName}`);
      expect(validate, fixture.path).toBeTypeOf('function');
      expect(Boolean(validate(value)), fixture.path).toBe(fixture.expected === 'accept');
    }
  });
});

describe('catalogue package validation', () => {
  it('accepts the complete Golden Automation Package', () => {
    expect(errorsFor(golden)).toEqual([]);
  });

  it('executes the intake schema as part of catalogue validation', () => {
    expect(validateIntakeRecords(repoRoot).errors).toEqual([]);
    expect(validateCatalog(repoRoot).errors).toEqual([]);
  });

  it('detects deterministic workflow graph failures', () => {
    const duplicate = copiedGolden();
    fs.copyFileSync(path.join(validatorFixtures, 'workflow-duplicate-node.json'), path.join(duplicate, 'workflow.json'));
    expect(errorsFor(duplicate)).toEqual(expect.arrayContaining(['duplicate_or_missing_node_id', 'duplicate_or_missing_node_name']));

    const badTarget = copiedGolden();
    fs.copyFileSync(path.join(validatorFixtures, 'workflow-missing-connection-target.json'), path.join(badTarget, 'workflow.json'));
    expect(errorsFor(badTarget)).toContain('invalid_workflow_connection');
  });

  it('rejects secret-shaped source content without returning the value', () => {
    const packageDir = copiedGolden();
    const file = path.join(packageDir, 'contracts/configuration.schema.json');
    fs.writeFileSync(file, JSON.stringify({ password: 'fixture-value-must-not-appear-in-errors' }));
    const errors = validatePackageDirectory({ repoRoot, packageDir }).errors;
    expect(errors.map((error) => error.code)).toContain('secret_like_field');
    expect(JSON.stringify(errors)).not.toContain('fixture-value-must-not-appear-in-errors');
  });

  it('rejects credential objects and private-key-shaped workflow content', () => {
    const packageDir = copiedGolden();
    const workflowFile = path.join(packageDir, 'workflow.json');
    const workflow = JSON.parse(fs.readFileSync(workflowFile, 'utf8'));
    workflow.nodes[1].credentials = { demo: { id: 'fixture-only' } };
    workflow.nodes[1].parameters.private_material = '-----BEGIN PRIVATE KEY-----';
    fs.writeFileSync(workflowFile, `${JSON.stringify(workflow, null, 2)}\n`);
    expect(errorsFor(packageDir)).toEqual(expect.arrayContaining(['secret_like_field', 'secret_like_content']));
  });

  it('binds a release to the actual governed source digest', () => {
    const packageDir = copiedGolden();
    const outputFile = path.join(packageDir, 'contracts/output.schema.json');
    const output = JSON.parse(fs.readFileSync(outputFile, 'utf8'));
    output.description = 'A harmless contract change still requires a new release digest.';
    fs.writeFileSync(outputFile, `${JSON.stringify(output, null, 2)}\n`);
    expect(errorsFor(packageDir)).toContain('package_digest_mismatch');
  });

  it('requires exact evaluation evidence before a release is certified', () => {
    const packageDir = copiedGolden();
    const manifestFile = path.join(packageDir, 'automation.json');
    const manifest = JSON.parse(fs.readFileSync(manifestFile, 'utf8'));
    manifest.release.lifecycle = 'certified';
    fs.writeFileSync(manifestFile, `${JSON.stringify(manifest, null, 2)}\n`);
    expect(errorsFor(packageDir)).toContain('certification_receipt_unavailable');
  });

  it('rejects a certified release even when an ordinary copied receipt says it passed', () => {
    const packageDir = copiedGolden();
    const manifestFile = path.join(packageDir, 'automation.json');
    const manifest = JSON.parse(fs.readFileSync(manifestFile, 'utf8'));
    manifest.release.lifecycle = 'certified';
    fs.writeFileSync(manifestFile, `${JSON.stringify(manifest, null, 2)}\n`);
    fs.writeFileSync(path.join(packageDir, 'evals/certification-receipt.json'), JSON.stringify({ passed: true, ...manifest.release.identity }));
    expect(errorsFor(packageDir)).toContain('certification_receipt_unavailable');
  });

  it('binds provenance source maps and evaluation identity to the exact package release', () => {
    const packageDir = copiedGolden();
    const provenanceFile = path.join(packageDir, 'provenance/sources.json');
    const provenance = JSON.parse(fs.readFileSync(provenanceFile, 'utf8'));
    provenance.source_to_target_map[0].source_content_digest = 'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff';
    fs.writeFileSync(provenanceFile, `${JSON.stringify(provenance, null, 2)}\n`);
    expect(errorsFor(packageDir)).toContain('source_hash_mismatch');

    const evalMismatch = copiedGolden();
    const suiteFile = path.join(evalMismatch, 'evals/suite.json');
    const suite = JSON.parse(fs.readFileSync(suiteFile, 'utf8'));
    suite.automation_version = '9.9.9';
    fs.writeFileSync(suiteFile, `${JSON.stringify(suite, null, 2)}\n`);
    expect(errorsFor(evalMismatch)).toContain('evaluation_identity_mismatch');
  });

  it('rejects result behavior that does not match the n8n graph', () => {
    const packageDir = copiedGolden();
    const manifestFile = path.join(packageDir, 'automation.json');
    const manifest = JSON.parse(fs.readFileSync(manifestFile, 'utf8'));
    manifest.runtime.result_mode = 'synchronous_response';
    fs.writeFileSync(manifestFile, `${JSON.stringify(manifest, null, 2)}\n`);
    expect(errorsFor(packageDir)).toContain('declared_result_behavior_mismatch');
  });

  it('accepts the supported synchronous webhook response graph', () => {
    const packageDir = copiedGolden();
    const manifestFile = path.join(packageDir, 'automation.json');
    const manifest = JSON.parse(fs.readFileSync(manifestFile, 'utf8'));
    manifest.runtime.trigger_mode = 'webhook';
    manifest.runtime.result_mode = 'synchronous_response';
    fs.writeFileSync(manifestFile, `${JSON.stringify(manifest, null, 2)}\n`);

    const workflowFile = path.join(packageDir, 'workflow.json');
    const workflow = JSON.parse(fs.readFileSync(workflowFile, 'utf8'));
    workflow.nodes[0].type = 'n8n-nodes-base.webhook';
    workflow.nodes[2] = {
      parameters: { respondWith: 'allIncomingItems' },
      id: '00000000-0000-4000-8000-000000000999',
      name: 'Respond to Webhook',
      type: 'n8n-nodes-base.respondToWebhook',
      typeVersion: 1.4,
      position: [740, 300],
    };
    workflow.connections['Return Contract Output'] = { main: [[{ node: 'Respond to Webhook', type: 'main', index: 0 }]] };
    fs.writeFileSync(workflowFile, `${JSON.stringify(workflow, null, 2)}\n`);

    expect(errorsFor(packageDir)).not.toContain('declared_result_behavior_mismatch');
    expect(errorsFor(packageDir)).not.toContain('unsupported_result_behavior');
  });

  it.each([
    ['callback', 'n8n-nodes-base.httpRequest'],
    ['event', 'n8n-nodes-base.nats'],
  ])('fails closed for %s even when a generic emitter-shaped node is present', (resultMode, nodeType) => {
    const packageDir = copiedGolden();
    const manifestFile = path.join(packageDir, 'automation.json');
    const manifest = JSON.parse(fs.readFileSync(manifestFile, 'utf8'));
    manifest.runtime.result_mode = resultMode;
    fs.writeFileSync(manifestFile, `${JSON.stringify(manifest, null, 2)}\n`);

    const workflowFile = path.join(packageDir, 'workflow.json');
    const workflow = JSON.parse(fs.readFileSync(workflowFile, 'utf8'));
    workflow.nodes.push({
      parameters: { url: 'https://example.invalid/untrusted-result-destination' },
      id: `00000000-0000-4000-8000-${resultMode === 'callback' ? '000000000997' : '000000000998'}`,
      name: `${resultMode} generic emitter`,
      type: nodeType,
      typeVersion: 1,
      position: [740, 300],
    });
    fs.writeFileSync(workflowFile, `${JSON.stringify(workflow, null, 2)}\n`);

    const errors = validatePackageDirectory({ repoRoot, packageDir }).errors;
    expect(errors.map((error) => error.code)).toContain('unsupported_result_behavior');
    expect(JSON.stringify(errors)).not.toContain('untrusted-result-destination');
  });

  it('binds a catalogue directory identity to its manifest identity', () => {
    const definitionDir = fs.mkdtempSync(path.join(repoRoot, 'automations/catalog/incorrect-id-'));
    const packageDir = path.join(definitionDir, '0.1.0');
    fs.cpSync(golden, packageDir, { recursive: true });
    try {
      expect(errorsFor(packageDir)).toContain('directory_automation_identity_mismatch');
    } finally {
      fs.rmSync(definitionDir, { recursive: true, force: true });
    }
  });

  it('rejects a package reference that escapes through a symlink', () => {
    const packageDir = copiedGolden();
    const outside = path.join(os.tmpdir(), `lautowork-outside-${crypto.randomUUID()}.md`);
    fs.writeFileSync(outside, 'outside package');
    const linked = path.join(packageDir, 'operations/outside-runbook.md');
    fs.symlinkSync(outside, linked);
    const manifestFile = path.join(packageDir, 'automation.json');
    const manifest = JSON.parse(fs.readFileSync(manifestFile, 'utf8'));
    manifest.operations.runbook_ref = 'operations/outside-runbook.md';
    fs.writeFileSync(manifestFile, `${JSON.stringify(manifest, null, 2)}\n`);
    expect(errorsFor(packageDir)).toContain('missing_reference');
    fs.rmSync(outside, { force: true });
  });

  it('builds byte-identical empty operator indexes and allows instances only from certified releases', () => {
    const first = indexBytes(buildCatalogIndex(repoRoot));
    const second = indexBytes(buildCatalogIndex(repoRoot));
    expect(first).toBe(second);
    expect(fs.readFileSync(path.join(repoRoot, 'automations/catalog/index.json'), 'utf8')).toBe(first);
    expect(canCreateNewInstance('certified')).toBe(true);
    expect(canCreateNewInstance('deprecated')).toBe(false);
    expect(canCreateNewInstance('retired')).toBe(false);
  });
});
