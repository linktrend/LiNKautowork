# Provider lifecycle v1

AW-04 is a pure transition guard for AW-02 durable records. It fails closed on changed idempotency fingerprints, CAS mismatch, terminal transitions, and kill-switched starts; it never claims a consumer-domain result.
