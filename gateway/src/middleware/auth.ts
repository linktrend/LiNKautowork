import type { NextFunction, Request, Response } from 'express';
import type { AppEnv } from '../config/env.js';
import { HttpError } from '../lib/http-error.js';
import { NonceStore } from '../lib/nonce-store.js';
import { verifyLinkSignature } from '../lib/signing.js';
import { createHmac, createPublicKey, timingSafeEqual, verify as verifySignature } from 'node:crypto';
import type { JsonWebKey as CryptoJsonWebKey } from 'node:crypto';
import { z } from 'zod';

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

const platformClaimsSchema = z.object({
  iss: z.string(), aud: z.union([z.string(), z.array(z.string())]), sub: z.string().min(1),
  exp: z.number().int(), nbf: z.number().int().optional(), service: z.string().min(2),
  org_id: z.string().uuid(), org_entitlements: z.array(z.string().uuid()),
}).passthrough();

/** Verifies the local HS256 contract adapter. Production stays fail-closed until the live OIDC verifier is configured. */
export function requirePlatformInvocationClaim(env: AppEnv) {
  return (req: Request, _res: Response, next: NextFunction): void => {
    try {
      if (env.NODE_ENV === 'production' || !env.PLATFORM_JWT_TEST_SECRET) throw new HttpError(503, 'live Platform JWT verifier is not configured');
      const value = req.header('authorization');
      if (!value?.startsWith('Bearer ')) throw new HttpError(401, 'missing Platform bearer token');
      const parts = value.slice(7).split('.');
      if (parts.length !== 3) throw new HttpError(401, 'invalid Platform bearer token');
      const [encodedHeader, encodedClaims, encodedSignature] = parts;
      const header = JSON.parse(Buffer.from(encodedHeader, 'base64url').toString('utf8')) as { alg?: string; typ?: string };
      if (header.alg !== 'HS256' || header.typ !== 'JWT') throw new HttpError(401, 'unsupported Platform token algorithm');
      const expected = createHmac('sha256', env.PLATFORM_JWT_TEST_SECRET).update(`${encodedHeader}.${encodedClaims}`).digest();
      const supplied = Buffer.from(encodedSignature, 'base64url');
      if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) throw new HttpError(401, 'invalid Platform token signature');
      const claims = platformClaimsSchema.parse(JSON.parse(Buffer.from(encodedClaims, 'base64url').toString('utf8')));
      const now = Math.floor(Date.now() / 1000);
      const audience = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
      if (claims.iss !== env.PLATFORM_JWT_ISSUER || !audience.includes(env.PLATFORM_JWT_AUDIENCE)) throw new HttpError(401, 'invalid Platform token issuer or audience');
      if (claims.exp <= now || (claims.nbf !== undefined && claims.nbf > now)) throw new HttpError(401, 'Platform token is expired or not active');
      if (!req.linkService || claims.service !== req.linkService || !claims.org_entitlements.includes(claims.org_id)) throw new HttpError(403, 'Platform service or organisation entitlement denied');
      req.platformInvocation = { orgId: claims.org_id, service: claims.service, subject: claims.sub };
      next();
    } catch (error) { next(error instanceof z.ZodError ? new HttpError(401, 'invalid Platform token claims') : error); }
  };
}

const librarianClaimsSchema = z.object({ iss:z.string(),aud:z.union([z.string(),z.array(z.string())]),sub:z.string().min(3),exp:z.number().int(),nbf:z.number().int().optional(),org_id:z.string().uuid(),role:z.enum(['proposer','independent_reviewer']) }).strict();
export type InstitutionalJwk=CryptoJsonWebKey&{kid?:string;use?:string;kty?:string};
export interface InstitutionalJwksProvider { get(kid:string):Promise<InstitutionalJwk|undefined>; }

/** Bounded remote JWKS cache. Unknown kids trigger at most one refresh per 30 seconds. */
export class RemoteInstitutionalJwksProvider implements InstitutionalJwksProvider {
  private readonly keys=new Map<string,InstitutionalJwk>(); private expiresAt=0; private lastUnknownRefresh=0; private inFlight?:Promise<void>;
  constructor(private readonly url:string,private readonly ttlMs:number,private readonly fetcher:typeof fetch=fetch){}
  async get(kid:string):Promise<InstitutionalJwk|undefined>{const now=Date.now();if(now<this.expiresAt&&this.keys.has(kid))return this.keys.get(kid);if(now<this.expiresAt&&!this.keys.has(kid)){if(now-this.lastUnknownRefresh<30_000)return undefined;this.lastUnknownRefresh=now;}await this.refresh();return this.keys.get(kid);}
  private async refresh(){if(this.inFlight)return this.inFlight;this.inFlight=(async()=>{const response=await this.fetcher(this.url,{headers:{accept:'application/json'}});if(!response.ok)throw new Error(`institutional JWKS unavailable (${response.status})`);const body=await response.json() as {keys?:InstitutionalJwk[]};if(!Array.isArray(body.keys)||body.keys.length>20)throw new Error('institutional JWKS payload is invalid');const next=new Map<string,InstitutionalJwk>();for(const key of body.keys){if(key.kty==='RSA'&&key.use==='sig'&&typeof key.kid==='string')next.set(key.kid,key);}this.keys.clear();for(const [id,key]of next)this.keys.set(id,key);this.expiresAt=Date.now()+Math.min(this.ttlMs,300_000);})().finally(()=>{this.inFlight=undefined;});return this.inFlight;}
}

function acceptLibrarianClaims(env:AppEnv,claims:z.infer<typeof librarianClaimsSchema>,req:Request,next:NextFunction){const audiences=Array.isArray(claims.aud)?claims.aud:[claims.aud],now=Math.floor(Date.now()/1000);if(claims.iss!==env.LIBRARIAN_JWT_ISSUER||!audiences.includes(env.LIBRARIAN_JWT_AUDIENCE)||claims.exp<=now||(claims.nbf!==undefined&&claims.nbf>now))throw new HttpError(401,'invalid or expired institutional token claims');if(req.platformInvocation&&req.platformInvocation.orgId!==claims.org_id)throw new HttpError(403,'institutional token organization mismatch');req.librarianInstitutional={issuer:claims.iss,actorId:claims.sub,orgId:claims.org_id,role:claims.role};next();}

/** HS256 is test-only; every non-test environment requires governed RS256/JWKS verification. */
export function requireLibrarianInstitutionalClaim(env: AppEnv, injectedProvider?:InstitutionalJwksProvider) {
  const productionProvider=injectedProvider??(env.LIBRARIAN_JWKS_URL?new RemoteInstitutionalJwksProvider(env.LIBRARIAN_JWKS_URL,env.LIBRARIAN_JWKS_CACHE_TTL_SECONDS*1000):undefined);
  return (req: Request, _res: Response, next: NextFunction): void => {
    try {
      const token=req.header('x-librarian-institutional-token'); const parts=token?.split('.')??[]; if(parts.length!==3)throw new HttpError(401,'missing or invalid institutional Librarian token');
      const [headerPart,claimsPart,signaturePart]=parts; const header=JSON.parse(Buffer.from(headerPart,'base64url').toString()) as {alg?:string;typ?:string;kid?:string}; if(header.typ!=='JWT')throw new HttpError(401,'unsupported institutional token type');
      const claims=librarianClaimsSchema.parse(JSON.parse(Buffer.from(claimsPart,'base64url').toString()));
      if(env.NODE_ENV==='test'){
        if(header.alg!=='HS256'||!env.LIBRARIAN_JWT_TEST_SECRET)throw new HttpError(503,'institutional test JWT verifier is not configured');const expected=createHmac('sha256',env.LIBRARIAN_JWT_TEST_SECRET).update(`${headerPart}.${claimsPart}`).digest(),supplied=Buffer.from(signaturePart,'base64url');if(supplied.length!==expected.length||!timingSafeEqual(supplied,expected))throw new HttpError(401,'invalid institutional token signature');acceptLibrarianClaims(env,claims,req,next);return;
      }
      if(header.alg!=='RS256'||!header.kid)throw new HttpError(401,'institutional token requires RS256 and kid');if(!productionProvider)throw new HttpError(503,'live institutional JWKS verifier is not configured');
      productionProvider.get(header.kid).then((jwk)=>{if(!jwk)throw new HttpError(401,'institutional signing key is unknown');const valid=verifySignature('RSA-SHA256',Buffer.from(`${headerPart}.${claimsPart}`),createPublicKey({key:jwk,format:'jwk'}),Buffer.from(signaturePart,'base64url'));if(!valid)throw new HttpError(401,'invalid institutional token signature');acceptLibrarianClaims(env,claims,req,next);}).catch((error)=>next(error instanceof HttpError?error:new HttpError(503,'institutional JWKS verifier unavailable')));
    } catch(error){next(error instanceof z.ZodError?new HttpError(401,'invalid institutional token claims'):error);}
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
