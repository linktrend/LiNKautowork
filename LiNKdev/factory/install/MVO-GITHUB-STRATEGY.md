# MVO GitHub Strategy — Four-Repo Workspace

**Status:** Canonical for MVO multi-repo development (May 2026)  
**Workspace file:** `LiNKtrend-System.code-workspace` (same folder as this doc)

This document unifies Git workflow across the four active MVO repositories opened together in Cursor. **All four repos follow the same branch model** as **LiNKdev SPEC §8** (`LiNKdev/factory/SPEC.md`).

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

**All four MVO repos use the identical branch model** — same as **LiNKdev SPEC §8** and `LiNKdev/factory/rules/01-git-branching.mdc`:

| Branch | Purpose | Who merges |
|--------|---------|------------|
| **`development`** | Integration trunk — all agent and ad-hoc work lands here via PR | **Integrator** (after Reviewer PASS) |
| **`staging`** | Pre-production validation | **Principal only** (Release OK) |
| **`main`** | Production | **Principal only** (Release OK) |
| `issue/<id>-<slug>` | One branch per LiNKdev issue from `development` | Executor → PR → Integrator merges to `development` |
| `dev/<machine><ide>` | Optional ad-hoc IDE work (e.g. `dev/blackcursor`) | PR → **`development`** |

**Promotion flow:**

```
issue/* or dev/*  →  PR to development  →  Integrator merges when merge-ready
development       →  PR to staging      →  Principal only
staging           →  PR to main         →  Principal only
```

- **Integrator** merges only into **`development`** — never `staging` or `main`.
- **Principal** approves promotion **`development` → `staging` → `main`** (LAW-06).
- No direct pushes to `staging` or `main`.
- Allowed PR sources into `development` are enforced in `.github/workflows/branch-source-policy.yml`.

**Laws:** `LiNKdev/factory/laws/LINKDEV_LAWS.md` — LAW-05 (one branch per issue), LAW-06 (no staging/main without Principal Release OK).

### Cross-repo coordination

- Program issues may touch only one repo, or may specify companion PRs in sibling repos — record linked PR URLs in issue `report_path`.
- Branch names and promotion rules are **identical** across all four repos.
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

LiNKbot-core is an OpenClaw fork. Modify for LiNKtrend integration; **never push upstream**. Upstream sync lands in **`development`** with conflict resolution before Principal promotion to `staging`/`main`.

Nested **`link-n8n/`** in LiNKautowork follows the same rule: upstream n8n sync targets **`development`** only.

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
