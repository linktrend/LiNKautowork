import { describe, expect, it } from 'vitest';
import {
  assertNoSecretShapedContent,
  automationInstanceSchema,
  automationReleaseSchema,
  automationSecretBindingSchema,
} from '../src/index.js';

const orgId = '00000000-0000-0000-0000-000000000001';
const id = '00000000-0000-0000-0000-000000000010';
const digest = `sha256:${'a'.repeat(64)}`;

describe('automation control contracts', () => {
  it('accepts a draft immutable-release identity', () => {
    expect(automationReleaseSchema.parse({
      id,
      org_id: orgId,
      definition_id: id,
      version: '1.2.3',
      channel: 'development',
      lifecycle: 'draft',
      package_digest: digest,
      workflow_digest: digest,
      source_git_sha: 'a'.repeat(40),
      n8n_version: '2.30.0',
      package_path: 'automations/catalog/example/1.2.3',
    }).version).toBe('1.2.3');
  });

  it('accepts only a named secret reference, never a secret value', () => {
    expect(automationSecretBindingSchema.parse({
      id,
      org_id: orgId,
      instance_id: id,
      secret_ref: 'LINKAUTOWORK_CLIENT_A_TOKEN',
      purpose: 'Client API authentication',
      scope: 'connector',
      required: true,
      health_state: 'healthy',
    }).secret_ref).toBe('LINKAUTOWORK_CLIENT_A_TOKEN');
    expect(() => automationSecretBindingSchema.parse({ id, org_id: orgId, instance_id: id, secret_ref: 'token-value', purpose: 'bad', scope: 'instance', required: true, health_state: 'healthy' })).toThrow();
  });

  it('rejects secret-shaped configuration keys and values', () => {
    expect(() => automationInstanceSchema.parse({
      id,
      org_id: orgId,
      definition_id: id,
      release_id: id,
      instance_key: 'client-a-reminder',
      state: 'draft',
      configuration_digest: digest,
      configuration: { api_key: 'ltfx.app.test.ts.apikey.18.2.v1' },
    })).toThrow(/secret-shaped key/);
    ltfx.ph.0db5cd5b56.v1
    expect(() => assertNoSecretShapedContent({ callback_url: 'postgres://' + 'admin:pw123@db.internal:5432/app' })).toThrow(/secret-shaped value/);
    expect(() => assertNoSecretShapedContent({ callback_url: 'mongodb+srv://' + 'admin:pw123@cluster.example/app' })).toThrow(/secret-shaped value/);
    expect(() => assertNoSecretShapedContent({ authorization: 'Bearer abcdefghijklmnop' })).toThrow(/secret-shaped value/);
  });

  it('accepts database URIs without embedded credentials and ignores malformed URI text', () => {
    expect(() => assertNoSecretShapedContent({ callback_url: 'postgres://' + 'db.internal:5432/app' })).not.toThrow();
    expect(() => assertNoSecretShapedContent({ callback_url: 'ltfx.ph.e0a9425a0e.v1 a URI' })).not.toThrow();
  });
});
