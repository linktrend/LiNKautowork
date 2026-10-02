# C-W3-10 — commercial snapshot and ordered webhook correction

## Scope

This correction is limited to Wave 3 blockers 3 and 4: the governed commercial publication/order/subscription/provisioning path, the signed Product API webhook boundary, the disposable durable database verifier, focused Product API/client tests, and this evidence record. It does not add a payment provider, payment collection, credential intake, VPS mutation, or live customer action.

## Durable contract

- `product_offering_publications` is the pre-VPS publication read model. A published row is immutable, must reference a certified release, and carries the immutable offering version, release id/package digest/workflow digest, terms document id/version/digest, non-charging commercial descriptor, and safe configuration schema/version.
- Order creation selects the currently published certified publication and inserts its complete snapshot atomically in the same database transaction. Idempotent retries return the original snapshot even if a later publication exists.
- Terms acceptance requires an exact match for all three snapshotted authoritative terms values. Subscription creation and provisioning re-check the snapshotted certified release id and digests; they do not substitute a later current offering or release.
- Provider receipts persist the signed event id, allow-listed event type, provider `occurredAt`, and positive monotonic provider sequence. Locked transitions cover payment success/failure/refund and bounded provisioning completion/failure. Stale sequence/time, conflicting event ids, invalid lifecycle transitions, and forged signatures fail closed.

## Evidence commands

```text
npm --prefix apps/product-api run test
npm --prefix apps/product-api run typecheck
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm run verify:automation-librarian-db
npm --prefix apps/web run test:browser
```

The durable verifier includes a real HTTP Product API server backed by the disposable PostgREST service. It proves signed success/failure, forged-signature rejection, exact duplicate, duplicate after Product API restart, and stale/out-of-order rejection. It does not call the internal lifecycle transition as a substitute for the HTTP proof.

## Environment boundary

The canonical durable checks require Docker Compose, PostgreSQL/PostgREST, and the repository’s installed Node toolchain. No live services, provider credentials, payment account, secrets, migration target, or deployment authority are fabricated by this correction. If the local CLI cannot access the Docker socket, the exact master commands above remain the required rerun on a Docker-enabled verification host.
