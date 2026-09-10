# AW-01 Bugbot repair independent review

Review the exact issue #133 repair candidate read-only:

- Repository: `https://github.com/linktrend/LiNKautowork`
- Ref: `issue/133-repair-aw-01-final-bugbot-database-findings`
- Repair base: `0a4ffc2a667ad54b90d3a2d8e6af3103ea08ac0d`
- Candidate commit: `8299ba41aab61a59109d9a79cefba641b782dac6`
- Candidate tree: `b915e628dd03ded1bff1d70c404e4dea7f196448`

The accepted AW-01 candidate and fixture repair remain unchanged outside this
five-file repair. Verify the exact candidate resolves all three Bugbot findings
from Phase PR #132 / check `102818570314`:

1. `server01_live_fingerprint` must enumerate grants from authoritative PostgreSQL
   catalog ACL data, independent of the caller role, with deterministic ordering.
   Prove the same fingerprint and package status for every role granted EXECUTE.
2. Concurrent identical `server01_accept_invocation` requests must produce one
   fresh result and one replay; concurrent differing fingerprints must retain an
   explicit conflict. Confirm this is proved with real independent database
   sessions, not sequential calls.
3. `server01_admit_callback` must reject a mismatch between the outer callback
   request ID and receipt request ID before any receipt, callback, or outbox
   write. Confirm a valid callback and exact replay still succeed afterwards.

Review only these paths:

- `.github/linktrend-secret-scan-fixtures.json`
- `docs/contracts/server01/MIGRATION-PACKAGE.json`
- `docs/contracts/server01/verification.sql`
- `packages/automation-contracts/tests/server01-live-interfaces.test.ts`
- `supabase/migrations/20260910_000001_lautowork_server01_live_interfaces.sql`

Run the secret scan, Fast profile, automation-contract tests, `verify:db` with
Docker, and `git diff --check` against the repair base. Verify package hashes and
the fixture declaration converge and bind to this candidate. Distinguish any
cloud Docker/bootstrap defect from a source defect. Return `PASS` or `FAIL`
first, then exact identities, file/line findings, commands/results, and remaining
HOLDs. Do not edit, commit, push, open a PR, publish checks, merge, deploy,
access Server01/providers/credentials, or dispatch workers.
