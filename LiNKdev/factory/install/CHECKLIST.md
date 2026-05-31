# Wire LiNKdev — Install Checklist

Agents execute this checklist **autonomously**. The Principal only sends one-line launches in [PRINCIPAL-LAUNCH.md](PRINCIPAL-LAUNCH.md).

| Sections | Agent | Prompt file |
|----------|--------|-------------|
| 0–3, 6–7 | Cursor | [EXECUTE-WIRE-LINKDEV.md](EXECUTE-WIRE-LINKDEV.md) |
| 4–5 | Codex (computer use) | [EXECUTE-LINKDEV-UI-AUTOMATIONS.md](EXECUTE-LINKDEV-UI-AUTOMATIONS.md) |
| 9 (+ wire sign-off) | Cursor | [EXECUTE-WIRE-LINKDEV-POST-UI.md](EXECUTE-WIRE-LINKDEV-POST-UI.md) |
| 8 **Go** | Principal only | `linkdev-go` / **Go** — not part of wire |

Progress is recorded in `LiNKdev/product/reports/wire/WIRE-SESSION.md`.

## 0. Prerequisites

**Cursor wire agent verifies** (no Principal interview):

- [ ] Git repository with `development`, `staging`, `main` branches (or documented equivalents)
- [ ] GitHub remote connected (`gh repo view`)
- [ ] Cursor and Codex accounts assumed enabled for deployed instances
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

## 3. GitHub Actions guard

**Cursor wire agent verifies:**

- [ ] `.github/workflows/linkdev-guard.yml` on `development`

## 4. Cursor automations

**Codex UI agent only** — [EXECUTE-LINKDEV-UI-AUTOMATIONS.md](EXECUTE-LINKDEV-UI-AUTOMATIONS.md) + [automations/CURSOR-CREATE-AUTOMATIONS.md](automations/CURSOR-CREATE-AUTOMATIONS.md)

- [ ] Orchestrator — trigger: merge to `development`
- [ ] Reviewer — trigger: label `linkdev:review-ready`
- [ ] Integrator — trigger: label `linkdev:merge-ready`
- [ ] Executor — trigger: `linkdev:ready` + `runtime:cursor`

## 5. Codex automations

**Codex UI agent only** — [EXECUTE-LINKDEV-UI-AUTOMATIONS.md](EXECUTE-LINKDEV-UI-AUTOMATIONS.md) + [automations/CODEX-CREATE-AUTOMATIONS.md](automations/CODEX-CREATE-AUTOMATIONS.md)

- [ ] Executor — trigger: `linkdev:ready` + `runtime:codex`

## 6. Skills

**Cursor wire agent verifies:**

- [ ] `LiNKdev/skills/SKILLS_CATALOG.md`; bootstrap points to `LiNKdev/skills/`
- [ ] `.cursor/rules/00-linkdev-bootstrap.mdc` installed (no root `AGENTS.md`)

## 7. Product program

**Cursor wire agent verifies:**

- [ ] `LiNKdev/product/programs/<product>/PROGRAM.md` exists (draft OK pre-Go)
- [ ] Planner / Codex issue-group automations — **after Go**, not during wire

## 8. Go

**Principal only** (not wire agents):

- [ ] Principal says **Go**
- [ ] Program `STATE.md` phase = `running`
- [ ] Orchestrator sets first parallel group to `linkdev:ready`

## 9. Proof of wire

**Cursor post-UI agent** — [EXECUTE-WIRE-LINKDEV-POST-UI.md](EXECUTE-WIRE-LINKDEV-POST-UI.md):

- [ ] Test issue: automation fired without manual executor launch
- [ ] Report contains proof block
- [ ] `LiNKdev/factory/scripts/verify.sh` exits 0

## Done

LiNKdev is **wired**. Runtime mode is autonomous until `linkdev:principal-stop` or blocker. Principal **Go** starts the program.
