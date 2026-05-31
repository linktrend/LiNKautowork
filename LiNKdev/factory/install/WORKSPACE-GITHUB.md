# Workspace GitHub strategy

Unified git and GitHub policy for LiNKtrend **MVO workspace repos**, aligned with `LiNKdev/factory/SPEC.md` §8, **LAW-05**, **LAW-06**, and `LiNKdev/factory/rules/01-git-branching.mdc`.

## Core four repos (MVO workspace)

| Repo | Role | Upstream |
|------|------|----------|
| **LiNKtrend-System** | LiNKaios monorepo — control plane, suites, brain, skills, autowork orchestration | none |
| **LiNKbot-core** | LiNKbot runtime (OpenClaw fork) | `openclaw/openclaw` |
| **LiNKautowork** | Deterministic workflow execution (n8n) | none |
| **LiNKsites** | LinkSites product — Payload CMS, templates, publish | none |

Each repo uses the same **three stable branches**: `development`, `staging`, `main`.

## Branch flow (all product repos)

```
issue/<id>-<slug>  ─┐
dev/<machine><ide> ─┼→ PR → development → PR → staging → PR → main
```

| Step | Actor | Rule |
|------|-------|------|
| Issue / ad-hoc work | Executor on `issue/*` or `dev/*` from `development` | **LAW-05**: one branch per issue; no worktrees |
| Merge to `development` | Integrator after Reviewer PASS | Default integration target |
| Merge to `staging` | **Principal only** | After program Release OK |
| Merge to `main` | **Principal only** | Production deploy source |

GitHub is the source of truth. Coordination with LiNKdev uses labels, `STATE.md`, issue branches, and PRs — not direct pushes to protected branches.

## Required GitHub Actions (copy per repo)

Each product repo should install workflows from this template pack:

| Workflow | Source template | Purpose |
|----------|-----------------|--------|
| **Branch source policy** | `LiNKdev/factory/install/github/branch-source-policy.yml` | Enforces promotion flow; allows `issue/*` and `dev/*` into `development` |
| **CI** | Host repo’s existing `ci.yml` | Build, test, lint on PR |
| **Upstream sync** (forks only) | Host repo’s `upstream-sync.yml` | Sync upstream into fork **`development`** only |

### Install branch source policy

```bash
mkdir -p .github/workflows
cp LiNKdev/factory/install/github/branch-source-policy.yml .github/workflows/
git add .github/workflows/branch-source-policy.yml
```

Commit on `development` and promote with the rest of the repo policy rollout. The workflow must exist on `development` before branch protection required-checks reference it.

### Allowed PR sources (enforced by workflow)

| Target branch | Allowed source |
|---------------|----------------|
| `development` | `issue/*`, `dev/*`, `feature/*`, `fix/*`, `chore/*`, `codex/*`, `cursor/*`, `antigravity/*`, `dependabot/*` |
| `staging` | `development` only |
| `main` | `staging` only |

**LiNKdev mandatory:** executor issues use `issue/<issue-id>-<slug>` — ensure `issue/*` is allowed (included in template).

## Fork repos (`link-*`)

- Never open PRs to upstream.
- Automation syncs upstream into the **`linktrend/*` fork `development`** branch.
- Resolve conflicts in `development` before Principal promotion.
- Example: **LiNKbot-core** syncs from `openclaw/openclaw` into `linktrend/LiNKbot-core` `development`.

## LiNKdev template repo

**LiNKdev** (`linktrend/LiNKdev`) is the portable factory source — not an MVO runtime repo. It uses the same branch model. Tagged releases on `main` drive `sync-installations.sh` to registered product repos (factory + shim only; **`LiNKdev/product/` never overwritten** on hosts).

## Registry and auto-sync

Product repos register in LiNKdev `registry/installations.json` with GitHub secret **`LINKDEV_SYNC_TOKEN`** for factory upgrades. See LiNKdev root `docs/SYNC-INSTALLATIONS.md`.

## Wire verification

During LiNKdev wire (`LiNKdev/factory/install/CHECKLIST.md` §0):

- [ ] `development`, `staging`, `main` exist
- [ ] `branch-source-policy.yml` on `development`
- [ ] Branch protections on `staging` and `main` (Principal-only promotion)
- [ ] Fork upstream sync targets `development` (if applicable)
