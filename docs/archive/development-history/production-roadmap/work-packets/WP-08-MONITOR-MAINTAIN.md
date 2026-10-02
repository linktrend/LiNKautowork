# WP-08 — Monitoring, Incidents, Maintenance, Canary, and Rollback

## Objective

Create the operational safety system that detects failed or missing automation runs, alerts the correct people, records incidents, performs bounded diagnostics and safe maintenance, and supports tested canary promotion and rollback.

## Dependencies

WP-04 data model, WP-05 instance runtime, and WP-06 trustworthy execution events. WP-07 candidates may consume incident evidence but are not required for detection.

## Owned paths

- `packages/automation-operations/**`
- `gateway/src/services/monitoring/**`
- `gateway/src/services/incidents/**`
- `gateway/src/services/maintenance/**`
- `gateway/src/services/deployments/**`
- Operational API contracts, jobs, runbooks, fixtures, and tests

## Required implementation

### Health and monitoring

1. Derive health from server-side instance policy plus execution events: success/failure rate, consecutive failures, duration, retry count, queue delay, callback delay, and last successful completion.
2. Detect scheduled automations that did not run within declared cadence plus grace. A healthy HTTP process is not evidence that a scheduled business job happened.
3. Distinguish platform, automation-version, instance/configuration, credential, dependency, and unknown failures.
4. Add dependency probes that are safe and rate-limited. Never use destructive business actions as health checks.
5. Expose organisation-scoped health summaries and a private operator-wide view; do not expose raw payloads or secrets.

### Alerts and incidents

6. Implement deduplicated alert policies with severity, routing key, acknowledgement, repeat interval, and recovery notification. Alert integrations are adapters; absence of live Slack/email credentials must not block local proof.
7. Create durable incidents linked to affected instance(s), execution(s), deployment, package release, alerts, diagnostic evidence, actions, and resolution.
8. Implement lifecycle `open`, `acknowledged`, `investigating`, `mitigated`, `resolved`, `closed`; retain append-only history.

### Maintenance and troubleshooting

9. Implement scheduled maintenance checks for version drift, disabled workflows, stale callbacks, expiring/invalid credential references where provider metadata permits, untested dependencies, storage/queue pressure signals, backup freshness, and unresolved incidents.
10. Automated remediation is allow-listed and bounded: retry according to policy, pause an instance, fail over only where explicitly supported, or roll back to a certified release. Credential rotation, schema changes, data deletion, and broad workflow editing require approval.
11. Every action records actor, reason, evidence, before/after state, result, and compensating action.

### Canary and rollback

12. Implement deployment states and a canary policy using selected non-production/test instances or an explicitly approved fraction. Compare the candidate against a certified baseline with minimum sample and time windows.
13. Promotion requires compatible bindings, current certification, healthy canary evidence, and authorised approval. Rollback is idempotent and restores the last certified deployment without deleting evidence.
14. Provide break-glass pause/kill controls scoped globally, by automation, organisation, or instance, with audit records.

### Backup and restore proof

15. Define backup artifacts for control data, catalogue packages/receipts, and n8n workflow/configuration state. Implement a disposable local restore rehearsal proving recovery steps; do not claim live disaster recovery.

## Test matrix

- Success, single failure, repeated failure, missing scheduled run, slow run, missing callback.
- Alert deduplication, acknowledgement, recovery, and adapter failure.
- Incident lifecycle and append-only history.
- Allowed remediation succeeds; forbidden remediation is rejected.
- Canary pass, insufficient evidence, regression, and automatic rollback policy.
- Global/automation/org/instance pause precedence.
- Disposable backup/restore with integrity hashes.
- Organisation and redaction boundaries on all views.

## Acceptance criteria

- A simulated missing run opens one incident and sends one deduplicated adapter alert.
- A regressing candidate cannot promote and can be rolled back to the certified baseline.
- Maintenance actions are explainable, bounded, reversible where applicable, and fully audited.
- Local restore rehearsal proves control records and workflow references can be reconstructed.
- Monitoring itself exposes health and failed-job signals.

## Evidence required at handoff

Scenario matrix/results, example redacted incident timeline, alert proof, canary/rollback proof, restore rehearsal report, changed files, risks, and rollback instructions.

## Stop conditions

Do not select real alert recipients, retention periods, recovery targets, or production auto-remediation authority without Principal-approved policy. Implement configuration contracts and safe defaults, then record these as deployment inputs.
