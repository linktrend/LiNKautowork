# Server01 contract / version matrix

Pinned for AW-01 source freeze. Live consumer proof is HOLD.

| Contract | Version | Owner | Use |
|---|---|---|---|
| `platform.auth-claims` | `1.1.0` | LiNKplatform | Exact camelCase claims; Autowork consumes, does not issue |
| PACI token envelope | ES256, 15-minute TTL, no refresh | LiNKplatform | Production machine tokens; issuer/audience/scopes HOLD until Platform receipts |
| Provider family | `2026-08-13.v1` | LiNKautowork | Existing request/attempt/receipt/callback/outbox persistence |
| Server01 live interfaces | `lautowork.server01.migration-identity/1.0.0` | LiNKautowork authored / Platform applied | Invocation, PREPARED intent, callback, receipt, credential bindings, roles, fingerprint |
| Golden Automation Package | `v0.1` | LiNKautowork | Release identity consumed by catalogue migrations |
| n8n | `2.30.0` | LiNKautowork runtime / n8n upstream schema | Isolated `lautowork_n8n` only |
| Platform protected `development` | commit `f6373fccc89732cbb88bb18562daa69cc031a2e3` tree `83feddf7d935561cfede60df456ea616a021d726` | LiNKplatform | Mechanical rebaseline; no Autowork schema change |

## Invocation fields (Server01)

Required persisted fields (no task body, no secret value):

- `work_ref`, `authority_ref` — opaque Program work and authority
- Platform binding: `actor_id`, `audience`, `capability`, `credential_id`, `binding_id`, `credential_binding_ref`
- Exact automation: id/version/definition digest/configuration ref+digest
- `allowed_operation`, `operation_kind`, `input_ref`+digest, `idempotency_key`, `request_fingerprint`
- `callback_binding_ref`, `budget_ceiling_ref`, `expires_at`
- Atomic `PREPARED` intent + `prepared_intent` outbox row

Receipts are immutable, fingerprint-bound, and `does_not_complete_consumer = true`.
