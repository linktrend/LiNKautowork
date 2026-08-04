import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { createApp, type AppDeps } from '../src/app.js';
import type { AppEnv } from '../src/config/env.js';
import { NonceStore } from '../src/lib/nonce-store.js';

function createRateLimitTestApp() {
  const env = {
    REPLAY_WINDOW_SECONDS: 300,
    serviceTokens: new Map(),
    hmacSecrets: new Map(),
  } as AppEnv;
  const deps = { env, nonceStore: new NonceStore(env.REPLAY_WINDOW_SECONDS) } as AppDeps;
  return createApp(deps);
}

describe('gateway ingress rate limiting', () => {
  it('limits execution callbacks before signed-ingress authentication', async () => {
    const app = createRateLimitTestApp();

    for (let attempt = 0; attempt < 120; attempt += 1) {
      await request(app).post('/v1/executions/callback').send({}).expect(401);
    }

    const response = await request(app).post('/v1/executions/callback').send({}).expect(429);
    expect(response.body).toEqual({ error: 'rate_limit_exceeded' });
  });
});
