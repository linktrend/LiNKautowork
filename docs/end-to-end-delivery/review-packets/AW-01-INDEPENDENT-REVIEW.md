# AW-01 independent review instruction

Role: **independent-review**. This instruction is stable; the coordinator dispatch
packet supplies the exact issue branch, base commit/tree and candidate commit/tree.
Stop on any repository, ref, commit or tree mismatch.

Review AW-01 only against its supplied base. Make no tracked-file edits, commits,
pushes, issues, PRs, checks, merges, deployments or external mutations. Do not use
Platform credentials, provider credentials, live databases or Server01. Dependency
installation and disposable local test resources are allowed inside the isolated
review worker.

Verify all of the following:

1. The candidate diff is confined to `supabase/migrations/**`,
   `docs/contracts/server01/**`, and
   `packages/automation-contracts/tests/server01-*.test.ts`.
2. Migration ordering and hashes are deterministic and the package is additive,
   replay-safe and compatible with both fresh install and upgrade.
3. Organisation isolation, least-privilege roles/grants, append-only receipts,
   idempotent `PREPARED`/outbox behavior, authenticated callback replay handling,
   secret-free evidence and recovery/partial-apply refusal satisfy AW-01.
4. The package does not store task bodies or secrets, grant portfolio/Program
   authority, modify consumer ledgers, or claim live Platform application.
5. Every AW-01 manifest verification command and documented minimum validation is
   run. Where a disposable dependency is genuinely unavailable, report the exact
   command and evidence gap rather than substituting a claim.

The final response begins exactly `PASS` or `FAIL`, then reports concise file/line
findings, exact starting/final identities, commands and results, toolchain, and
remaining HOLDs. PASS is source-only; Platform application receipts and Server01
acceptance remain later gates. Do not propose or implement fixes in this review.
