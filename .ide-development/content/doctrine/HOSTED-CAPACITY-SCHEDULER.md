# Hosted-capacity scheduler (Coding Execution Protocol)

**Status:** Canonical for Coding Execution Protocol 1.0.1 amendment `V25_BOOTSTRAP_LEAN`
**Authority:** PKT-01 packaged continuous-utilization contract
**Runtime:** `core/execution/scheduler.py`
**Config:** `core/managed-core/content/config/continuous-utilization.json`
**Schema:** `core/managed-core/schemas/continuous-utilization.schema.json`
**Does not:** dispatch GitHub Actions, paid models, Fast gates, Full Suite, or provider-live jobs

This doctrine is implemented by a **deterministic admission runtime**. Doctrine without that runtime is not the packaged contract.

## Hosted concurrency authority

`hostedConcurrencyAuthority` is `execution-protocol`. GitHub Actions, paid-model brokers, and Fast gates are not admission authorities.

## Slots

Admission limits:

- local: **1**
- Stage 1: up to **5 Cursor + 2 Luna**
- Stage 2: up to **10 Cursor + 4 Luna**, only after routing/integration verification
- Stage 3: up to **20 Cursor + 4 Luna**, only after another verification

Underfill is **1 Luna** in Stages 1-2 and **2 Luna** in Stage 3. Every stage is
further bounded by available Mac memory and real, freshly verified Cursor
capacity; the policy is not a fixed total-worker cap.

The scheduler reports each input separately as provider capacity, spend ceiling,
safety limit, dependency/path constraints, admitted workers, issued workers, and
running workers. Missing, stale, unauthenticated, or mismatched evidence blocks
hosted admission. Evidence is valid only when its exact account, API-key name,
team, and Program Run identity match the scheduler input and freshness is bound
to that identity. Missing or stale components remain individually reported.

Before a new dispatch, all uncompleted PREPARED intents using the retired fixed
cap are atomically marked SUPERSEDED and recomputed under the adaptive policy.
Completed evidence remains immutable; stores that cannot enumerate and read
back intents fail closed.

Admission is deterministic: higher `priority`, then earlier `submitted_at`, then `item_id`. Unmet dependencies and conflict groups block a job without delaying unrelated admitted work.

## Unknown probe and existing backstop

An incomplete snapshot starts an unknown probe. The probe does not occupy a slot. Existing timer recovery remains available; it does not add a 10-minute heartbeat cadence. Busy or exhausted allocator hints are not `capacity_exhausted` while the snapshot is incomplete.

## UTILIZATION_GAP and event recomputation

If a lane has free slots and waiting runnable work, the runtime emits `UTILIZATION_GAP` and does not invent paid fallback. Repair recomputes on `utilization_gap_repair` after a complete snapshot. Recompute also runs on `admission`, `completion`, `invalidation`, `probe_timeout`, and `api_rejection`.

Invalidation delays **only** the invalidated identity. Completion unlocks the slot for the next eligible job.

## API rejection

Hosted API rejection is `hosted_api_rejected`. Requesting paid/Fast fallback is `paid_fallback_forbidden`.

## Proof limits

A scheduled or admitted verdict is not hosted CI proof and does not authorize Review Ready, Fast, or provider mutation.
