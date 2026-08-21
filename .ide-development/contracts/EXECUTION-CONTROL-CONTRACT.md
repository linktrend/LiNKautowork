# Execution Control Contract

**Status:** Canonical for Coding Execution Protocol 1.0.1 amendment `V25_BOOTSTRAP_LEAN`
**Consumes:** `core/execution/CODING-EXECUTION-PROTOCOL.md`
**Schema:** `core/contracts/EXECUTION-MANIFEST.schema.json`

This contract governs execution-manifest controls. It does not implement delivery workflows, GitHub Actions, or publisher YAML.

## Producer and consumer

- Producer: program planner that emits a schema-valid execution-manifest.
- Consumer: implementer runtime that validates the manifest, discovers protocol surfaces, and evaluates control decisions before mutation.

## Exact-candidate invalidation

A candidate identity is the tuple:

`repository + commit + tree` and, when supplied, `workflowDigest` and `profileDigest`.

A later head, tree, repository, or bound digest **invalidates** the previous candidate. Seals, reviews, receipts, and late success for the previous identity must be rejected. Checkpoints may record Git state without sealing.

## Bounded retry

| Failure class | Attempts | Next |
|---|---|---|
| Ordinary source repair | at most 3 | fourth attempt stops |
| Infrastructure on the same exact candidate | 2 total | second failure stops; no third try |
| Code or test failure | 0 automatic retries | return to development / repair on a new identity |

Unknown failure classes stop. Retry is never a reason to prefer-incoming.

## Orchestration lease

Packet mutation requires a lease scoped to `packet-repository`.

- A live lease from another holder is `orchestration_lease_held`.
- An expired lease cannot authorize mutation.
- Holder, packet id, and repository must match.

Discovery and schema validation do not require a lease.

## Resource uncertainty

Admission fails closed when the resource snapshot is missing or any of `cpu_percent`, `memory_percent`, `free_disk_gib`, or `docker_available` is unknown. Uncertainty is a blocker, not an invitation to guess. Interactive-use pressure also refuses admission.

A busy or exhausted allocator response is not a final capacity diagnosis until the snapshot is complete; incomplete snapshots remain `resource_uncertain`.

## Durable heartbeat write/readback

Packet mutation (RUNNING) requires a durable heartbeat:

1. write the heartbeat record (packet, attempt, sequence, checkout commit/tree)
2. read it back from the same store
3. admit only when the readback matches the written record and the checkout identity

A missing write, missing readback, mutated readback, or unbound commit/tree is `heartbeat_readback_missing` / `heartbeat_identity_unbound`. Memory-only or event-only heartbeats are not durable.

## Checkout-bound verification receipts

A verification receipt is accepted only when it binds to the exact checkout identity `repository + commit + tree`.

- `refs/pull/<n>/merge` is merge-ref identity and is never promotable.
- Merge-ref evidence, when recorded, must set `promotableIdentity=false` and cannot complete a packet.
- COMPLETE / ARCHIVE_CONFIRMED packets require a checkout-bound receipt whose commit and tree match `acceptedCommit` / `acceptedTree`.

## Retry-exhaustion diagnosis and recovery

When `retry_decision` stops, the runtime must diagnose before any further attempt:

| Exhaustion reason | Recovery |
|---|---|
| `ordinary_source_exhausted` | new identity (new commit/tree) |
| `infrastructure_stopped` | hold; named exception or new identity |
| `code_failure_no_retry` | new identity |

Silent retry on the same repository/commit/tree after exhaustion is forbidden (`silent_retry_after_exhaustion`). Undiagnosed exhaustion on a live packet is `retry_exhaustion_undiagnosed`.

## Hosted-capacity scheduler

Hosted scheduling is a **deterministic runtime** (`core/execution/scheduler.py`) bound to the packaged continuous-utilization config:

- `hostedConcurrencyAuthority` is `execution-protocol` (not GitHub, paid models, or Fast).
- Canonical slot maxima are local `1` and hosted `2`.
- Incomplete snapshots stay `resource_uncertain`. Allocator `busy` / `exhausted` in that state is not `capacity_exhausted`.
- Unknown probes do not occupy slots. After 600 seconds the runtime recovers and recomputes.
- Free slots with waiting runnable work emit `UTILIZATION_GAP`; repair recomputes after a complete snapshot.
- Completion unlocks a slot. Invalidation delays only that identity.
- Hosted API rejection must not fall back to paid/Fast (`paid_fallback_forbidden`).
- This contract does not start paid models, Fast gates, or hosted CI.

## Automatic approval rules

| Action | Decision |
|---|---|
| `checkpoint`, `issue_commit` | automatic |
| `staging_promote` | automatic when receipt identity holds (this contract does not evaluate receipts) |
| `main_promote`, `publish_release`, `deploy_production`, `github_protection_change`, `provider_live_mutation` | founder approval must already be recorded for the exact action |
| `self_review`, `self_merge`, `prefer_incoming` | forbidden |

Absence of a recorded founder approval is not a request to invent one.

## Repository and Git authority

- Work branches match `issue/<n>-<slug>`.
- Protected refs: `development`, `staging`, `main`. Implementers must not push them.
- Implementers must not open or merge delivery PRs.
- Nested `.ide-development` install into this system repository is forbidden.
- Packager / packager coordinator opens Phase PRs.
- Delivery controller merges to `development` through protection.

This contract does not change workflow files. It forbids claiming Git authority the workflows have not granted.

## v2.5 Issue checkpoint (`V25_BOOTSTRAP_LEAN`)

A v2.5 Issue checkpoint is accepted when all of the following are present:

1. exact pushed commit and tree
2. scoped diff
3. focused tests
4. independent Terra verification
5. manifest evidence

Review Ready publication and publisher tokens are **not** required and must not block that acceptance.

## Publisher authority (no singular legacy canonical)

`canonicalForV25` is `none`. No singular legacy publisher is canonical for v2.5, including `linktrend-review-ready-publisher`, `mark-review-ready.sh-as-publisher`, `.linktrend/review-ready.json`, and user-PAT publication.

A failed or missing legacy publisher is classified **`WAIVED_LEGACY_GATE`**. That classification is never PASS and never an implementation failure.

Delivery and workflow implementation remain owned by other packets.

## Administrator recovery

A later exact-head administrator recovery is allowed only as a **named** exception, only after substantive replacement proof, and only for:

- `protection_snapshot`
- `restore`
- `readback`

Unnamed recovery, recovery without replacement proof, or any other operation is forbidden by this control contract.

## Semantic lifecycle (beyond JSON Schema)

`validate_execution_lifecycle` / `validate_plan_or_runtime` reject inconsistent manifests. They do not silently normalize fields. Every diagnostic names `packet=<id> attempt=<id|->`.

- `COMPLETE` and `ARCHIVE_CONFIRMED` require a valid accepted commit/tree plus packet-level `packet_completion` evidence bound to that identity, and a checkout-bound verification receipt for that identity. Event-only or empty completion evidence is rejected.
- `ARCHIVE_CONFIRMED` additionally requires archive API readback evidence.
- Every attempt on a completed packet must be terminal: `lifecycle=TERMINAL`, terminal `rawStatus`, `endedAt`, and `result` or `reason`.
- `RUNNING` requires exactly one authoritative nonterminal current attempt, that attempt's active write lock, a current orchestration lease, and a durable heartbeat with matching readback. Prior repaired terminal attempts may remain.
- Exhausted retries on a live packet require an exhaustion diagnosis; silent same-identity retry is rejected.
- Completed packets must not retain an active write lock.
- `COMPLETE` plus a RUNNING attempt is rejected.

## LiNKautowork automation discovery

When Autowork discovery is callable, it is required. Skipping a callable discovery is a control violation.

When discovery is not callable, the truthful result is an unavailable hold. That hold is not hosted, provider-live, application, consumer, staging, VPS, E2E, or production proof.

## PKT-08 revision-60 final controls

The paired contract
`PKT08-REVISION-60-FINAL-CONTROLS.md` and schema
`core/managed-core/schemas/transactional-dispatch.schema.json` are mandatory
for the permanent final controls.

- External dispatch derives a deterministic request-bound idempotency key and
  durably writes `PREPARED` before any API call.
- HTTP `201` response interruption is recovered only by authoritative lookup
  using that key. The runtime CAS-commits and reads back the committed intent
  in the same turn, bounded to three attempts, and never redispatches after a
  collision or duplicate wake.
- A live packet-repository lease and sufficient deadline budget are required
  before any write or external call. Stale leases and insufficient budgets
  fail closed.
- Only an `APPROVED` manifest design record bound to a manifest digest is
  authoritative. Conversation text cannot grant design approval.
- Approved manifests suppress redundant executor design approvals. One
  unsolicited terminal `design-only` result may automatically resume through a
  deterministic durable marker; later wakes are suppressed.
