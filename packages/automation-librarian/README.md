# Automation-mode institutional Librarian adapter

This package names the LiNKautowork integration boundary. Its implementation is deliberately in `gateway/src/services/librarian/`: only the gateway may enforce the automation organisation, redaction, kill/pause, and review boundaries.

The future institutional host must accept only the strict `librarian-automation` contract: `domain: "automation"`, immutable `evidence://` references with SHA-256 hashes, a canonical `orgId`, model/prompt/policy audit metadata, and a machine-readable candidate patch reference. It must return the same candidate ID and lifecycle transitions. It must not receive credentials, raw execution/client payloads, or LiNKskills/LiNKbrain records.

The gateway persists candidate, audit, deduplication, kill/pause, and review state through organisation-authorized Supabase RPCs called with the scoped runtime JWT. Production institutional actor identity requires RS256, `kid`, a governed issuer/audience/JWKS URL, bounded key caching, and signed org/subject/role/time claims. HS256 is accepted only under `NODE_ENV=test`. WP-06 receipts retain their native HMAC envelope and are verified through a governed key ID/GSM reference. This is a local contract and disposable database path, not a claim that the external institutional host is live.
