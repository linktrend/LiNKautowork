# Receipt seal and recovery (Update 6 / WP-U06)

**Status:** Active for `v2.4.0` WP-U06.
**Authority:** frozen `issue/307` Update 6 / `AC-U06-01`–`AC-U06-10`.
**Implementation:** `scripts/gitops/receipt_seal.py` (identity format unchanged: FullSuiteReceipt schemaVersion 2).

## Normal path

1. Packager/Coordinator seals a Phase candidate only after Fast and repository CI pass.
2. Full Suite checks out the **canonical PR head** (never `refs/pull/<n>/merge` as identity).
3. Synthetic merge-ref SHA/tree may be recorded only as separately labelled integration evidence (`mergeRefEvidence.promotableIdentity=false`).
4. Ordinary Phase merge into `development` requires the exact retained Full receipt bound to that head/tree (`phase_merge_eligibility_with_receipt`).
5. Controllers must not merge first and obtain a receipt afterward.

## Receipt discovery and selection

- Enumerate and classify every candidate artifact before selecting one.
- Inaccessible/stale/unrelated artifacts are recorded and skipped.
- Selection fails closed when the exact expected receipt is missing, inaccessible, malformed, duplicated, stale, or wrong-head/tree.
- Skipping an unrelated artifact never converts a non-matching receipt into success.

## Recovery path

For an already-integrated, unchanged `development` tree that lacks a retained receipt:

- Dispatch `Linktrend Full Suite` with `mode=recovery` on the exact development commit/tree.
- Preconditions: clean checkout, exact installed manifest, declared checks success on that tree, matching dependency digest.
- Recovery does **not** open a PR, create an empty commit, or authorize a different tree.
- The produced receipt uses the same schemaVersion 2 identity guarantees and is reusable for unchanged staging/main promotion; any content change fails closed.

## Rollback

- Do not invent empty commits or empty PRs.
- Leave issue branches unmerged when blocked.
- Prefer failing closed over weakened identity.

## Related

- `docs/contracts/STREAMLINED-DELIVERY.md`
- `scripts/gitops/coordinator/receipts.py`
- `scripts/gitops/promotion_receipt_gate.py`
- `scripts/gitops/phase_integrator.py`
