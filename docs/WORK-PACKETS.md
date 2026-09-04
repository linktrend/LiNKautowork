# LiNKautowork production work packets

These packets describe the remaining configuration, testing, deployment, and production work. They do not reopen completed pre-configuration engineering.

| Packet | Remaining outcome | Current state |
|---|---|---|
| PROD-01 | Bind exact LiNKharness, LiNKprofiles, OSS, SDK, and cross-repository release identities | READY_FOR_CONFIGURATION |
| PROD-02 | Configure Cursor and Codex executors, permitted tools, budgets, retries, and fail-closed routing | HOLD_FOR_ENVIRONMENT_VALUES |
| PROD-03 | Configure external providers using approved sandbox accounts and capability readback | HOLD_FOR_PROVIDER_ACCESS |
| PROD-04 | Configure Program-to-Program adapters and record producer/consumer conformance | HOLD_FOR_COUNTERPART_CONFIGURATION |
| PROD-05 | Create or enable LiNKautowork automations, schedules, escalation, idempotency, and rollback | HOLD_FOR_AUTOMATION_CONFIGURATION |
| PROD-06 | Supply secrets, domains, certificates, storage, queues, databases, and network policy | HOLD_FOR_SECURE_CONFIGURATION |
| PROD-07 | Apply and verify staging migrations, seed data, retention, backup, and restoration | HOLD_FOR_STAGING |
| PROD-08 | Run staging functional, integration, security, privacy, tenancy, load, and failure tests | HOLD_FOR_STAGING |
| PROD-09 | Verify dashboards, logs, metrics, alerts, audit records, support, and incident runbooks | HOLD_FOR_OPERATIONS |
| PROD-10 | Conduct controlled production rollout, rollback rehearsal, and operational acceptance | HOLD_FOR_FOUNDER_PRODUCTION_APPROVAL |

## Execution rules

Each packet must record the exact repository commit/tree, environment, responsible owner, commands or checks, evidence location, rollback action, and PASS/HOLD result. Credentials and sensitive values must never be committed.
