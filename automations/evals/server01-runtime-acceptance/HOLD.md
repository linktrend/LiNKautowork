# AW-04 HOLD register

This packet records **source-only mock** evidence. The mock now executes
independent behavioral checks (input schema, AW-02/AW-03-compatible
idempotency, transitions, cancellation, callbacks, receipts/redaction).
It still does **not** prove:

- live n8n import, export, activation, or execution on Server01
- disposable real n8n container import/export digest (`eval:full` remains the golden-template Docker path)
- AW-02 durable storage applied on stage or production
- AW-03 live callback ingress or gateway composition
- credentials, GSM resolution, or provider HTTP
- deployment, canary, certified release, or founder acceptance (AW-08)
- consumer Issue, ledger, or gate completion

`n8n_dispatched` is always `false`. `live_n8n_activation` is always `hold`.
Receipts disclaim consumer completion. Fixture operations must not be described
as a live canary, certified release, or rollback.
