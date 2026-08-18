import { createHmac } from 'node:crypto';
import { createServer, type Server } from 'node:http';
import { createProductApi } from '../../../apps/product-api/src/app.js';
import { createPostgrestRpc } from '../../../apps/product-api/src/postgrest.js';
import { PostgrestProductApiService, PostgrestProvisioningAdapter } from '../../../apps/product-api/src/service.js';

const restUrl = process.env.DURABLE_POSTGREST_URL;
if (!restUrl) throw new Error('DURABLE_POSTGREST_URL is required');
const postgrestSecret = 'ltfx.ph.24c6deb948.v1';
const webhookSecret = 'ltfx.ph.dab4648be8.v1';
const orgId = '00000000-0000-0000-0000-000000000002';
const subscriptionSuccess = '93000000-0000-0000-0000-000000000001';
const subscriptionFailure = '93000000-0000-0000-0000-000000000002';
const postgrestRetryLimit = 8;
const postgrestRetryDelayMs = 500;

function jwt() {
  const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const header = encode({ alg: 'HS256', typ: 'JWT' });
  const payload = encode({ role: 'service_role', org_id: orgId, exp: Math.floor(Date.now() / 1000) + 300 });
  return `${header}.${payload}.${createHmac('sha256', postgrestSecret).update(`${header}.${payload}`).digest('base64url')}`;
}

const wait = (milliseconds: number) => new Promise<void>((resolve) => setTimeout(resolve, milliseconds));

function isTransientPostgrestError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const cause = error.cause as { code?: unknown } | undefined;
  return ['ECONNRESET', 'ECONNREFUSED', 'ETIMEDOUT', 'UND_ERR_SOCKET'].includes(typeof cause?.code === 'string' ? cause.code : '');
}

async function waitForPostgrest(): Promise<void> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= postgrestRetryLimit; attempt += 1) {
    try {
      const response = await fetch(`${restUrl}/`);
      if (response.ok) return;
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    if (attempt < postgrestRetryLimit) await wait(postgrestRetryDelayMs);
  }
  throw new Error(`PostgREST did not become ready after ${postgrestRetryLimit} attempts: ${String(lastError)}`);
}

await waitForPostgrest();
const rawRpc = createPostgrestRpc({ restUrl, rpcPath: '', serviceRoleToken: jwt() });
const rpc: typeof rawRpc = async (...args) => {
  let lastError: unknown;
  for (let attempt = 1; attempt <= postgrestRetryLimit; attempt += 1) {
    try {
      return await rawRpc(...args);
    } catch (error) {
      if (!isTransientPostgrestError(error)) throw error;
      lastError = error;
    }
    if (attempt < postgrestRetryLimit) {
      await wait(postgrestRetryDelayMs);
      await waitForPostgrest();
    }
  }
  throw lastError;
};
const service = new PostgrestProductApiService(rpc, new PostgrestProvisioningAdapter(rpc));
const app = createProductApi({ nodeEnv: 'test', issuer: 'https://durable.webhook.test', audience: 'product-api', testJwtSecret: 'ltfx.ph.caba3e9d16.v1', webhookSecret }, service);
let activeServer: Server = createServer(app);
await new Promise<void>((resolve) => activeServer.listen(0, '127.0.0.1', resolve));
const address = activeServer.address(); if (!address || typeof address === 'string') throw new Error('webhook verifier server did not bind');
const endpoint = `http://127.0.0.1:${address.port}/v1/webhooks/status`;

async function closeServer(server: Server): Promise<void> {
  server.closeAllConnections();
  if (server.listening) await new Promise<void>((resolve) => server.close(() => resolve()));
}

async function send(event: Record<string, unknown>, signingMaterial = webhookSecret) {
  const body = JSON.stringify(event);
  const signature = createHmac('sha256', signingMaterial).update(body).digest('hex');
  const response = await fetch(endpoint, { method: 'POST', headers: { 'connection': 'close', 'content-type': 'application/json', 'x-link-webhook-signature': signature }, body });
  return { response, body: await response.json() as Record<string, unknown> };
}

try {
  const successEvent = { eventId: 'durable-webhook-success-0001', eventType: 'payment.succeeded', occurredAt: '2026-08-04T01:00:00.000Z', providerSequence: 10, orgId, subscriptionId: subscriptionSuccess };
  const first = await send(successEvent); if (first.response.status !== 202 || first.body.replay !== false || first.body.state !== 'awaiting_configuration') throw new Error(`signed success did not advance durable lifecycle: ${JSON.stringify(first)}`);
  const duplicate = await send(successEvent); if (duplicate.response.status !== 202 || duplicate.body.replay !== true) throw new Error('exact signed duplicate was not a durable replay');
  await closeServer(activeServer);

  activeServer = createServer(createProductApi({ nodeEnv: 'test', issuer: 'https://durable.webhook.test', audience: 'product-api', testJwtSecret: 'ltfx.ph.caba3e9d16.v1', webhookSecret }, new PostgrestProductApiService(rpc, new PostgrestProvisioningAdapter(rpc))));
  await new Promise<void>((resolve) => activeServer.listen(address.port, '127.0.0.1', resolve));
  const restarted = await send(successEvent); if (restarted.response.status !== 202 || restarted.body.replay !== true) throw new Error('duplicate after Product API restart was not recovered from durable PostgREST');

  const forged = await send({ ...successEvent, eventId: 'durable-webhook-forged-0001' }, 'wrong-webhook-secret'); if (forged.response.status !== 401) throw new Error('forged webhook signature was accepted');
  const stale = await send({ ...successEvent, eventId: 'durable-webhook-stale-0001', providerSequence: 9, occurredAt: '2026-08-04T00:59:00.000Z' }); if (stale.response.status < 400 || stale.response.status >= 500) throw new Error('stale provider event was accepted');
  const failed = await send({ eventId: 'durable-webhook-failed-0001', eventType: 'payment.failed', occurredAt: '2026-08-04T01:00:00.000Z', providerSequence: 1, orgId, subscriptionId: subscriptionFailure }); if (failed.response.status !== 202 || failed.body.state !== 'failed') throw new Error(`signed failure did not lock lifecycle: ${JSON.stringify(failed)}`);
  console.log('Durable Product API webhook HTTP verification passed: signed success/failure, duplicate, restart recovery, forged-signature rejection, and ordering rejection.');
} finally {
  await closeServer(activeServer);
}
