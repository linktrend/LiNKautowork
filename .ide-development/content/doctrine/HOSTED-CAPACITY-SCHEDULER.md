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

Canonical maxima:

- local: **1**
- hosted: **2** (tests may use a third hosted slot only as unused capacity under the same authority)

Admission is deterministic: higher `priority`, then earlier `submitted_at`, then `item_id`. Unmet dependencies and conflict groups block a job without delaying unrelated admitted work.

## Unknown probe and 10-minute backstop

An incomplete snapshot starts an unknown probe. The probe does not occupy a slot. After **600 seconds** the runtime emits `probe_timeout` / timer recovery and recomputes. Busy or exhausted allocator hints are not `capacity_exhausted` while the snapshot is incomplete.

## UTILIZATION_GAP and event recomputation

If a lane has free slots and waiting runnable work, the runtime emits `UTILIZATION_GAP` and does not invent paid fallback. Repair recomputes on `utilization_gap_repair` after a complete snapshot. Recompute also runs on `admission`, `completion`, `invalidation`, `probe_timeout`, and `api_rejection`.

Invalidation delays **only** the invalidated identity. Completion unlocks the slot for the next eligible job.

## API rejection

Hosted API rejection is `hosted_api_rejected`. Requesting paid/Fast fallback is `paid_fallback_forbidden`.

## Proof limits

A scheduled or admitted verdict is not hosted CI proof and does not authorize Review Ready, Fast, or provider mutation.
