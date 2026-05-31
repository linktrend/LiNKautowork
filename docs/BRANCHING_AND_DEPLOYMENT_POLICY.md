# Branching and Deployment Policy

Owner: LiNKtrend Platform  
Last updated: 2026-05-31

## Purpose

This repository follows the **LiNKdev branch model** so integration, release, and production deploys are deterministic and auditable. Canonical rules: `LiNKdev/factory/SPEC.md` **§8** and `LiNKdev/factory/rules/01-git-branching.mdc`.

MVO workspace policy lives in LiNKtrend-System `docs/workspace/` (execution target repo only).

## Branch model

| Branch | Purpose | Who merges |
|--------|---------|------------|
| **`development`** | Integration — all agent and ad-hoc work lands here via PR | **Integrator** (after Reviewer PASS) |
| **`staging`** | Pre-production validation before release | **Principal only** (after Release OK) |
| **`main`** | Production — deploy only from tagged commits here | **Principal only** (after Release OK) |

Short-lived work branches branch **from `development`** and merge **to `development`** via PR.

## Work branches

| Prefix | Use | Merge target |
|--------|-----|--------------|
| `issue/<id>-<slug>` | LiNKdev issue execution (one branch per issue, LAW-05) | **`development`** (Integrator only) |
| `dev/<machine><ide>` | Optional ad-hoc IDE work per host SOP | **`development`** via PR |

Examples:

- `issue/LA-012-gateway-lease-hook`
- `dev/blackcursor`

**LAW-05:** one branch per issue; one repo checkout per executor run. Git worktrees are forbidden in LiNKdev.

## Promotion flow

```
issue/* or dev/*  →  PR to development  →  Integrator merges when merge-ready
development       →  PR to staging      →  Principal
staging           →  PR to main         →  Principal
```

1. Branch from latest **`development`**.
2. Implement; open PR targeting **`development`**.
3. Pass CI, Reviewer PASS, Integrator merge (**LAW-06** blocks direct merge to `staging`/`main`).
4. After program Release OK, Principal promotes **`development` → `staging` → `main`**.

Deploy only from tagged commits on **`main`** (pin by tag/SHA, never `latest`).

## Required gates

- CI must pass on PRs to **`development`**, **`staging`**, and **`main`**.
- Security checks: SAST, dependency vulnerability scan, secret scan.
- **`branch-source-policy.yml`** enforces allowed PR sources (`.github/workflows/`).
- **`staging`** and **`main`**: PR required; no direct pushes; force push disabled.

## Deployment rules

- Production deployment source is **`main`** only.
- Optional dev/staging VPS deployments may come from **`staging`**.
- Every production release must be tagged (example: `v2026.05.31-1`).

## Branch protection setup

Configure in GitHub repository settings:

- Protect **`main`**: no force-push, no direct push, required checks, Principal approval.
- Protect **`staging`**: required checks and Principal approval.
- Protect **`development`**: PR required; enforce allowed source branches via workflow.

## Related docs

- LiNKdev SPEC §8: `LiNKdev/factory/SPEC.md`
- Factory git rule: `LiNKdev/factory/rules/01-git-branching.mdc`
- Host git rule: `.cursor/rules/01-git-branching.mdc`
- Nested n8n fork upstream: `docs/UPSTREAM.md`
