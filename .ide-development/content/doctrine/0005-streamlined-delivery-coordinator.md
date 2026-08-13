# ADR 0005: Streamlined delivery with bounded local coordination

**Status:** Accepted for W3-P1 repository integration.
**Date:** 2026-08-13
**Related:** [`../contracts/STREAMLINED-DELIVERY.md`](../contracts/STREAMLINED-DELIVERY.md),
[`../contracts/DELIVERY-MODES.md`](../contracts/DELIVERY-MODES.md),
[`0004-portable-managed-core-v2.md`](0004-portable-managed-core-v2.md)

## Decision

1. Phase integration is a packaged delivery mode. Issue branches remain
   checkpoint-only, and one Integrator-owned Phase branch becomes the reviewable
   delivery unit.
2. The Mac coordinator owns bounded queueing and observation, not authorization.
   GitHub remains authoritative for history, review, statuses, protections, and
   releases.
3. Candidate commands run in disposable Linux containers under explicit CPU,
   memory, PID, timeout, network, mount, and cleanup limits. Protected default
   branch policy is the only execution policy source.
4. Exact Git-tree, dependency, profile, gate, attempt, and evidence identities
   bind receipts. A matching passed receipt is reused for staging/main short
   gates; a changed identity fails closed.
5. Two execution attempts and two sealed candidate revisions are hard limits.
   The second failure stops automatic work and creates one durable alert.
6. Main promotion defaults to principal approval bound to the exact staging
   source, main base, promotion head, and receipt.

## Consequences

The managed package contains shared configuration, receipt, and promotion
interfaces. Host service code remains outside consumer installation. Existing
`issue-pr` and GitHub Actions profiles remain readable. Live canary,
installation, branch protection, PR, merge, promotion, tag, release, and
rollback actions require Terra/operator authority and are not package-agent
actions.

## Rejected alternatives

- GitHub Actions as the primary scheduler: rejected for local-coordinator
  repositories because it creates avoidable high-churn cascades.
- Commit SHA-only receipt reuse: rejected because a different tree or
  dependency content can share or obscure commit-level assumptions.
- Host-shell candidate execution: rejected because candidate code is untrusted.
- Automatic retries without a hard stop: rejected because they can become an
  unbounded repair loop.
