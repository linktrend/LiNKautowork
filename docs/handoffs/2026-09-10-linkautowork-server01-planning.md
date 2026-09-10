# LiNKautowork Server01 planning handoff

Date: 2026-09-10, Asia/Taipei
Issue: #127
Branch: `issue/127-plan-linkautowork-end-to-end-deployment-on-links`
Status: **PLAN READY / EXECUTABLE-NOW HOLD / AWAITING APPROVE**

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
`40eb451c010c2916ceaa53537cf7ee0c34e36ad30035df0ad2c2e66a43b5eb51`.

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
- Planning/interface maturity is READY, but executable-now readiness is HOLD.
  AW-01 is the first content packet and its product inputs are ready. The installed
  `cursor-cloud-dispatch-v2` route is source-verifiable, while `CURSOR_API_KEY`, a
  matching GSM reference, `cursor-sdk`, and authenticated Cursor Cloud readback are
  unavailable. `cursor-agent status` reports `Not logged in`; CLI login is not API
  authority. Founder must authorise route provisioning/verification or explicitly
  select the Luna High fallback in addition to `APPROVE`.
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
