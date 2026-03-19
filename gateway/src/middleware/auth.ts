import type { NextFunction, Request, Response } from 'express';
import type { AppEnv } from '../config/env.js';
import { HttpError } from '../lib/http-error.js';
import { NonceStore } from '../lib/nonce-store.js';
import { verifyLinkSignature } from '../lib/signing.js';

export function requireSignedIngress(env: AppEnv, nonceStore: NonceStore) {
  return (req: Request, _res: Response, next: NextFunction): void => {
    try {
      const service = req.header('x-link-service');
      const token = req.header('x-link-service-token');
      const signature = req.header('x-link-signature');
      const timestamp = req.header('x-link-timestamp');
      const nonce = req.header('x-link-nonce');

      if (!service || !token || !signature || !timestamp || !nonce) {
        throw new HttpError(401, 'missing signed ingress headers');
      }

      const expectedToken = env.serviceTokens.get(service);
      if (!expectedToken || expectedToken !== token) {
        throw new HttpError(403, 'invalid service token');
      }

      const secret = env.hmacSecrets.get(service);
      if (!secret) {
        throw new HttpError(403, `no hmac secret configured for service ${service}`);
      }

      const verification = verifyLinkSignature({
        secret,
        timestamp,
        nonce,
        signature,
        rawBody: req.rawBody ?? '{}',
        replayWindowSeconds: env.REPLAY_WINDOW_SECONDS,
        nonceStore,
      });

      if (!verification.ok) {
        throw new HttpError(401, verification.reason);
      }

      req.linkService = service;
      next();
    } catch (error) {
      next(error);
    }
  };
}

export function requireInternalServiceToken(env: AppEnv) {
  return (req: Request, _res: Response, next: NextFunction): void => {
    const service = req.header('x-link-service');
    const token = req.header('x-link-service-token');

    if (!service || !token) {
      next(new HttpError(401, 'missing service headers'));
      return;
    }

    const expectedToken = env.serviceTokens.get(service);
    if (!expectedToken || expectedToken !== token) {
      next(new HttpError(403, 'invalid service token'));
      return;
    }

    req.linkService = service;
    next();
  };
}

export function requireControlToken(env: AppEnv) {
  return (req: Request, _res: Response, next: NextFunction): void => {
    const headerToken = req.header('x-link-control-token');
    const authHeader = req.header('authorization');
    const bearerToken = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : undefined;
    const provided = headerToken ?? bearerToken;

    if (!provided) {
      next(new HttpError(401, 'missing control token'));
      return;
    }

    if (provided !== env.LINK_CONTROL_TOKEN) {
      next(new HttpError(403, 'invalid control token'));
      return;
    }

    next();
  };
}
