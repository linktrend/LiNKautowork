import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const root = resolve(fileURLToPath(new URL('../public/', import.meta.url)));
const types: Record<string, string> = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };
const port = Number.parseInt(process.env.PORT ?? '8080', 10);
/** Public, non-secret browser contract. The Platform OIDC issuer owns interactive sign-in. */
function runtimeConfig() { return JSON.stringify({
  productApiOrigin: process.env.PRODUCT_API_PUBLIC_ORIGIN ?? '',
  oidcIssuer: process.env.PLATFORM_OIDC_ISSUER ?? '',
  oidcClientId: process.env.OPERATOR_OIDC_CLIENT_ID ?? '',
  oidcRedirectUri: process.env.OPERATOR_OIDC_REDIRECT_URI ?? '',
  testMode: false,
}); }
createServer(async (request, response) => {
  if (request.url === '/healthz') { response.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' }); response.end('{"status":"ok"}'); return; }
  if (request.url?.split('?')[0] === '/runtime-config.json') { response.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' }); response.end(runtimeConfig()); return; }
  const relative = request.url === '/' ? 'index.html' : decodeURIComponent(request.url?.split('?')[0] ?? '').replace(/^\/+/, '');
  const target = resolve(root, relative);
  if (!target.startsWith(`${root}/`)) { response.writeHead(404).end(); return; }
  try { await stat(target); response.writeHead(200, { 'content-type': types[target.slice(target.lastIndexOf('.'))] ?? 'application/octet-stream', 'x-content-type-options': 'nosniff' }); createReadStream(target).pipe(response); } catch { response.writeHead(404).end(); }
}).listen(port, '0.0.0.0');
