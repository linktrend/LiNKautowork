# PKT-08 revision-60 final controls

**Amendment:** `V25_PKT08_REVISION_60_FINAL_CONTROLS`

This contract governs the permanent final controls for external dispatch and
design authority. It is consumed by the execution runtime and is independent
of any consumer product or provider workflow.

## Transactional external dispatch

1. The runtime derives one idempotency key from the packet, exact repository /
   commit / tree identity, action, and canonical request payload.
2. It writes a `PREPARED` dispatch intent durably before calling the external
   API. The write uses compare-and-set and an immediate readback of the same
   revision, digest, and payload.
3. A successful external dispatch is HTTP `201`. If the caller is interrupted
   after a `201` was accepted, the runtime reads the external authority by the
   idempotency key and recovers the dispatch instead of calling the API again.
4. The intent is committed with CAS and read back in the same turn. A CAS
   collision retries only within the configured bound and never redispatches.
5. The deadline-budget guard runs before every transactional turn. Insufficient
   budget fails closed before a durable write or external side effect.
6. A repeated wake finds the committed intent and suppresses duplicate logical
   dispatch.

The runtime requires a current packet-repository lease. Stale or mismatched
leases, malformed authority responses, and exhausted CAS attempts fail closed.

## Approved-manifest design authority

Only an `APPROVED` design authority record in the exact manifest, with a
manifest digest, can authorize design completion. Conversation text and
executor claims are never authority. When the manifest is approved, redundant
executor design approval is suppressed.

An unsolicited terminal `design-only` result may automatically resume exactly
once. The resume marker is deterministic from the approved manifest digest and
result id, and a repeated wake is suppressed by the durable marker. Nonterminal,
solicited, or non-design results do not resume automatically.
