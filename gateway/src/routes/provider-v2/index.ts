import { Router, type NextFunction, type Request, type Response } from 'express';
import { z } from 'zod';
import { HttpError } from '../../lib/http-error.js';
import { ProviderAdmissionService } from '../../services/provider-admission.js';
import { ProviderStoreError, type ProviderStore } from '../../services/provider-store.js';
import { PROVIDER_RUN_STATES } from '../../../../packages/automation-contracts/src/provider-contract.js';

const transitionBodySchema = z.object({
  expected_version: z.number().int().positive(),
  next_state: z.enum(PROVIDER_RUN_STATES),
}).strict();

/** Maps Zod and store failures onto the Express error chain without leaking payloads. */
function mapStoreError(error: unknown, next: NextFunction): void {
  if (error instanceof z.ZodError) {
    next(new HttpError(400, error.issues.map((issue) => issue.message).join('; ')));
    return;
  }
  next(error);
}

function providerV2ErrorHandler(error: unknown, _req: Request, res: Response, next: NextFunction): void {
  if (res.headersSent) {
    next(error);
    return;
  }
  if (error instanceof HttpError) {
    res.status(error.statusCode).json({ error: error.message });
    return;
  }
  if (error instanceof ProviderStoreError) {
    const status = error.category === 'not_found' ? 404 : error.category === 'conflict' ? 409 : error.category === 'blocked' ? 503 : error.category === 'forbidden' ? 403 : 400;
    res.status(status).json({ error: error.category });
    return;
  }
  next(error);
}

/**
 * Source-only `/v2/provider/*` admission, CAS lifecycle, receipt, and cursor routes.
 * Callers must inject the authenticated organisation; this router never reads credentials
 * or activates a provider. Wiring into the live gateway remains a later packet.
 */
export function createProviderV2Router(store: ProviderStore, resolveOrg: (req: Request) => string): Router {
  const admission = new ProviderAdmissionService(store);
  const router = Router();

  router.post('/v2/provider/requests', async (req, res, next) => {
    try {
      const result = await admission.admit(resolveOrg(req), req.body);
      res.status(result.replay ? 200 : 202).json({ replay: result.replay, status: result });
    } catch (error) {
      mapStoreError(error, next);
    }
  });

  router.get('/v2/provider/requests/:requestId', async (req, res, next) => {
    try {
      res.json({ status: await admission.request(resolveOrg(req), req.params.requestId) });
    } catch (error) {
      mapStoreError(error, next);
    }
  });

  router.post('/v2/provider/requests/:requestId/transitions', async (req, res, next) => {
    try {
      const body = transitionBodySchema.parse(req.body);
      res.json({ status: await admission.transition(resolveOrg(req), req.params.requestId, body.expected_version, body.next_state) });
    } catch (error) {
      mapStoreError(error, next);
    }
  });

  router.get('/v2/provider/requests/:requestId/receipt', async (req, res, next) => {
    try {
      res.json({ receipt: await admission.receipt(resolveOrg(req), req.params.requestId) });
    } catch (error) {
      mapStoreError(error, next);
    }
  });

  router.get('/v2/provider/events', async (req, res, next) => {
    try {
      const cursor = typeof req.query.cursor === 'string' ? req.query.cursor : null;
      const limit = typeof req.query.limit === 'string' ? Number(req.query.limit) : 50;
      res.json(await admission.events(resolveOrg(req), cursor, limit));
    } catch (error) {
      mapStoreError(error, next);
    }
  });

  router.use(providerV2ErrorHandler);
  return router;
}

/** Maps provider-v2 failures to compact HTTP categories. */
export { mapStoreError, providerV2ErrorHandler };
