import express from 'express';
import { fileURLToPath } from 'node:url';
import { createProductApi } from '../../product-api/src/app.js';
import { InMemoryProductApiService } from '../../product-api/src/service.js';

const orgId = '00000000-0000-0000-0000-000000000002';
const service = new InMemoryProductApiService([], [], { incidents: [{ id: 'incident-1', orgId, status: 'open', version: 1, summary: 'local fixture incident' }] });
const api = createProductApi({ nodeEnv: 'test', issuer: 'local', audience: 'local', testJwtSecret: 'ltfx.local.product.api.demo.ts.testjwtsecret.8.0.v1' }, service, () => ({ sub: 'demo-operator', org_id: orgId, roles: ['operator', 'approver'], iss: 'local', aud: 'local', exp: Math.floor(Date.now() / 1000) + 60 }));
const app = express(); app.use(api); app.use(express.static(fileURLToPath(new URL('../', import.meta.url)))); app.listen(Number(process.env.PORT ?? 4180));
