# Provider Persistence v1

AW-02 adds source-only, additive tenant-isolated request, attempt, receipt, event, outbox, and kill-switch storage. It stores references and digests only. Same org/idempotency reuse is constrained by a unique key; route-layer admission must compare the AW-01 canonical fingerprint and quarantine changed content. Stage migration application, credentials, live queue behavior, external dispatch, consumer E2E, and production remain HOLD.
