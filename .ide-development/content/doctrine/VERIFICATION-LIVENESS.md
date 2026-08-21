# PKT-08 verification liveness

**Status:** Founder-authorized v2.5 amendment
**Amendment:** `V25_PKT08_VERIFICATION_LIVENESS`
**Runtime:** `core/execution/verification_liveness.py`
**Config:** `core/managed-core/content/config/verification-liveness.json`
**Schema:** `core/managed-core/schemas/verification-run.schema.json`

Long `Full` verification is admitted only as a durable, exact-candidate-bound
run. The record binds repository, canonical checkout, cwd, commit, tree,
argv digest, deterministic log and receipt paths, UTC start, timeout, durable
handle, and state. The only persisted states are:

`STARTED`, `LIVE`, `TERMINAL`, `ORPHANED`, `TIMED_OUT`, `RESTARTED`.

Observed `RUNNING` is a handle status, not a durable completion claim.
Heartbeat reconciliation rejects stale `RUNNING`, missing or dead handles,
completed hosted checks still recorded as running, command/log/receipt/
repository/commit/tree mismatches, and duplicate same-tree `Full` runs.

Checkout, cwd, log, and receipt equality is based on the physical canonical
path (`realpath`), allowing platform aliases such as macOS `/var` and
`/private/var` only when they resolve to the same target. Different physical
targets remain mismatches.

An incomplete orphan may be restarted automatically once. A terminal or
timed-out run, or an orphan that has exhausted its restart budget, is held.
The restart retains the same identity and deterministic artifact paths while
recording a new durable handle and refreshed timestamps.

This package surface is local-contract proof only. It never dispatches paid or
Fast checks, pushes protected refs, merges, or publishes Review Ready.
