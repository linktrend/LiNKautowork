# LiNKautowork Documentation Index

Owner: LiNKtrend Platform  
Last updated: 2026-09-18 (1.0 source consolidation)

## 1.0 agent entry

- [AI agent guide](./LINKAUTOWORK-AI-AGENT-GUIDE.md) — identity, toolchain, git
  roles, HOLDs, and tagged-main deploy contract.
- [1.0 source-release packet](./end-to-end-delivery/evidence/source-release/README.md)
- [Deployment handoff (non-secret, AW-08)](./end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md)
- [1.0 superseded index](./archive/LINKAUTOWORK-1.0-SUPERSEDED-INDEX.md)

## Product description (still current)

- [Intent](./LINKAUTOWORK-INTENT.md)
- [Technical PRD](./LINKAUTOWORK-TECHNICAL-PRD.md)
- [Operations Manual](./LINKAUTOWORK-OPERATIONS-MANUAL.md)
- [Open Issues / build log](./OPEN-ISSUES.md) — historical engineering trace;
  not the 1.0 agent entrypoint.

## Remaining production configuration (not live-accepted)

- [Production PRD](./PRD.md)
- [Production work packets PROD-01–10](./WORK-PACKETS.md)
- [Production-readiness index](./PRODUCTION-READINESS.md)

## Operational docs (source topology; live start HOLD)

- [Server01 end-to-end delivery package](./end-to-end-delivery/README.md) —
  planning record; implementation authority is the source-release packet plus
  later AW-08, not the 2026-09-10 “not authorised” banner alone.
- [Operations runbook](./runbooks/OPERATIONS.md)
- [Server01 JetStream / restore rehearsal](./runbooks/SERVER01-OPERATIONS.md)
- [Production release gates](./runbooks/PRODUCTION_RELEASE_GATES.md)
- [Tailscale hardening](./runbooks/TAILSCALE_HARDENING.md)
- [Import automation templates](./runbooks/IMPORT_AUTOMATION_TEMPLATES.md)
- [Deploy readiness](./DEPLOY_READINESS.md)
- [SLO](./SLO.md)

## Contracts

- [Server01 migration package](./contracts/server01/README.md)
- Provider v1 contracts under `docs/contracts/provider-*.md`

## Archive

- [Archive index](./archive/README.md)
- [1.0 superseded development-only documents](./archive/LINKAUTOWORK-1.0-SUPERSEDED-INDEX.md)
- [Legacy document register](./archive/LEGACY-DOCUMENT-REGISTER.md)

## Rule

If 1.0 agent procedure changes, update the AI agent guide and the
source-release packet in the same checkpoint. Do not open an implementer PR.
Physical moves of `release:check`-required files are out of consolidation
scope; classify them in the superseded index instead of deleting them.
