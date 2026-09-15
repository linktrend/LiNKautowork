import { createProductApi, type ProductApiEnv } from './app.js';
import { gsmProductApiPaciIntrospector, RemoteProductApiPaciJwksProvider } from './paci.js';
import { createPostgrestRpc } from './postgrest.js';
import { PostgrestProductApiService, PostgrestProvisioningAdapter } from './service.js';

function required(env: NodeJS.ProcessEnv, name: string): string { const value = env[name]; if (!value) throw new Error(`Missing required Product API environment variable: ${name}`); return value; }

/** Constructs the production server only from runtime configuration; test auth is impossible here. */
export function createProductionServer(env: NodeJS.ProcessEnv = process.env) {
  const rpc = createPostgrestRpc({ restUrl: required(env, 'PRODUCT_API_POSTGREST_URL'), runtimeToken: required(env, 'PRODUCT_API_RUNTIME_TOKEN'), apiKey: env.PRODUCT_API_API_KEY });
  const issuer = required(env, 'PRODUCT_API_JWT_ISSUER');
  const audience = required(env, 'PRODUCT_API_JWT_AUDIENCE');
  const jwksUrl = required(env, 'PRODUCT_API_PACI_JWKS_URL');
  const introspectionUrl = required(env, 'PRODUCT_API_PACI_INTROSPECTION_URL');
  const paciClientId = required(env, 'PRODUCT_API_PACI_CLIENT_ID');
  if (audience !== 'linkautowork-product-api') throw new Error('PRODUCT_API_JWT_AUDIENCE must be linkautowork-product-api');
  if (new URL(issuer).protocol !== 'https:' || issuer.endsWith('/') || jwksUrl !== `${issuer}/.well-known/jwks.json` || introspectionUrl !== `${issuer}/oauth/introspect`) throw new Error('Product API PACI endpoints must exactly match the HTTPS issuer');
  const cacheSeconds = Number.parseInt(env.PRODUCT_API_PACI_JWKS_CACHE_TTL_SECONDS ?? '300', 10);
  if (!Number.isSafeInteger(cacheSeconds) || cacheSeconds < 30 || cacheSeconds > 300) throw new Error('PRODUCT_API_PACI_JWKS_CACHE_TTL_SECONDS must be between 30 and 300');
  const apiEnv: ProductApiEnv = {
    nodeEnv: 'production', issuer, audience, orgId: required(env, 'PRODUCT_API_ORG_ID'), paciClientId, webhookSecret: required(env, 'PRODUCT_API_WEBHOOK_SECRET'),
    publicClientOrigin: required(env, 'PRODUCT_API_CLIENT_ORIGIN'), operatorConsoleOrigin: required(env, 'PRODUCT_API_OPERATOR_ORIGIN'),
    paciJwks: new RemoteProductApiPaciJwksProvider(jwksUrl, cacheSeconds * 1000),
    paciIntrospector: gsmProductApiPaciIntrospector(introspectionUrl, paciClientId, required(env, 'PRODUCT_API_PACI_CLIENT_KEY_ID'), required(env, 'PRODUCT_API_PACI_CLIENT_ASSERTION_SECRET_RESOURCE')),
  };
  return createProductApi(apiEnv, new PostgrestProductApiService(rpc, new PostgrestProvisioningAdapter(rpc)));
}

/** Container entrypoint. It intentionally exits before listening if any trusted boundary is absent. */
export function startProductionServer(): void { const app = createProductionServer(); const port = Number.parseInt(process.env.PORT ?? '8080', 10); if (!Number.isSafeInteger(port) || port < 1 || port > 65535) throw new Error('Invalid PORT'); app.get('/healthz', (_req, res) => res.status(200).json({ status: 'ok' })); app.listen(port, '0.0.0.0'); }

if (process.argv[1]?.endsWith('/server.js')) startProductionServer();
