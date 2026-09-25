#!/usr/bin/env node
// Mints a short-lived Platform PACI access token (client_credentials +
// private_key_jwt) for the operations scheduler and prints it on stdout.
// The private key comes from a mounted file or a pinned GSM secret version;
// neither the key nor the assertion is ever printed.
import { createPrivateKey, randomUUID, sign } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { SecretManagerServiceClient } from '@google-cloud/secret-manager';

const issuer = process.env.PLATFORM_JWT_ISSUER;
const clientId = process.env.OPERATIONS_PLATFORM_CLIENT_ID || 'server01-lautowork-operations';
const kid = process.env.OPERATIONS_PLATFORM_CLIENT_KEY_ID || clientId;
const keyFile = process.env.OPERATIONS_PLATFORM_CLIENT_KEY_FILE;
const keyResource = process.env.OPERATIONS_PLATFORM_CLIENT_ASSERTION_SECRET_RESOURCE;

function fail(message) {
  process.stderr.write(`mint-platform-token: ${message}\n`);
  process.exit(1);
}

async function loadPem() {
  if (keyFile) return readFile(keyFile, 'utf8');
  if (keyResource) {
    if (!/^projects\/[a-z0-9-]+\/secrets\/[A-Za-z0-9_-]+\/versions\/[1-9][0-9]*$/.test(keyResource)) fail('secret resource must pin a version');
    const [version] = await new SecretManagerServiceClient().accessSecretVersion({ name: keyResource });
    return version.payload?.data?.toString('utf8') ?? '';
  }
  return fail('OPERATIONS_PLATFORM_CLIENT_KEY_FILE or OPERATIONS_PLATFORM_CLIENT_ASSERTION_SECRET_RESOURCE is required');
}

export function clientAssertion(endpoint, key, now = Math.floor(Date.now() / 1000)) {
  const header = Buffer.from(JSON.stringify({ alg: 'ES256', typ: 'JWT', kid })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({ iss: clientId, sub: clientId, aud: endpoint, iat: now, exp: now + 60, jti: randomUUID() })).toString('base64url');
  const input = `${header}.${payload}`;
  return `${input}.${sign('SHA256', Buffer.from(input), { key, dsaEncoding: 'ieee-p1363' }).toString('base64url')}`;
}

async function main() {
  if (!issuer || !issuer.startsWith('https://')) fail('PLATFORM_JWT_ISSUER must be an https origin');
  const pem = await loadPem();
  if (!pem) fail('client key is unavailable');
  const key = createPrivateKey(pem);
  if (key.asymmetricKeyType !== 'ec' || key.asymmetricKeyDetails?.namedCurve !== 'prime256v1') fail('client key must be a private P-256 key');
  const endpoint = `${issuer}/oauth/token`;
  const response = await fetch(endpoint, {
    method: 'POST', redirect: 'error', signal: AbortSignal.timeout(10_000),
    headers: { 'content-type': 'application/x-www-form-urlencoded', accept: 'application/json' },
    body: new URLSearchParams({
      grant_type: 'client_credentials', client_id: clientId, scope: 'autowork',
      client_assertion_type: 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer', client_assertion: clientAssertion(endpoint, key),
    }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || typeof body.access_token !== 'string') fail(`token endpoint returned ${response.status} ${body.error ?? ''}`.trim());
  process.stdout.write(body.access_token);
}

main().catch((error) => fail(error instanceof Error ? error.message : 'unexpected error'));
