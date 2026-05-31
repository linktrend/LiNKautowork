# LiNKdev wire session — LiNKautowork

- **Repo:** linktrend/LiNKautowork
- **Branch:** development
- **Wire agent:** Cursor (Step A)
- **Session date:** 2026-05-31

## Principal launch (only these lines)

See `LiNKdev/factory/install/PRINCIPAL-LAUNCH.md`.

| Step | Status |
|------|--------|
| A — `EXECUTE-WIRE-LINKDEV.md` | **complete** |
| B — `EXECUTE-LINKDEV-UI-AUTOMATIONS.md` | **pending_codex_ui** |
| C — `EXECUTE-WIRE-LINKDEV-POST-UI.md` | **blocked** until B complete |
| 8 — Go (Planner) | **blocked** — canonical program runs on LiNKtrend-System |

## UI automations (Step B)

- **Status:** pending_codex_ui
- **Principal launches Codex with:** `Execute the EXECUTE-LINKDEV-UI-AUTOMATIONS.md prompt in LiNKdev/factory/install/`
- **Note:** Automation specs live under `LiNKdev/factory/install/automations/`; Codex UI agent fills `wire-automation-setup.md` when created.

## Step C block

Step C (`EXECUTE-WIRE-LINKDEV-POST-UI.md`) requires all five core automations in `wire-automation-setup.md` with **Created=Y** and **Trigger verified=Y**. Do not launch Step C until Step B is **complete**.

## Checklist (CHECKLIST.md)

### §0 Prerequisites — complete

- [x] Branches: `development`, `staging`, `main` present locally and on origin
- [x] GitHub remote: `gh repo view` → `linktrend/LiNKautowork`
- [x] Cursor/Codex accounts: assumed enabled for deployed instance (not verifiable from CLI)
- [x] Principal policy: **Go**, **Continue**, `staging`/`main` promotion are Principal-only per SPEC

### §1 Copy pack — complete

- [x] `LiNKdev/` at repository root
- [x] `.cursor/rules/00-linkdev-bootstrap.mdc` present (matches portable-cursor template; no sync needed)
- [x] `LiNKdev/README.md` and `LiNKdev/factory/SPEC.md` present
- [x] Product rules: host `.cursor/rules/` includes bootstrap + LiNKautowork rules (`01`–`07`, `10`, `11`, `15`)

### §2 GitHub labels — complete

- [x] `LiNKdev/factory/scripts/install-labels.sh` exited 0 (15 definitions)
- [x] All `linkdev:*`, `runtime:*`, `tier:*` labels visible via `gh label list`

### §3 GitHub Actions guard — complete

- [x] `.github/workflows/linkdev-guard.yml` on `development` (local + `git show development:...`)
- [x] Enabled when workflow file is on `development` (no Principal toggle required)

### §4 Cursor automations — pending_codex_ui

- [ ] LiNKdev-orchestrator — merge to `development`
- [ ] LiNKdev-reviewer — `linkdev:review-ready`
- [ ] LiNKdev-integrator — `linkdev:merge-ready`
- [ ] LiNKdev-executor-cursor — `linkdev:ready` + `runtime:cursor`

### §5 Codex automations — pending_codex_ui

- [ ] LiNKdev-executor-codex — `linkdev:ready` + `runtime:codex`

### §6 Skills — complete

- [x] `LiNKdev/skills/SKILLS_CATALOG.md` present
- [x] Bootstrap rule points to `LiNKdev/skills/` (not flat `.cursor/skills/` bodies)
- [x] Host `AGENTS.md` at repo root (LiNKtrend dev standards); LiNKdev entry remains `.cursor/rules/00-linkdev-bootstrap.mdc`

### §7 Product program — complete

- [x] `LiNKdev/product/programs/linkautowork/PROGRAM.md` exists (status: execution-target; canonical program `linktrend-system` on LiNKtrend-System)
- [x] `LiNKdev/factory/STATE.md` JSON valid (bootstrap program_id `bootstrap`, phase `complete`)
- [x] Planner / issue-group automations deferred — Principal **Go** runs against LiNKtrend-System program host

### §8 Go — not executed (Principal only)

- [ ] Principal says **Go** (canonical program host: LiNKtrend-System)

### §9 Proof of wire — blocked until Step B + C

- [ ] Dry-run test issue: executor automation fired
- [ ] Report contains proof block
- [x] `verify.sh` exits 0 (Step A proof below)

## Agent log

### Commands run (Step A)

```bash
git branch -a
# * development, main, staging; remotes origin/development, origin/main, origin/staging

gh repo view
# name: linktrend/LiNKautowork — resolved OK

# Section 1 — pack checks
test -d LiNKdev && test -f LiNKdev/factory/SPEC.md && test -f LiNKdev/README.md
test -f .cursor/rules/00-linkdev-bootstrap.mdc
diff -q LiNKdev/factory/install/portable-cursor/.cursor/rules/00-linkdev-bootstrap.mdc .cursor/rules/00-linkdev-bootstrap.mdc
# (identical — shim not copied)

LiNKdev/factory/scripts/install-labels.sh
# OK: labels ensured on linktrend/LiNKautowork (15 definitions)

gh label list --limit 200 | grep -E 'linkdev:|runtime:|tier:'
# linkdev:planned, linkdev:ready, linkdev:in-progress, linkdev:review-ready,
# linkdev:blocked, linkdev:merge-ready, linkdev:done, linkdev:principal-stop,
# linkdev:program-active, linkdev:promote-main, linkdev:promote-staging,
# runtime:cursor, runtime:codex, tier:standard, tier:critical

git show development:.github/workflows/linkdev-guard.yml | head -5
# name: LiNKdev guard — present on development

LiNKdev/factory/scripts/verify.sh
# == verify passed == ; VERIFY OK: tier A gates passed ; exit 0
```

### verify.sh summary (Step A proof)

```
== LiNKdev verify (tier=standard scope=LiNKdev) ==
state json ok
VERIFY OK: no obvious secret assignments in LiNKdev
VERIFY OK: scripts present
VERIFY OK: contracts json valid
== verify passed ==
== LiNKdev gates tier=A scope=LiNKdev program=— report=— ==
GATE OK:   verify_subset
GATE OK:   secrets_scan
GATE SKIP: proof_block_present (no --report)
GATE SKIP: allowed_files_respected (no --report)
GATE SKIP: working_tree_clean (no --report)
== gates summary tier=A passed=2 skipped=3 failed=0 ==
VERIFY OK: tier A gates passed
```

### Blockers

None for Step A.
