import type { NextFunction, Request, Response } from 'express';

export function captureRawBody(req: Request, _res: Response, buf: Buffer): void {
  req.rawBody = buf.toString('utf8');
}

export function ensureRawBody(req: Request, _res: Response, next: NextFunction): void {
  if (!req.rawBody && req.body) {
    req.rawBody = JSON.stringify(req.body);
  }
  next();
}
