# LiNKautowork production PRD

Status: pre-configuration engineering baseline complete as of 2026-09-04.

## Product outcome

LiNKautowork must operate as an independently buildable and deployable repository. It consumes exact version-pinned shared contracts and communicates with other LiNK repositories only through published interfaces.

For Program repositories, the reproducible composition is:

> pinned LiNKharness release + pinned LiNKprofiles base + repository-specific profile and implementation = Program

## Completed scope

The protected `development` branch contains the completed pre-configuration engineering baseline. Promotion of this baseline does not claim that credentials, live providers, staging deployment, production deployment, or operational acceptance already exist.

## Remaining production outcome

Production completion requires:

- exact Cursor SDK/API and Codex SDK/API executor configuration where applicable;
- approved OSS dependency versions, licences, security disposition, and supply-chain evidence;
- external-service adapters configured against approved sandbox and production accounts;
- exact cross-Program contract pins and consumer compatibility receipts;
- LiNKautowork automation schedules, triggers, retries, budgets, escalation, and rollback configuration;
- environment-specific secrets supplied through an approved secrets manager;
- staging migrations, smoke tests, integration tests, failure exercises, and rollback rehearsal;
- monitoring, logs, metrics, alerts, backup/restore, incident response, and operator runbooks;
- controlled production rollout and recorded operational acceptance.

Missing live information must remain disabled with an explicit HOLD. It must never be replaced by invented credentials, endpoints, approvals, or provider capabilities.

## Acceptance boundary

Source-ready means the repository can be configured and tested without further product redesign. Production-accepted means the configured system has passed staging, rollout, recovery, security, and operator acceptance with exact evidence.
