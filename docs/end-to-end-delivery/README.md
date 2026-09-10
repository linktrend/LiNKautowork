# LiNKautowork end-to-end delivery package

Status: **CANDIDATE PLAN READY / ADVISOR ACCEPTANCE PENDING / IMPLEMENTATION NOT AUTHORISED**
Prepared: 2026-09-10, Asia/Taipei
Assigned host: **LiNKserver 01** (`linkserver-01`)
Planning issue: [#127](https://github.com/linktrend/LiNKautowork/issues/127)
Planning manifest SHA-256:
`8a19a79b1461abad4abef25970a7ff3ad7c4363c042fc9c26b276d4551da34c5`

This directory is the stable entry point for making LiNKautowork usable on its
assigned existing server. It does not replace the approved product authority or
the completed pre-VPS engineering record.

## Read order

1. [Server01 delivery plan and deployment PRD](./LINKAUTOWORK-SERVER01-DELIVERY-PLAN.md)
2. [Atomic work packets](./WORK-PACKETS.md)
3. [Execution manifest](./EXECUTION-MANIFEST.json)
4. [Verified Cursor Cloud execution route](./CURSOR-CLOUD-EXECUTION-ROUTE.md)
5. [Planning readiness report](./READINESS-REPORT.md)

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

The first content packet is AW-01 and its product/interface inputs are ready. The
established Keychain-backed REST dispatcher has verified read-only access to the
exact Cursor account, Grok 4.6 Medium/Fast-off selection and
`linktrend/LiNKautowork`. Its sanitised packet, retrieval and checkpoint rules are
committed in the execution-route document above. No new credential, login, SDK
installation or founder route choice is needed. Once the Deployment Advisor
accepts this exact package, `APPROVE` is the sole remaining founder gate to creating
the first paid worker. Advisor acceptance releases planning only and never implies
implementation authority.

The queue remains globally suspended. After `APPROVE`, coordinator task
`01a089cb-ef0d-75a2-b87f-4f3dd8163b24` first reconciles the existing Server01
owner and then atomically adds only its own `linktrend/LiNKautowork` grant to the
existing resume scope. It preserves all other owner grants and `SUSPENDED`. This
scheduled control transition is fully specified in the route document and needs no
second founder decision.

Maximum safe planned source concurrency is two workers after AW-01: one runtime
lane and one disjoint deployment-source lane. Current executable capacity remains
one because the shared dispatcher guard is repository-wide. Deployment Advisor
owns the single lane-aware dispatcher extension after `APPROVE`; LiNKautowork does
not modify it. Until verified, the two ready lanes run sequentially; afterward the
coordinator fills both as capacity becomes available.

An active source-readiness Phase PR, [#125](https://github.com/linktrend/LiNKautowork/pull/125),
and its repair issue [#126](https://github.com/linktrend/LiNKautowork/issues/126)
remain owned by their existing lane. This package does not copy or replace their
changes. They require source reconciliation before affected implementation, but do
not block downstream planning against the settled interfaces in this package.
