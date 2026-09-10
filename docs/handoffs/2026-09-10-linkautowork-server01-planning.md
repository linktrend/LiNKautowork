# LiNKautowork Server01 planning handoff

Date: 2026-09-10, Asia/Taipei
Issue: #127
Branch: `issue/127-plan-linkautowork-end-to-end-deployment-on-links`
Status: **CANDIDATE PLAN READY / ADVISOR ACCEPTANCE PENDING**

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
- Sanitised verified worker route and GitHub-hosted packet inputs:
  `docs/end-to-end-delivery/CURSOR-CLOUD-EXECUTION-ROUTE.md`

Manifest SHA-256:
`28bf51adee6866f139a2dddbf1a7c09201ca4368388931f6213ee0b4b2f5a960`.

## Settled scope

Initial release deploys the gateway, stock pinned n8n, persistent NATS
JetStream, Platform/Supabase persistence, private Product API/operator surfaces,
monitoring/recovery, and the usable package/instance/binding/invocation/receipt
path. LiNKautowork owns that automation-platform runtime; Platform owns identity,
credentials, shared migrations and live environment operation; each later Program
owns its own automation definition, permission-to-act and result acceptance.

The earlier Cursor/IDE `governed-repository-executor` is a proposal, not a
founder-approved requirement. It is excluded from the required release and cannot
be built without a separate founder/Program-owner scope decision.

Commercial/public/client workflows and unspecified future Program automations are
explicit later expansion and do not block the initial internal release.

## Exact dependencies and HOLDs

- Existing Phase PR #125 and issue #126 remain with their current owner; this
  package does not duplicate their source-readiness work. They require
  reconciliation before affected implementation but do not block downstream
  planning against settled interfaces.
- Live work waits only for the specific Platform consumer registrations/PACI
  endpoints and scopes, least-privilege database roles, and exact migration
  receipts named in the plan. General Platform completion is not claimed or used
  as a blanket blocker.
- No Server01 LiNKautowork, n8n or NATS runtime was observed. No product,
  credential, provider, database, workflow or server mutation occurred.
- Planning/interface maturity is READY and executable-after-approval readiness is
  READY with one scheduled coordinator control transition. Coordinator task
  `01a089cb-ef0d-75a2-b87f-4f3dd8163b24` owns this repository and AW-01 is the
  first content packet. Direct
  read-only API calls through the established Keychain-backed REST dispatcher
  proved account `cursor-001@linktrend.one`, Grok 4.6 Medium/Fast-off support and
  LiNKautowork repository visibility. No new key, login, SDK install or founder
  route choice is needed; no paid worker was launched.
- `SUSPENDED` is present and current `RESUME-SCOPE.json` does not contain this
  coordinator. After `APPROVE`, it first requires terminal handoff from the running
  prior `autowork-phase-admission-015`, refreshes the protected baseline, then
  atomically adds only its own LiNKautowork grant while preserving suspension and
  every existing owner. The route document defines validation and rollback; no
  second founder decision is needed.
- Later live prerequisites are the exact Platform registrations/PACI scopes,
  least-privilege database roles, migration receipts, GSM runtime references and
  private Server01 routes. They gate AW-08 live acceptance, not downstream planning.
- The installed protocol requires exact-commit independent narrow review for a
  later accepted implementation Issue checkpoint. This planning task forbids
  downstream dispatch; planning readiness itself is not gated on inventing that
  review.

## Validation

- execution-manifest JSON Schema: PASS
- execution-manifest semantic lifecycle: PASS
- JSON parse: PASS
- scoped relative links: PASS
- `git diff --check`: PASS
- `npm run release:check`: PASS
- automation/catalogue commands: not completed because `ajv` is not installed in
  the clean worktree and dependency installation is prohibited before approval;
  the catalogue is unchanged, so this is not a new product failure

The exact pushed planning commit and tree are reported in the founder-facing final
because this document cannot contain its own final Git identity.
