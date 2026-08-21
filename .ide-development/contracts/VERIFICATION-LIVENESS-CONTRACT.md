# PKT-08 durable verification-liveness contract

**Status:** Founder-authorized v2.5 amendment
**Amendment:** `V25_PKT08_VERIFICATION_LIVENESS`
**Runtime:** `core/execution/verification_liveness.py`
**Schema:** `core/contracts/VERIFICATION-RUN.schema.json`

This contract governs long-running `Full` verification commands. It is
checkout-bound and fail-closed. It does not authorize paid models, Fast
checks, protected pushes, merges, Review Ready publication, or hosted
provider mutation.

## Durable run binding

Every run records:

- the packet and `Full` profile;
- repository, canonical checkout, and exact working directory;
- exact commit and Git tree;
- argv and a deterministic SHA-256 command digest;
- deterministic `.linktrend/verification/<runId>.log` and
  `.linktrend/verification/<runId>.receipt.json` paths;
- UTC start and last-heartbeat times plus a timeout;
- a durable local PID or hosted-check handle;
- one of `STARTED`, `LIVE`, `TERMINAL`, `ORPHANED`, `TIMED_OUT`, or
  `RESTARTED`.

The canonical checkout and cwd must resolve to the same directory. A
reconciliation input that changes command, artifact paths, repository, commit,
or tree is rejected; no field is silently repaired. Path equality uses the
physical canonical path (`realpath`), so platform aliases such as macOS
`/var` and `/private/var` are equivalent only when they resolve to the same
target.

## Heartbeat reconciliation

`RUNNING` is an observed handle status, not a persisted run state. A
`RUNNING` observation is accepted only while the heartbeat is fresh and the
durable handle is present, has the expected identity, and is alive. Reconcile
rejects:

- stale `RUNNING` observations;
- missing, dead, or mismatched durable handles;
- a hosted check that completed while its run remains nonterminal;
- command, log, receipt, repository, commit, or tree mismatches;
- duplicate `Full` execution for the same repository, commit, and tree.

Timeout is terminal for automatic recovery and produces `TIMED_OUT`.

## Recovery

Missing or dead handles and stale heartbeats produce `ORPHANED` only when the
command is incomplete. Automatic restart is permitted only for an
`ORPHANED` run without completion evidence and only within the configured
restart limit. Completed and timed-out commands cannot restart. The default
automatic restart budget is one.

`RESTARTED` is a durable transition with a new handle and refreshed start and
heartbeat timestamps. The same run identity and deterministic artifact paths
are retained, so a restart cannot create an untracked execution.

## Package parity

The runtime, canonical contract/schema, managed config/schema/example, and this
doctrine are all explicit managed package entries. An extracted package must
validate the same example without importing the IDE Development checkout.
