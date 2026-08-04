import type { PlatformSession } from './product-api-http.js';

export type BrowserRuntimeConfig = { productApiOrigin: string; oidcIssuer: string; oidcClientId: string; oidcRedirectUri: string; testMode: boolean };
type OidcMetadata = { authorization_endpoint: string; token_endpoint: string };
declare global { interface Window { LINKAUTOWORK_CLIENT_SESSION?: PlatformSession } }

let accessToken: string | undefined;

/** Reads only public endpoints and client IDs. Runtime configuration never contains a token or secret. */
export async function browserRuntimeConfig(): Promise<BrowserRuntimeConfig> {
  const response = await fetch('/runtime-config.json', { cache: 'no-store' });
  if (!response.ok) throw new Error('The public sign-in configuration is unavailable.');
  const value = await response.json() as Partial<BrowserRuntimeConfig>;
  return { productApiOrigin: value.productApiOrigin ?? '', oidcIssuer: value.oidcIssuer ?? '', oidcClientId: value.oidcClientId ?? '', oidcRedirectUri: value.oidcRedirectUri ?? '', testMode: value.testMode === true };
}

function testSession(config: BrowserRuntimeConfig): PlatformSession | undefined { return config.testMode ? window.LINKAUTOWORK_CLIENT_SESSION : undefined; }
function random() { const bytes = new Uint8Array(32); crypto.getRandomValues(bytes); return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }
async function challenge(verifier: string) { const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)); return btoa(String.fromCharCode(...new Uint8Array(digest))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }

/** OIDC Authorization Code + PKCE. The access token is retained only in page memory. */
export async function platformSession(config: BrowserRuntimeConfig): Promise<PlatformSession | undefined> {
  const injected = testSession(config); if (injected) return injected;
  if (accessToken) return { accessToken, subject: '', organisationId: '', roles: [] };
  const callback = new URL(location.href); const code = callback.searchParams.get('code'); const state = callback.searchParams.get('state');
  if (!code || !state || state !== sessionStorage.getItem('linkautowork.oidc.state') || !config.oidcIssuer || !config.oidcClientId || !config.oidcRedirectUri) return undefined;
  const verifier = sessionStorage.getItem('linkautowork.oidc.verifier'); if (!verifier) return undefined;
  const metadata = await fetch(`${config.oidcIssuer.replace(/\/$/, '')}/.well-known/openid-configuration`, { cache: 'no-store' }).then(async (response) => { if (!response.ok) throw new Error('Platform sign-in metadata is unavailable.'); return response.json() as Promise<OidcMetadata>; });
  const body = new URLSearchParams({ grant_type: 'authorization_code', code, redirect_uri: config.oidcRedirectUri, client_id: config.oidcClientId, code_verifier: verifier });
  const token = await fetch(metadata.token_endpoint, { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body }).then(async (response) => { if (!response.ok) throw new Error('Platform sign-in could not be completed.'); return response.json() as Promise<{ access_token?: string }>; });
  if (!token.access_token) throw new Error('Platform sign-in did not return an access token.');
  accessToken = token.access_token; sessionStorage.removeItem('linkautowork.oidc.state'); sessionStorage.removeItem('linkautowork.oidc.verifier'); callback.searchParams.delete('code'); callback.searchParams.delete('state'); history.replaceState({}, '', `${callback.pathname}${callback.search}${callback.hash}`);
  return { accessToken, subject: '', organisationId: '', roles: [] };
}

/** Redirects to the Platform. PKCE verifier/state are not credentials and are cleared after exchange. */
export async function beginPlatformSignIn(config: BrowserRuntimeConfig): Promise<void> {
  if (!config.oidcIssuer || !config.oidcClientId || !config.oidcRedirectUri) throw new Error('Platform sign-in has not been configured for this environment.');
  const metadata = await fetch(`${config.oidcIssuer.replace(/\/$/, '')}/.well-known/openid-configuration`, { cache: 'no-store' }).then(async (response) => { if (!response.ok) throw new Error('Platform sign-in metadata is unavailable.'); return response.json() as Promise<OidcMetadata>; });
  const state = random(); const verifier = random(); sessionStorage.setItem('linkautowork.oidc.state', state); sessionStorage.setItem('linkautowork.oidc.verifier', verifier);
  const query = new URLSearchParams({ response_type: 'code', client_id: config.oidcClientId, redirect_uri: config.oidcRedirectUri, scope: 'openid profile', state, code_challenge: await challenge(verifier), code_challenge_method: 'S256' }); location.assign(`${metadata.authorization_endpoint}?${query}`);
}
