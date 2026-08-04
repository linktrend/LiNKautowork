import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPostgrestRpc } from '../src/postgrest.ts';
import { createProductionServer } from '../src/server.ts';

const clientOrigin = 'https://client.example';
const operatorOrigin = 'https://operator.example';

function stubProductionEnvironment(): void {
  const values = {
    PRODUCT_API_POSTGREST_URL: 'http://postgrest.test/rest/v1',
    PRODUCT_API_SERVICE_ROLE_TOKEN: 'product-api-service-role-token',
    PRODUCT_API_SESSION_URL: 'http://session.test/check',
    PRODUCT_API_JWT_ISSUER: 'https://issuer.example',
    PRODUCT_API_JWT_AUDIENCE: 'linkautowork-product-api',
    PRODUCT_API_JWKS_URL: 'http://jwks.test/keys',
    PRODUCT_API_WEBHOOK_SECRET: 'product-api-webhook-secret',
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

  it('mounts PostgREST RPCs at the supplied restUrl root when rpcPath is empty', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const rpc = createPostgrestRpc({ restUrl: 'https://project.supabase.co', rpcPath: '', serviceRoleToken: 'product-api-service-role-token' });

    await rpc('linkautowork_product_published_products', { p_limit: 10, p_cursor: null });

    expect(fetchMock).toHaveBeenCalledWith('https://project.supabase.co/rpc/linkautowork_product_published_products', expect.anything());
  });

  it('uses the default /rest/v1 PostgREST path', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const rpc = createPostgrestRpc({ restUrl: 'https://project.supabase.co', serviceRoleToken: 'product-api-service-role-token' });

    await rpc('linkautowork_product_published_products', { p_limit: 10, p_cursor: null });

    expect(fetchMock).toHaveBeenCalledWith('https://project.supabase.co/rest/v1/rpc/linkautowork_product_published_products', expect.anything());
  });

  it('captures exactly one PostgREST REST path when the environment already supplies /rest/v1', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const rpc = createPostgrestRpc({ restUrl: 'https://project.supabase.co/rest/v1', serviceRoleToken: 'product-api-service-role-token' });

    await rpc('linkautowork_product_published_products', { p_limit: 10, p_cursor: null });

    expect(fetchMock).toHaveBeenCalledWith('https://project.supabase.co/rest/v1/rpc/linkautowork_product_published_products', expect.anything());
    expect((fetchMock.mock.calls[0]?.[0] as string).match(/\/rest\/v1/g)).toHaveLength(1);
  });

  it('delegates the verified organisation to an org-scoped command behind a fixed service credential', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const rpc = createPostgrestRpc({ restUrl: 'https://project.supabase.co', serviceRoleToken: 'product-api-service-role-token' });

    await rpc('linkautowork_product_request_provisioning_audited', {}, '00000000-0000-0000-0000-000000000002');

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.headers).toMatchObject({
      'x-link-org-id': '00000000-0000-0000-0000-000000000002',
      'x-link-request-claims': JSON.stringify({ role: 'service_role', org_id: '00000000-0000-0000-0000-000000000002' }),
    });
  });
});
