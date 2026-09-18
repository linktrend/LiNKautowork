# LiNKautowork 1.0 source-release candidate (AW-07 / issue 165)

Status: **SOURCE-ONLY DEPLOYMENT-READY CANDIDATE**. This packet does **not**
open or merge a PR, promote protected refs, deploy, resolve GSM, apply
migrations, start Docker, or claim live Server01/Platform acceptance.

Prepared: 2026-09-18T03:51:44Z from admitted identity
`linktrend/LiNKautowork`
`issue/165-prepare-linkautowork-1-0-release-candidate-and-d`
commit `20f3d4cc03445ca443e31c41f22d34347c866acf`
tree `95bec98a0d65ca30889e595a7bcaa85ddfe52b47`.

Production authority reused (read-only):

- `docs/production-roadmap/LINKAUTOWORK-PRODUCTION-ROADMAP.md`
- `docs/production-roadmap/EXECUTION-STATE.yaml` (`pre_vps_complete`)
- `docs/runbooks/PRODUCTION_RELEASE_GATES.md`
- `docs/end-to-end-delivery/LINKAUTOWORK-SERVER01-DELIVERY-PLAN.md`
- `docs/contracts/server01/MIGRATION-PACKAGE.json`
- `deploy/prod/release-identity.json`

## Packager / controller inputs

| File | Purpose |
|---|---|
| `SOURCE-IDENTITY.json` | Starting vs admitted vs hosted identities |
| `TOOLCHAIN.json` | CI/image pins vs writer runtime; lock diagnosis |
| `VALIDATION-RECORD.json` | Commands, exits, hosted CI substitution |
| `IMAGE-CONFIG-MIGRATION-REFERENCES.json` | Image tags, Dockerfiles, compose, migration package |
| `HOLD-REGISTER.json` | Remaining live/Platform/Docker HOLDs |
| `ROLLBACK.md` | Source rollback contract (not executed) |
| `DEPLOYMENT-HANDOFF.md` | AW-08 inputs this candidate may hand off |

## Hard limits

- Allowed write path: `docs/end-to-end-delivery/evidence/source-release/` only.
- Implementer does not open the Phase PR. Phase Packager/Coordinator and
  delivery controller remain the integration actors.
- Writer VM has no Docker. Full `npm run ci` locally failed at
  `packages/automation-contracts` disposable Postgres (`spawnSync docker ENOENT`).
  Hosted `validate-and-test` on the **same commit** succeeded
  (run `34955615212`).
