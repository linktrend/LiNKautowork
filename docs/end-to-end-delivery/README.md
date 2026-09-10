# LiNKautowork end-to-end delivery package

Status: **PLAN READY / IMPLEMENTATION NOT AUTHORISED**
Prepared: 2026-09-10, Asia/Taipei
Assigned host: **LiNKserver 01** (`linkserver-01`)
Planning issue: [#127](https://github.com/linktrend/LiNKautowork/issues/127)
Planning manifest SHA-256:
`f63ac4165c5a23201f6b5b4b344ce3c8b2b74b2231832f935249f3f9e6a3f92a`

This directory is the stable entry point for making LiNKautowork usable on its
assigned existing server. It does not replace the approved product authority or
the completed pre-VPS engineering record.

## Read order

1. [Server01 delivery plan and deployment PRD](./LINKAUTOWORK-SERVER01-DELIVERY-PLAN.md)
2. [Atomic work packets](./WORK-PACKETS.md)
3. [Execution manifest](./EXECUTION-MANIFEST.json)
4. [Planning readiness report](./READINESS-REPORT.md)

## Existing authorities reused, not copied

- [`docs/production-roadmap/LINKAUTOWORK-PRODUCTION-ROADMAP.md`](../production-roadmap/LINKAUTOWORK-PRODUCTION-ROADMAP.md) — approved product intent, ownership, architecture, and pre-VPS definition.
- [`docs/PRD.md`](../PRD.md) — current source/configuration/production acceptance boundary.
- [`docs/WORK-PACKETS.md`](../WORK-PACKETS.md) — existing PROD-01 through PROD-10 configuration and rollout outcomes.
- [`docs/production-roadmap/EXECUTION-STATE.yaml`](../production-roadmap/EXECUTION-STATE.yaml) — accepted pre-VPS wave record.
- [`docs/runbooks/PRODUCTION_RELEASE_GATES.md`](../runbooks/PRODUCTION_RELEASE_GATES.md) — release gates.
- [`docs/runbooks/OPERATIONS.md`](../runbooks/OPERATIONS.md) — existing operating commands; it must be corrected or extended only by an implementation packet when live topology requires it.
- [`docs/production-roadmap/evidence/WP-12-VPS-DEPLOYMENT-INPUT-REGISTER.md`](../production-roadmap/evidence/WP-12-VPS-DEPLOYMENT-INPUT-REGISTER.md) — historical placeholder register, superseded for Server01 values only by this package.

## Authority boundary

Planning documentation, its issue branch, validation, commit, and push are
authorised. Product changes, credentials, migrations, provider calls, workflow
activation, deployment, protected integration, and live mutation remain blocked
until the founder records `APPROVE` in this task. The approval must bind to the
manifest digest above and the named Server01 deployment action.

An active source-readiness Phase PR, [#125](https://github.com/linktrend/LiNKautowork/pull/125),
and its repair issue [#126](https://github.com/linktrend/LiNKautowork/issues/126)
must be resolved through their existing owner. This package does not copy or
replace their changes.
