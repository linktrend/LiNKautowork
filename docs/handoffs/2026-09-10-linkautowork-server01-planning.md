# LiNKautowork Server01 planning handoff

Date: 2026-09-10, Asia/Taipei
Issue: #127
Branch: `issue/127-plan-linkautowork-end-to-end-deployment-on-links`
Status: **PLAN READY / AWAITING APPROVE**

## Delivered

- Stable package entrypoint:
  `docs/end-to-end-delivery/README.md`
- Complete Server01 deployment PRD/definition of done:
  `docs/end-to-end-delivery/LINKAUTOWORK-SERVER01-DELIVERY-PLAN.md`
- Eight atomic dependency-ordered work packets:
  `docs/end-to-end-delivery/WORK-PACKETS.md`
- IDE Development 2.5.2 schema-valid PLAN manifest:
  `docs/end-to-end-delivery/EXECUTION-MANIFEST.json`
- Evidence-based readiness and uncertainties:
  `docs/end-to-end-delivery/READINESS-REPORT.md`

Manifest SHA-256:
`f63ac4165c5a23201f6b5b4b344ce3c8b2b74b2231832f935249f3f9e6a3f92a`.

## Settled scope

Initial release deploys the gateway, stock pinned n8n, persistent NATS
JetStream, Platform/Supabase persistence, private Product API/operator surfaces,
monitoring/recovery, and one usable `governed-repository-executor@1.0.0` binding.
IDE Development owns the first consumer task/authority/acceptance;
LiNKautowork owns the automation/runtime/receipt; Platform owns identity,
credentials, shared migrations and live environment operation.

Commercial/public/client workflows and unspecified future Program automations are
explicit later expansion and do not block the initial internal release.

## Exact dependencies and HOLDs

- Existing Phase PR #125 and issue #126 must complete through their current owner;
  this package does not duplicate their source-readiness work.
- Live work waits only for the specific Platform consumer registrations/PACI
  endpoints and scopes, least-privilege database roles, and exact migration
  receipts named in the plan. General Platform completion is not claimed or used
  as a blanket blocker.
- No Server01 LiNKautowork, n8n or NATS runtime was observed. No product,
  credential, provider, database, workflow or server mutation occurred.
- Independent narrow review of the exact planning commit remains HOLD because
  this planning task forbids downstream dispatch. It must bind to the pushed
  commit/tree before Issue checkpoint acceptance.

## Validation

- execution-manifest JSON Schema: PASS
- execution-manifest semantic lifecycle: PASS
- JSON parse: PASS
- scoped relative links: PASS
- `git diff --check`: PASS
- `npm run release:check`: PASS
- automation/catalogue commands: not completed because `ajv` is not installed in
  the clean worktree and dependency installation is prohibited before approval

The exact pushed planning commit and tree are reported in the founder-facing final
because this document cannot contain its own final Git identity.
