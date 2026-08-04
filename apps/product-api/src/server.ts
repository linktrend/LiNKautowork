import { createProductApi, type ProductApiEnv } from './app.js';
import { createPostgrestRpc } from './postgrest.js';
import { PostgrestProductApiService, PostgrestProvisioningAdapter } from './service.js';

function required(env: NodeJS.ProcessEnv, name: string): string { const value = env[name]; if (!value) throw new Error(`Missing required Product API environment variable: ${name}`); return value; }

/** Constructs the production server only from runtime configuration; test auth is impossible here. */
export function createProductionServer(env: NodeJS.ProcessEnv = process.env) {
  const rpc = createPostgrestRpc({ restUrl: required(env, 'PRODUCT_API_POSTGREST_URL'), serviceRoleToken: required(env, 'PRODUCT_API_SERVICE_ROLE_TOKEN') });
  const sessionUrl = required(env, 'PRODUCT_API_SESSION_URL');
  const apiEnv: ProductApiEnv = {
    nodeEnv: 'production', issuer: required(env, 'PRODUCT_API_JWT_ISSUER'), audience: required(env, 'PRODUCT_API_JWT_AUDIENCE'), platformJwksUrl: required(env, 'PRODUCT_API_JWKS_URL'), webhookSecret: required(env, 'PRODUCT_API_WEBHOOK_SECRET'),
    publicClientOrigin: required(env, 'PRODUCT_API_CLIENT_ORIGIN'), operatorConsoleOrigin: required(env, 'PRODUCT_API_OPERATOR_ORIGIN'),
    sessionActive: async (subject, sessionId) => {
      const response = await fetch(sessionUrl, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ subject, sessionId }) });
      return response.ok && (await response.json() as { active?: boolean }).active === true;
    },
  };
  return createProductApi(apiEnv, new PostgrestProductApiService(rpc, new PostgrestProvisioningAdapter(rpc)));
}

/** Container entrypoint. It intentionally exits before listening if any trusted boundary is absent. */
export function startProductionServer(): void { const app = createProductionServer(); const port = Number.parseInt(process.env.PORT ?? '8080', 10); if (!Number.isSafeInteger(port) || port < 1 || port > 65535) throw new Error('Invalid PORT'); app.get('/healthz', (_req, res) => res.status(200).json({ status: 'ok' })); app.listen(port, '0.0.0.0'); }

if (process.argv[1]?.endsWith('/server.js')) startProductionServer();
