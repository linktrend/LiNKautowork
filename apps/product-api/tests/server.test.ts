import { createHmac } from 'node:crypto';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPostgrestRpc } from '../src/postgrest.ts';
import { createProductionServer } from '../src/server.ts';

function runtimeToken(role = 'svc_lautowork_product_api'): string {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({ role, exp: Math.floor(Date.now() / 1000) + 60 })).toString('base64url');
  return `${header}.${payload}.${createHmac('sha256', 'disposable-test-signing-key').update(`${header}.${payload}`).digest('base64url')}`;
}

const clientOrigin = 'https://client.example';
const operatorOrigin = 'https://operator.example';

function stubProductionEnvironment(): void {
  const values = {
    PRODUCT_API_POSTGREST_URL: 'http://postgrest.test/rest/v1',
    PRODUCT_API_RUNTIME_TOKEN: runtimeToken(),
    PRODUCT_API_JWT_ISSUER: 'https://issuer.example',
    PRODUCT_API_JWT_AUDIENCE: 'linkautowork-product-api',
    PRODUCT_API_ORG_ID: '00000000-0000-4000-8000-000000000002',
    PRODUCT_API_PACI_JWKS_URL: 'https://issuer.example/.well-known/jwks.json',
    PRODUCT_API_PACI_INTROSPECTION_URL: 'https://issuer.example/oauth/introspect',
    PRODUCT_API_PACI_CLIENT_ID: 'server01-lautowork-product-api',
    PRODUCT_API_PACI_CLIENT_KEY_ID: 'product-api-key-1',
    PRODUCT_API_PACI_CLIENT_ASSERTION_SECRET_RESOURCE: 'projects/disposable-project/secrets/product-api-client/versions/1',
    PRODUCT_API_WEBHOOK_SECRET: 'ltfx.ph.e48b2e34cf.v1',
    PRODUCT_API_CLIENT_ORIGIN: clientOrigin,
    PRODUCT_API_OPERATOR_ORIGIN: operatorOrigin,
  };
  for (const [name, value] of Object.entries(values)) vi.stubEnv(name, value);
}

describe('Product API production constructor', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it('constructs from process.env with separate required browser origins', () => {
    stubProductionEnvironment();

    const app = createProductionServer();
    expect(app).toEqual(expect.any(Function));
  });

  it('fails before constructing the production app when either exact origin is absent', () => {
    stubProductionEnvironment();

    expect(() => createProductionServer({ ...process.env, PRODUCT_API_CLIENT_ORIGIN: undefined })).toThrow('PRODUCT_API_CLIENT_ORIGIN');
    expect(() => createProductionServer({ ...process.env, PRODUCT_API_OPERATOR_ORIGIN: undefined })).toThrow('PRODUCT_API_OPERATOR_ORIGIN');
  });

  it('requires exact PACI endpoints, audience, org binding, and a pinned GSM client key version', () => {
    stubProductionEnvironment();
    expect(() => createProductionServer({ ...process.env, PRODUCT_API_ORG_ID: undefined })).toThrow('PRODUCT_API_ORG_ID');
    expect(() => createProductionServer({ ...process.env, PRODUCT_API_JWT_AUDIENCE: 'other-api' })).toThrow('linkautowork-product-api');
    expect(() => createProductionServer({ ...process.env, PRODUCT_API_PACI_INTROSPECTION_URL: 'https://other.example/oauth/introspect' })).toThrow('exactly match');
    expect(() => createProductionServer({ ...process.env, PRODUCT_API_JWT_ISSUER: 'https://issuer.example/path', PRODUCT_API_PACI_JWKS_URL: 'https://issuer.example/path/.well-known/jwks.json', PRODUCT_API_PACI_INTROSPECTION_URL: 'https://issuer.example/path/oauth/introspect' })).toThrow('root HTTPS issuer');
    expect(() => createProductionServer({ ...process.env, PRODUCT_API_PACI_CLIENT_ASSERTION_SECRET_RESOURCE: 'projects/disposable-project/secrets/product-api-client/versions/latest' })).toThrow('numeric GSM version');
  });

  it('mounts PostgREST RPCs at the supplied restUrl root when rpcPath is empty', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const rpc = createPostgrestRpc({ restUrl: 'https://project.supabase.co', rpcPath: '', runtimeToken: runtimeToken() });

    await rpc('linkautowork_product_published_products', { p_limit: 10, p_cursor: null });

    expect(fetchMock).toHaveBeenCalledWith('https://project.supabase.co/rpc/linkautowork_product_published_products', expect.anything());
  });

  it('uses the default /rest/v1 PostgREST path', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const rpc = createPostgrestRpc({ restUrl: 'https://project.supabase.co', runtimeToken: runtimeToken() });

    await rpc('linkautowork_product_published_products', { p_limit: 10, p_cursor: null });

    expect(fetchMock).toHaveBeenCalledWith('https://project.supabase.co/rest/v1/rpc/linkautowork_product_published_products', expect.anything());
  });

  it('captures exactly one PostgREST REST path when the environment already supplies /rest/v1', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const rpc = createPostgrestRpc({ restUrl: 'https://project.supabase.co/rest/v1', runtimeToken: runtimeToken() });

    await rpc('linkautowork_product_published_products', { p_limit: 10, p_cursor: null });

    expect(fetchMock).toHaveBeenCalledWith('https://project.supabase.co/rest/v1/rpc/linkautowork_product_published_products', expect.anything());
    expect((fetchMock.mock.calls[0]?.[0] as string).match(/\/rest\/v1/g)).toHaveLength(1);
  });

  it('delegates the verified organisation to an org-scoped command behind a fixed service credential', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const rpc = createPostgrestRpc({ restUrl: 'https://project.supabase.co', runtimeToken: runtimeToken() });

    await rpc('linkautowork_product_request_provisioning_audited', {}, '00000000-0000-0000-0000-000000000002');

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.headers).toMatchObject({
      'x-link-org-id': '00000000-0000-0000-0000-000000000002',
    });
    expect(request.headers).not.toHaveProperty('x-link-request-claims');
    expect(request.headers).not.toHaveProperty('apikey');
  });

  it('rejects broad or unrelated database credentials before any request', () => {
    for (const role of ['service_role', 'anon', 'svc_lautowork_gateway']) {
      expect(() => createPostgrestRpc({ restUrl: 'https://project.supabase.co', runtimeToken: runtimeToken(role) })).toThrow('svc_lautowork_product_api');
    }
    expect(() => createPostgrestRpc({ restUrl: 'https://project.supabase.co', runtimeToken: 'ltfx.ph.invalid-runtime.v1' })).toThrow('scoped runtime JWT');
  });

  it('keeps the API gateway key separate from the scoped authorization token', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const token = runtimeToken();
    await createPostgrestRpc({ restUrl: 'https://project.supabase.co', runtimeToken: token, apiKey: 'ltfx.ph.publishable.v1' })('linkautowork_product_published_products', {});
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ headers: { authorization: `Bearer ${token}`, apikey: 'ltfx.ph.publishable.v1' } });
  });
});
