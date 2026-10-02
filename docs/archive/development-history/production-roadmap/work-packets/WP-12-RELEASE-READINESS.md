# WP-12 — Security, Legacy Retirement, Deployment Packaging, and Final Pre-VPS Proof

## Objective

Reconcile the completed product, remove or quarantine LiNKaios-era production assumptions, harden supported boundaries, package a reproducible deployment, and produce truthful evidence that all work possible before selecting a VPS is complete.

## Dependencies

WP-09 through WP-11 and the accepted Wave 1–2 foundations. This packet integrates; it does not conceal incomplete upstream packets.

## Owned paths

- Deployment manifests, image/build configuration, CI workflows, release scripts
- Current runbooks, architecture/status documentation, generated inventories
- Legacy LiNKaios references explicitly approved by the inventory
- Cross-cutting security and end-to-end tests

## Required implementation

### Supported-surface reconciliation

1. Generate and review an inventory of services, routes, jobs, schemas, packages, products, workflows, secrets-by-name, external integrations, and deployment artifacts. Every supported runtime path maps to an owner and test.
2. Remove LiNKaios-era branding, scaffold scripts, obsolete runbook instructions, and deprecated compatibility paths from the supported product. Preserve history only in clearly labelled archives where removal would destroy useful evidence. Do not broadly delete by name without dependency searches and tests.
3. Reconcile `README`, architecture, operations, security, API, package authoring, client/operator, incident, backup/restore, and deployment documents with executable behaviour.

### Security and privacy gate

4. Verify authentication/authorisation, organisation isolation, SSRF/egress restrictions, webhook/callback authenticity, replay/idempotency, input/body limits, error/log redaction, dependency/container scanning, least-privilege runtime configuration, non-root containers where feasible, read-only filesystems where feasible, and network boundaries.
5. Prove secrets are referenced by contract and injected at runtime; no values in Git, images, logs, receipts, browser bundles, tests, or database rows. Produce a migration mapping template from old GSM names to the new GSM; do not read or move live values without separate approval.
6. Define data classification, retention/deletion configuration points, backup coverage, and evidence preservation. Unapproved business retention values remain explicit deployment decisions, not hidden constants.

### Reproducible deployment package

7. Pin production images/dependencies, create deterministic builds, health/readiness checks, startup ordering, migration job with checksum and dry-run, seed/publish job for certified packages, worker/scheduler topology, persistent volume requirements, and resource/configuration inventory.
8. Produce Traefik/TLS/DNS and Tailscale/private-boundary templates using placeholders—not invented hostnames. Public website/product API exposure and private operator/n8n/database boundaries must be explicit.
9. Provide forward/rollback procedures for application, migrations, package releases, and n8n workflows. A rollback must preserve audit/evidence records.
10. Provide stage/prod environment matrices for Supabase `linkplatform-stage` and `linkplatform-prod`, n8n, NATS, GSM, auth, payment, alerting, storage, DNS/TLS, backups, and observability. Mark each value `known`, `placeholder`, or `requires_authorisation`.

### Final pre-VPS verification

11. Run formatting, lint, typecheck, unit, integration, package validation, migration lint/test, security checks, disposable n8n eval, backup/restore rehearsal, and browser E2E. Record exact commands, Git SHA, environment, durations, skips, and artifacts.
12. Run a local end-to-end scenario: certified product → signup/fake payment → provisioning → linked invocation/schedule → execution callback → health/telemetry → incident path → maintenance/candidate evidence → canary/rollback → client/operator views.
13. Produce a release-candidate manifest with image/package hashes, schema versions, required migrations, configuration contracts, known limitations, and rollback target.
14. Produce a VPS Deployment Input Register. The next stage must not begin until targets and authority are supplied.

## Mandatory external inputs after this packet

- VPS provider/host, sizing, OS, region, SSH/Tailscale ownership, and backup target.
- DNS names, public/private exposure, Traefik and TLS authority.
- Authorisation to apply migrations to the named Supabase stage project, then production later.
- New GSM project, service identity, access policy, and approved old-to-new secret mapping/migration action.
- Live LiNKplatform auth issuer/audience/role contract.
- Approved payment provider/account, alert recipients, Slack credentials only for automations that use their own Slack nodes, email/storage providers, retention/recovery targets, and production approval.

## Test matrix

- Clean clone/reproducible build and package publication.
- All CI profiles and local end-to-end scenario.
- Negative auth/org isolation, secret scan, redaction, callback/webhook replay, SSRF/egress.
- Migration dry-run, fresh database apply, upgrade from supported baseline, rollback/forward recovery.
- Container health/readiness and dependency failure behaviour.
- Restore rehearsal and release rollback.
- Docs/link/config inventory consistency.

## Acceptance criteria

- All prior packets have accepted evidence or an explicit unresolved blocker; nothing is marked complete by assumption.
- The complete local/pre-VPS suite passes from a documented clean setup.
- LiNKaios is absent from supported runtime/configuration/documentation surfaces, with any retained archive clearly non-authoritative.
- A deployer can identify every required value and command without discovering architecture during deployment.
- No claim is made that stage or production works until live migration, secrets, networking, TLS, integrations, monitoring delivery, smoke tests, backup, canary, and rollback have been proven there.

## Independent audit

A separate Codex Sol Medium subagent performs the final read-only audit. It must verify source, tests, generated artifacts, worktree/Git state, packet evidence, roadmap compliance, security boundaries, and the VPS input register. Verdict is `PASS_PRE_VPS`, `HOLD`, or `FAIL`. It may not edit files. Corrections are dispatched only to implementation agents and re-audited.

## Evidence required at handoff

Release-candidate manifest, full validation ledger, local E2E trace, security/redaction report, legacy-retirement inventory, migration/GSM plan, deployment templates, VPS input register, exact changed files, risks, rollback instructions, and independent audit verdict.

## Stop conditions

Stop before any live Supabase migration, GSM access/migration, DNS/TLS change, VPS provisioning/deployment, payment, customer communication, or production integration call. Those are separately authorised deployment activities.
