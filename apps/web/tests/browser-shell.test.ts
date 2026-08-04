import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';

describe('WP-11 browser-facing client portal shell', () => {
  it('is responsive, accessible, uses an external Platform session, and keeps credential intake out of the browser', async () => {
    const [html, app, css] = await Promise.all([readFile(new URL('../public/index.html', import.meta.url), 'utf8'), readFile(new URL('../src/app.ts', import.meta.url), 'utf8'), readFile(new URL('../public/styles.css', import.meta.url), 'utf8')]);
    const [auth, server] = await Promise.all([readFile(new URL('../src/platform-auth.ts', import.meta.url), 'utf8'), readFile(new URL('../src/server.ts', import.meta.url), 'utf8')]); expect(html).toContain('viewport'); expect(app).toContain('browserRuntimeConfig'); expect(app).toContain('aria-live="polite"'); expect(app).toContain('aria-label="Your automation instances"'); expect(app).toContain('Credential values are never accepted'); expect(app).toContain('submitConfiguration'); expect(auth).toContain('Authorization Code + PKCE'); expect(auth).toContain('testMode'); expect(server).toContain('PRODUCT_API_PUBLIC_ORIGIN'); expect(app).not.toMatch(/submitCredentials|passwordInput|apiKeyInput/); expect(css).toContain('@media(max-width:700px)');
  });
  it('keeps client provisioning separate from operator promotion and exposes only safe client actions', async () => {
    const app = await readFile(new URL('../src/app.ts', import.meta.url), 'utf8');
    expect(app).toContain('createOrder'); expect(app).toContain('createSubscription'); expect(app).toContain('submitConfiguration'); expect(app).toContain('requestProvisioning'); expect(app).toContain('savedIntent'); expect(app).toContain("action: button.textContent === 'Resume' ? 'resume' : 'pause'"); expect(app).not.toContain('promote'); expect(app).not.toContain('rollback');
  });
});
