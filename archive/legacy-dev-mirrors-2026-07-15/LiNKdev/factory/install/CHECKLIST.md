# Wire LiNKdev — Install Checklist

Agents execute this checklist **autonomously**. The Principal only sends one-line launches in [PRINCIPAL-LAUNCH.md](PRINCIPAL-LAUNCH.md).

| Sections | Agent | Prompt file |
|----------|--------|-------------|
| 0–3, 6–7 | Cursor | [EXECUTE-WIRE-LINKDEV.md](EXECUTE-WIRE-LINKDEV.md) |
| 4–5 | Cursor | [EXECUTE-LINKDEV-DISPATCH-INSTALL.md](EXECUTE-LINKDEV-DISPATCH-INSTALL.md) |
| 9 (+ wire sign-off) | Cursor | [EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md](EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md) |
| 8 **Go** | Principal only | `linkdev-go` / **Go** — not part of wire |

Progress is recorded in `LiNKdev/product/reports/wire/WIRE-SESSION.md`.

Canonical dispatch doc: [../docs/DISPATCH.md](../docs/DISPATCH.md).

## 0. Prerequisites

**Cursor wire agent verifies** (no Principal interview):

- [ ] Git repository with `development`, `staging`, `main` branches (or documented equivalents)
- [ ] GitHub remote connected (`gh repo view`)
- [ ] Cursor account for Cloud Agents API (Principal supplies `CURSOR_API_KEY` secret)
- [ ] Principal policy documented: **Go**, **Continue**, `staging`/`main` only by Principal

## 1. Copy pack

**Cursor wire agent** (deployed instance skips copy if present):

- [ ] `LiNKdev/` exists at repository root
- [ ] Portable Cursor shim: `cp -R LiNKdev/factory/install/portable-cursor/.cursor ./` if missing
- [ ] `LiNKdev/README.md` and `LiNKdev/factory/SPEC.md` present
- [ ] Product-specific `.cursor/rules/01`–`08` when needed (add per host repo during wire)

## 2. GitHub labels

**Cursor wire agent runs:**

```bash
LiNKdev/factory/scripts/install-labels.sh
```

- [ ] Script exited 0; `gh label list` shows `linkdev:*`, `runtime:*`, `tier:*`

## 3. GitHub Actions (guard + dispatch)

**Cursor wire agent copies** from `LiNKdev/factory/install/github/` to `.github/workflows/`:

- [ ] `linkdev-guard.yml`
- [ ] `linkdev-dispatch.yml`
- [ ] `branch-source-policy.yml`
- [ ] Files committed on `development`

## 4. Dispatch secret

**Principal adds** (agents document status only):

- [ ] GitHub Actions secret `CURSOR_API_KEY` configured on this repository

## 5. Dispatch triggers (verify)

**Cursor dispatch agent** — [EXECUTE-LINKDEV-DISPATCH-INSTALL.md](EXECUTE-LINKDEV-DISPATCH-INSTALL.md):

- [ ] Workflow **LiNKdev dispatch** visible in Actions
- [ ] Orchestrator — PR merged to `development` (or `workflow_dispatch`)
- [ ] Reviewer — label `linkdev:review-ready` on PR
- [ ] Integrator — label `linkdev:merge-ready` on PR
- [ ] Executor — issue labels `linkdev:ready` **and** `runtime:cursor` (AND check in workflow)

Codex executor (`runtime:codex`) — **future**; not required for wire v1.

## 6. Skills

**Cursor wire agent verifies:**

- [ ] `LiNKdev/skills/SKILLS_CATALOG.md`; bootstrap points to `LiNKdev/skills/`
- [ ] `.cursor/rules/00-linkdev-bootstrap.mdc` installed (no root `AGENTS.md`)

## 7. Product program

**Cursor wire agent verifies:**

- [ ] `LiNKdev/product/programs/<product>/PROGRAM.md` exists (draft OK pre-Go)
- [ ] Planner — **after Go**, not during wire

## 8. Go

**Principal only** (not wire agents):

- [ ] Principal says **Go**
- [ ] Program `STATE.md` phase = `running`
- [ ] Orchestrator sets first parallel group to `linkdev:ready`

## 9. Proof of wire

**Cursor post-dispatch agent** — [EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md](EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md):

- [ ] Test issue: **LiNKdev dispatch** workflow ran after `linkdev:ready` + `runtime:cursor`
- [ ] Report contains proof block and Actions run link
- [ ] `LiNKdev/factory/scripts/verify.sh` exits 0

## Done

LiNKdev is **wired**. Runtime mode is autonomous until `linkdev:principal-stop` or blocker. Principal **Go** starts the program.
