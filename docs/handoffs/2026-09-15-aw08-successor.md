# AW08 successor checkpoint

Standing Portfolio Successor Launch Authorization v1 governs this work. Source
work is on Issue159; no protected integration or live acceptance is claimed by
this checkpoint. No subagents or external coding workers were used.

## Changes

- Product API uses its dedicated transport JWT and separate publishable API key.
  File 17 grants audited RPCs, revokes legacy Product API transport access, and
  preserves audit checks for nested provisioning.
- Production gateway verifies canonical PACI and uncached authenticated live
  introspection using a pinned GSM client PEM reference. It never reads an
  issuer private key or infers browser/operator permissions.
- File 18 grants the dedicated gateway role the existing durable v2 execution
  surface and org-filtered kill-switch hydration. Production removes the broad
  default bearer path. First sixteen migration bytes are preserved.
- The actual minimum workflow is the existing v2 instance executor: durable
  binding and digest checks, acceptance/idempotency, real n8n dispatch, and
  capability-bound callback persistence. v1 activation remains disabled.

## Validation and review

Lightweight env/secret/diff checks run locally. Dependency installation failed
on Mac disk exhaustion; its own partial node_modules was removed with coordinator
authorization. No local containers, installs, or heavy builds are permitted.
All database, browser, and TypeScript checks run in hosted CI.

Independent review rejected b59faf2 because legacy Product API SQL grants
remained. This checkpoint repairs that finding and needs a new exact-candidate
review. Its hosted CI also reached the browser journey and exposed nested
provisioning rejecting the scoped Product API role; the audited delegation guard
is repaired here. Do not reuse either historical candidate as release evidence.

## Host dependencies and acceptance

Platform owner must integrate the narrow introspection grant/ACL and provision
org-bound gateway and Product API JWT references plus a separate publishable API
key. Existing four-secret access does not supply these runtime credentials.
Server01 owner controls host changes. Final release requires exact source/tree,
image and migration hashes, live registration, private no-external-effects n8n
workflow, durable receipt/replay, restart persistence, and backup/isolated restore
and rollback proof. None of those live proofs is supplied by source-only tests.
