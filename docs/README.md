# LiNKautowork Documentation Index

Owner: LiNKtrend Platform  
Last updated: 2026-10-02 (1.0 status and archive consolidation)

## 1.0 agent entry

- [AI agent guide](./LINKAUTOWORK-AI-AGENT-GUIDE.md) — identity, toolchain, git
  roles, HOLDs, and tagged-main deploy contract.
- [Current release status](./LINKAUTOWORK-RELEASE-STATUS.md) — protected refs,
  current receipt gate, tag status, and deployment HOLDs.
- [1.0 source-release packet](./end-to-end-delivery/evidence/source-release/README.md)
- [Deployment handoff (non-secret, AW-08)](./end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md)
- [1.0 superseded index](./archive/LINKAUTOWORK-1.0-SUPERSEDED-INDEX.md)

## Product description (still current)

- [Intent](./LINKAUTOWORK-INTENT.md)
- [Technical PRD](./LINKAUTOWORK-TECHNICAL-PRD.md)
- [Operations Manual](./LINKAUTOWORK-OPERATIONS-MANUAL.md)
- [Archived Open Issues / build log](./archive/development-history/OPEN-ISSUES.md) —
  historical engineering trace; not the 1.0 agent entrypoint.

## Remaining production configuration (not live-accepted)

- [Production PRD](./PRD.md)
- [Production work packets PROD-01–10](./WORK-PACKETS.md)
- [Production-readiness index](./PRODUCTION-READINESS.md)

## Operational docs (source topology; live start HOLD)

- [Server01 deployment handoff](./end-to-end-delivery/evidence/source-release/DEPLOYMENT-HANDOFF.md) —
  historical source packet; current release status and runbooks determine
  whether deployment is allowed.
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
- [Archived development history](./archive/development-history/)

## Rule

If 1.0 agent procedure changes, update the AI agent guide and the
source-release packet in the same checkpoint. Do not open an implementer PR.
Historical source receipts remain byte-for-byte preserved. Dated planning,
build logs, roadmap evidence, and completed handoffs have been moved under the
archive. Small compatibility links at former paths point into the archive so
old receipts and references still resolve; there is only one stored copy.
The release check validates the archived locations.
