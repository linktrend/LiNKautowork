# LiNKautowork 1.0 source-release packet (issues 165 + 166)

Status: **SOURCE-ONLY**. No implementer PR, protected merge, Server01, Docker,
GSM value resolve, SQL apply, or production message is authorised here.

| Packet | Role |
|---|---|
| Issue 165 | Agent 1: sealed engineering candidate + first receipts |
| Issue 166 | This file set: AI-agent guide, README consolidation, archive index, tagged-main handoff, branch cleanup manifest |

## Identities

Engineering candidate (hosted CI green):

- commit `20f3d4cc03445ca443e31c41f22d34347c866acf`
- tree `95bec98a0d65ca30889e595a7bcaa85ddfe52b47`
- run https://github.com/linktrend/LiNKautowork/actions/runs/34955615212

Issue 166 admitted start (Agent 1 checkpoint, including 165 docs):

- branch `issue/166-consolidate-linkautowork-1-0-repository-and-publ`
- commit `a3c22a868a89c7627bd3018ece5edb21e7c59351`
- tree `bf85913dc6fb0b41c3c235cb6e8050db597802a3`

**Tagged main candidate:** not published at admission. Stale tag `v1.0.0` peels
to `7e76a5e77306d42cdcfd4fd59f22473235c7e7fc` and **must not** be installed.
See `DEPLOYMENT-HANDOFF.md` and `TAGGED-MAIN-CANDIDATE.json`.

## Files

| File | Purpose |
|---|---|
| `SOURCE-IDENTITY.json` | Cached vs admitted vs engineering identities |
| `TOOLCHAIN.json` | CI/image pins, writer runtime, lock diagnosis |
| `VALIDATION-RECORD.json` | Issue 166 acceptance commands |
| `IMAGE-CONFIG-MIGRATION-REFERENCES.json` | Image tags, Dockerfiles, SQL package (Agent 1; files unchanged) |
| `HOLD-REGISTER.json` | Live/Platform/Docker/protected HOLDs |
| `ROLLBACK.md` | Source + later application rollback (not executed) |
| `DEPLOYMENT-HANDOFF.md` | Non-secret AW-08 inputs for a **separate** Server01 agent |
| `TAGGED-MAIN-CANDIDATE.json` | Exact tag-on-main bind contract |
| `BRANCH-CLEANUP-MANIFEST.json` | Every remote head classified; no deletes applied |

## Hard limits

- Allowed writes this issue: root/`docs` READMEs, AI-agent guide, `docs/archive/`,
  this directory.
- Implementer does not open the Phase PR.
- Writer VM has no Docker. Do not install Docker to force `npm run ci`.
