# WP-10 — Internal Operator Console

## Objective

Build the private dashboard LiNKtrend human operators use to understand, provision, monitor, approve, pause, troubleshoot, maintain, and audit automations without entering n8n for ordinary operations.

## Dependencies

WP-09 API and all Wave 2 operational states. It can proceed in parallel with WP-11 after API contracts are frozen.

## Owned paths

- `apps/operator-console/**`
- Operator-specific UI tests and fixtures
- Shared UI components only where clearly generic and non-domain-specific

## Required screens

1. **Operations overview:** active/degraded/paused instances, failures, missing runs, open incidents, pending provisioning, expiring certification, and alert-channel health.
2. **Automation catalogue:** internal definitions/releases, validation/eval/certification state, source/provenance/license, linked products, and eligible actions. It is an operator catalogue, not a client search-and-run surface.
3. **Instance directory/detail:** organisation, product/binding, deployed release, configuration completion, n8n reference (operator-only), health, executions, incidents, maintenance, and audit trail.
4. **Provisioning queue/detail:** state-machine timeline, safe configuration checklist, retry/compensate actions, and exact failure reason.
5. **Execution explorer:** filtered summaries and redacted evidence, lifecycle events, retry relation, duration, status, and incident linkage.
6. **Incident centre:** severity, acknowledgement, assignment/owner field, affected scope, evidence, actions, mitigation/resolution, and recovery.
7. **Release and deployment:** candidate certification, approval separation, canary evidence, promotion eligibility, rollback target, and kill/pause controls.
8. **Librarian candidates:** evidence, proposed diff/changed artifacts, risk, eval results, approve/reject/supersede—not direct production rewrite.
9. **Audit and system health:** privileged actions, component/job health, backup/restore rehearsal status, version drift, and configuration readiness.

## Interaction and safety requirements

- Plain-English labels precede technical identifiers; technical detail is progressively disclosed.
- Destructive/high-impact actions show exact scope, reason field, confirmation, authorisation result, and resulting audit ID.
- Never render secret values, raw tokens, unrestricted payloads, or client data from another organisation.
- Loading, empty, partial, stale, permission-denied, API-unavailable, and failed-action states are designed and tested.
- Status colours are accompanied by text/icons; keyboard navigation and accessible names are required.
- Use the repository's Tailwind/shadcn standards and typed WP-09 client. Do not add a competing design system without approval.

## Test matrix

- Role/route guards and direct URL attempts.
- Dashboard state from representative fixtures.
- Provisioning failure and safe retry.
- Incident acknowledgement/resolution.
- Candidate review separation.
- Canary blocked/pass/rollback flows.
- Kill/pause confirmation and scope display.
- Secret/redaction snapshots, accessibility, responsive operator desktop/tablet, API failure and stale data.
- Browser E2E against local API fixtures.

## Acceptance criteria

- An authorised operator can trace a failing client automation from alert to execution evidence, incident, safe action, and recovery without using n8n.
- The console cannot promote uncertified code or let a proposer self-certify.
- All privileged actions have confirmation, reason, correlation/audit evidence, and accurate result state.
- Core browser journeys pass with no console errors and meet automated accessibility checks.

## Evidence required at handoff

Screen inventory, screenshots or test traces, role/action matrix, accessibility results, E2E results, changed files, limitations, and rollback instructions.

## Stop conditions

Do not invent operator approval authority, incident retention, or production kill-switch permissions where policy is undecided. Represent unavailable actions as clearly blocked and record the required decision.
