# Provider Persistence v1

AW-02 adds source-only, additive tenant-isolated request, attempt, receipt, event, outbox, and kill-switch storage. It stores references and digests only. The provider store compares the AW-01 canonical fingerprint for each `(org_id,idempotency_key)`: identical content replays the original logical request; changed content fails closed. Atomic `SECURITY INVOKER` RPCs retain the org-scoped runtime-JWT/RLS boundary for acceptance and CAS lifecycle transitions; no service-role bypass exists. Receipts are immutable and configuration-bound, while events are organization-scoped and cursor-bounded. Stage migration application, credentials, live queue behavior, external dispatch, consumer E2E, and production remain HOLD.

## Source boundary

- **Interface input:** AW-01 `packages/automation-contracts/src/provider-contract.ts` at `issue/133` commit `d60ebe7eb58acc94ddfc16e6514fd18b13fe2c25` (read-only). This packet does not merge or alter that branch.
- **Persistence types:** `packages/automation-contracts/src/provider-persistence.ts`.
- **Durable store:** `gateway/src/services/provider-store.ts` models the invoker RPC names `linkautowork_provider_accept`, `linkautowork_provider_get_request`, `linkautowork_provider_transition`, `linkautowork_provider_write_receipt`, `linkautowork_provider_admit_callback`, `linkautowork_provider_append_event`, `linkautowork_provider_list_events`, and `linkautowork_provider_kill_switch_active`.
- **Admission lifecycle:** `gateway/src/services/provider-admission.ts` plus source-only `/v2/provider/*` routes in `gateway/src/routes/provider-v2/`.
- **SQL apply:** repository migration files are not owned by this packet. Local SQL is not stage or production evidence.

## Invariants

1. Every invoker call requires `jwt_role=runtime` and `claim_org_id = org_id`. `service_role`, `anon`, and `public` fail closed.
2. Fingerprints are the AW-01 canonical digest. Replay returns the original logical request; any other canonical field change is `conflict`.
3. Receipts bind `automation_id`, version, and configuration digest. A second receipt id for the same request is immutable-conflict.
4. Events carry payload references and digests only, are isolated by `org_id`, and reject cursor limits outside `1..100`.
5. Outbox rows are stored as `pending` event-delivery intent. Live drain, credentials, and provider activation are HOLD.

## HOLD register

- Stage/production migration application
- Live runtime JWT issuance and RLS enforcement on a shared target
- Live outbox/queue delivery
- Provider activation, credentials, and external dispatch
- Consumer E2E and production readiness
