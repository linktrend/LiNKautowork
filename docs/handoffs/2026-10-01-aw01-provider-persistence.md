# AW01 provider persistence handoff

- Date: 2026-10-01
- Issue/branch: #197, `issue/197-aw-01-persist-full-provider-requests-and-receipt`
- Base: development `816ad18254ee8bb79555d89eed9b00ec0b38148e`, tree `ffe9381a383d0c61160db18e094dadad34d9ddcb`
- Scope authority: Carlos authorized the provider connection repair; repository owner confirmed AW01 owns migrations and the disposable verification changes do not overlap AW02. Parent owns cross-repository coordination. No live database application, deploy, credential, push, or source promotion was authorized or performed.

## Files inspected

- Repository root and scoped instructions; AW01/AW02/AW03 execution manifest and work packet ownership.
- Existing provider-plane migration, provider persistence contract, `ProviderStore` interface, callers, and provider route contract.
- Existing disposable database harness, setup, provider verification, and rollback flow.
- Supabase skill and official schema-selection documentation.
- Parent/owner coordination states; issue #196 adapter worktree remains untouched.

## Source changes

- Added `supabase/migrations/20261001072550_provider_request_receipt_roundtrip.sql`.
  - Adds nullable object-constrained `request_json` and `receipt_json` to existing provider tables.
  - Replaces provider accept/get/transition/receipt/callback RPC bodies to persist and return the complete contract JSON needed by `ProviderStore`.
  - Preserves historical projection-only rows without invented backfill; affected operations fail closed with explicit unavailable-payload errors.
  - Adds org-scoped kill-switch mutation via SECURITY INVOKER RPC, requires an opaque reason reference, grants execution only to `svc_lautowork_runtime`, and serializes admissions/transitions with global and automation-scoped toggles.
  - Adds a disposable-only down section; it drops the two new JSON columns and their stored payloads.
- Added `packages/automation-contracts/disposable-db/provider-plane-legacy-seed.sql` to create pre-upgrade projected-only request/receipt rows.
- Added `packages/automation-contracts/disposable-db/provider-persistence-verify.sql` for exact request/receipt round-trips, replay conflicts, transitions/attempts, callback receipt, fail-closed legacy rows, tenant isolation, and scoped/global kill-switch behavior.
- Extended `packages/automation-contracts/disposable-db/provider-plane-verify.sql` with column, RPC grant, and gateway non-grant checks.
- Extended `packages/automation-contracts/disposable-db/run.sh` to seed before upgrade, apply the additive migration, run focused verification, then exercise the disposable rollback.

## Contract and dependencies

- Provider route path remains `/v1/provider/*`. Current PACI authorization expects service scope `autowork` and a permitted operation (`read` for GET, `execute` otherwise); the invocation body expects `platform.audience = lautowork` and `platform.capability = catalogue.invoke` for the current canary. Provider operation kinds are `status_collection`, `precheck`, `evidence_collection`, `notification_delivery`, `external_assistance`, `artifact_transform`, `media_package`, and `outreach_adapter`; the current catalogue canary exposes status collection/precheck, and external assistance remains HOLD.
- Provider platform body fields are `org_id`, `actor_id`, `audience`, `capability`, `credential_id`, `binding_id`, `issued_at`, `expires_at`, and `revocation_ref`. Current route code does not bind actor/credential/binding/time/revocation fields to authenticated PACI identity; AW01 persistence does not repair that gap.
- Current provider RPC grants target `svc_lautowork_runtime`; the existing gateway runtime JWT is `svc_lautowork_gateway`. The provider custom schema also needs to be selected with `Content-Profile` for RPC calls. Both are integration-client/role dependencies outside this AW01 change. Do not grant gateway table access as a shortcut.
- The set-kill-switch source interface currently lacks a reason-reference argument; AW02 must reconcile the caller shape with the existing non-null `provider_kill_switches.reason_ref` column before wiring.

## Validation and current state

- `bash -n packages/automation-contracts/disposable-db/run.sh`: passed.
- `git diff --check`: passed.
- `npm --prefix packages/automation-contracts run verify:db`: attempted; failed before container start because the Docker API socket at `/Users/linktrend/.docker/run/docker.sock` was unavailable. No SQL execution was completed.
- Exact cheapest remaining proof: run `npm --prefix packages/automation-contracts run verify:db` once the local Docker daemon is available. It uses the repository's uniquely named disposable Compose project and cleanup trap. If it fails, capture the first SQL/harness error and fix before calling the migration verified.
- No package tests, SQL apply against shared/live databases, credential access, deployment, push, commit, or protected-source promotion were performed.
- Worktree contains only the AW01 migration, the four approved disposable verification files, this handoff, and this session record. Shared checkout caches and issue #196 adapter state remain untouched.

## Exact next action

Parent reviews this bounded source diff. After Docker is available, run the disposable database verifier. Before any migration is applied outside disposable local test, LiNKplatform must review and sequence it under its existing live-migration ownership. AW02 separately resolves caller reason reference, `lautowork` profile selection, and the approved runtime role client. Consumer selection remains HOLD until the PACI actor-binding gap is fixed and proven.
