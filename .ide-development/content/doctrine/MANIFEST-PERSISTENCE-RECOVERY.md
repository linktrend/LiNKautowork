# PKT-08 manifest persistence recovery

Canonical lifecycle manifests use compare-and-retry persistence. Every write
reads the current revision and digest immediately before compare-and-write,
then performs a fresh readback and compares revision, digest, and canonical
payload bytes. Conflicts and readback misses retry only within the configured
bound.

On a later heartbeat, missing dispatch, run, integration, and archive
transitions may be reconstructed only from identity-bound Cursor API, GitHub,
and Git observations. Conversation text is never authority. A transition is
identified deterministically from its kind, canonical identity, and authority
identity, so recovery is idempotent. Existing dispatch evidence suppresses any
duplicate dispatch.

Transient authority or storage misses do not notify a human immediately.
Repeated bounded failure returns a blocked, fail-closed result with a durable
diagnostic. No fallback weakens protected gates or secret scanning.

The installed executable boundary is
`scripts/gitops/heartbeat_controller.py`. It uses a compare-and-swap manifest
file, a compare-and-swap dispatch-intent file, and an idempotent durable outbox.
An actionable persisted repair may return success only after the outbox entry
and updated manifest are both read back. `DONT_NOTIFY` is allowed only with the
verified no-action receipt; missing runtime dependencies return actionable
failure rather than quiet success.
