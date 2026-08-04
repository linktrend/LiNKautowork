import 'express-serve-static-core';

declare module 'express-serve-static-core' {
  interface Request {
    rawBody?: string;
    linkService?: string;
    platformInvocation?: { orgId: string; service: string; subject: string };
    librarianInstitutional?: { issuer: string; actorId: string; orgId: string; role: 'proposer' | 'independent_reviewer' };
  }
}
