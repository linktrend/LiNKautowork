# MVO GitHub Strategy — Four-Repo Workspace

**Status:** Canonical for MVO multi-repo development (May 2026)  
**Workspace file:** `LiNKtrend-System.code-workspace` (same folder as this doc)

This document unifies Git workflow across the four active MVO repositories opened together in Cursor. It aligns per-repo SOP with **LiNKdev** factory laws where LiNKtrend-System is the program host.

---

## Repositories in scope

| Repo | Role | GitHub |
|------|------|--------|
| **LiNKtrend-System** | LiNKaios monorepo — control plane, suites, LinkSkills, LiNKbrain, LiNKbot wiring | `linktrend/LiNKtrend-System` |
| **LiNKbot-core** | OpenClaw fork — LiNKbot runtime engine | `linktrend/LiNKbot-core` |
| **LiNKautowork** | n8n gateway — deterministic automation plane | `linktrend/LiNKautowork` |
| **LiNKsites** | Website factory — Payload CMS, templates, publish stack | `linktrend/LiNKsites` |

**External but orchestrated:** LiNKsites product code is not in LiNKtrend-System; suite orchestration and traces live in `suites/linksites/` here.

---

## Branch model (all four repos)

Two models coexist — use the one each repo documents in `.cursor/rules/`:

### LiNKtrend-System (LiNKdev factory)

| Branch | Purpose | Who merges |
|--------|---------|------------|
| `development` | Integration trunk for program issues | Integrator (agents) |
| `staging` | Pre-production validation | **Principal only** (Release OK) |
| `main` | Production | **Principal only** (Release OK) |
| `issue/<id>-<slug>` | One branch per LiNKdev issue from `development` | Executor |

**Laws:** `LiNKdev/factory/laws/LINKDEV_LAWS.md` — LAW-05 (one branch per issue), LAW-06 (no staging/main without Principal Release OK).

### LiNKbot-core, LiNKautowork, LiNKsites (SOP v2)

| Branch | Purpose | Who merges |
|--------|---------|------------|
| `dev/<machine><ide>` | Per-operator working branch (e.g. `dev/blackcursor`) | Developer/agent on that branch |
| `staging` | Integration | PR + approval |
| `main` | Production | PR + approval |

**Flow:** `dev/*` → PR to `staging` → PR to `main`. No direct pushes to `staging` or `main`.

### Cross-repo coordination

- **LiNKtrend-System** program issues may touch only System, or may specify companion PRs in sibling repos — record linked PR URLs in issue `report_path`.
- Do not assume branch names match across repos (`development` vs `dev/blackcursor`).
- MVO proof spans repos: one LinkSites lead loop may require merges in System + LiNKsites + LiNKautowork; trace artifacts must land in LiNKbrain via System orchestration.

---

## Commit and PR conventions

- **Conventional commits:** `type(scope): summary` — `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`
- **Scope:** plane or app name (`linkaios-web`, `linksites`, `n8n-gateway`, `openclaw`)
- **PR body:** Summary, test plan, behavior proof for side-effecting changes
- **Secrets:** never commit — GSM naming `LINKTREND_[SERVICE]_[ENV]_[RESOURCE]_[IDENTIFIER]`

---

## LiNKdev program integration (System repo only)

When executing a LiNKdev issue:

1. Read `LiNKdev/AGENTS.md` → active issue `read_first` only
2. Branch `issue/<issue-id>-<slug>` from `development`
3. Run `LiNKdev/factory/scripts/verify.sh` before `linkdev:merge-ready`
4. Integrator merges to `development` only — not `staging`/`main`
5. Write proof to issue `report_path`

Labels: `LiNKdev/factory/contracts/labels.md` (`linkdev:ready`, `linkdev:merge-ready`, `linkdev:done`).

---

## Fork policy (`link-*` repos)

LiNKbot-core is an OpenClaw fork. Modify for LiNKtrend integration; **never push upstream**. Upstream sync lands in `staging` with conflict resolution before `main`.

---

## Agent routing

| Task | Primary repo | Read first |
|------|--------------|------------|
| LiNKaios UI, suites, capabilities | LiNKtrend-System | `LiNKdev/product/grounding/` + issue |
| Bot runtime, channels, gateway | LiNKbot-core | `AGENTS.md` + scoped subtree |
| n8n workflows, automation gateway | LiNKautowork | `AGENTS.md` + compose docs |
| Payload, templates, publish | LiNKsites | `docs/README.md` + `sites_specs/` |

---

## Workspace settings

See `LiNKtrend-System.code-workspace` for multi-root folder paths. Optional Cursor/VS Code settings may be added there; this markdown is the human-readable authority for cross-repo Git policy.
