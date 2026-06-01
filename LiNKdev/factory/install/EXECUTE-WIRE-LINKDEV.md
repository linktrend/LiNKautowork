# Execute: Wire LiNKdev (Cursor agent — autonomous)

**Principal launch (one line only):**  
`Execute the EXECUTE-WIRE-LINKDEV.md prompt in LiNKdev/factory/install/`

You are the **LiNKdev wire agent**. Complete every step you can **without** Principal input and **without** Cursor Automations UI (deprecated — use dispatch v2). Do not ask the Principal questions unless a step is **blocked** (missing auth, missing tool access, hard failure after retry).

## Rules

1. Follow [CHECKLIST.md](CHECKLIST.md) sections **0–3** and **6–7** only. **Skip §4–5** (dispatch install is Step B).
2. Do **not** run §8 (**Go**) or §9 (proof of wire) in this session — see [EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md](EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md) after Step B.
3. Paths and answers come from `LiNKdev/` only. Do not change product application code outside `LiNKdev/` and `.cursor/` shim fixes if required for wire.
4. Never commit secrets or `.env`.
5. Run commands yourself (`gh`, `git`, `LiNKdev/factory/scripts/*`). Record commands and output in [../../product/reports/wire/WIRE-SESSION.md](../../product/reports/wire/WIRE-SESSION.md).
6. When finished, **commit and push** wire artifacts to `development` if the repo is dirty only under `LiNKdev/product/reports/wire/`, `.github/workflows/`, and allowed install paths.

## Section 0 — Prerequisites (verify, do not interview)

| Check | Action |
|-------|--------|
| Branches | `git branch -a` — expect `development`, `staging`, `main` (or document equivalents in wire report) |
| GitHub remote | `gh repo view` — must resolve |
| Cursor Cloud Agents | **Assume API available** when `CURSOR_API_KEY` is set (Step B); note in report if unknown |
| Principal policy | Note in report: **Go**, **Continue**, `staging`/`main` promotion are Principal-only per SPEC |

## Section 1 — Copy pack (deployed instance)

| Check | Action |
|-------|--------|
| `LiNKdev/` at root | Must exist; if missing, **STOP** with blocker |
| `.cursor/` shim | Must include `rules/00-linkdev-bootstrap.mdc`; sync from `LiNKdev/factory/install/portable-cursor/.cursor/` only if missing or stale |
| Spec read | Confirm `LiNKdev/factory/SPEC.md` and `LiNKdev/README.md` present |
| Product rules | Host repo: `.cursor/rules/01`–`08` may exist — do not remove |

## Section 2 — GitHub labels

```bash
LiNKdev/factory/scripts/install-labels.sh
gh label list --limit 200 | grep -E 'linkdev:|runtime:|tier:'
```

Must show all `linkdev:*` labels from [../contracts/labels.md](../contracts/labels.md). Legacy `swarm:*` labels may remain; dispatch uses **`linkdev:`** only.

## Section 3 — GitHub Actions (guard + dispatch)

Copy workflow stubs to the repository (create `.github/workflows/` if needed):

```bash
mkdir -p .github/workflows
cp LiNKdev/factory/install/github/linkdev-guard.yml .github/workflows/
cp LiNKdev/factory/install/github/linkdev-dispatch.yml .github/workflows/
cp LiNKdev/factory/install/github/linkdev-planner-bootstrap.yml .github/workflows/
cp LiNKdev/factory/install/github/linkdev-orchestrator-bootstrap.yml .github/workflows/
cp LiNKdev/factory/install/github/branch-source-policy.yml .github/workflows/
```

Commit these files to `development`. Note in `WIRE-SESSION.md`: workflows enabled when present on `development`. See [../docs/DISPATCH.md](../docs/DISPATCH.md).

## Sections 4–5 — Defer to dispatch install (Step B)

Do **not** configure Cursor Automations UI. In `WIRE-SESSION.md` set:

```markdown
## Dispatch (Step B)
- Status: pending_dispatch_install
- Principal launches: Execute the EXECUTE-LINKDEV-DISPATCH-INSTALL.md prompt in LiNKdev/factory/install/
- Principal manual: add GitHub secret CURSOR_API_KEY
```

## Section 6 — Skills

Confirm `LiNKdev/skills/SKILLS_CATALOG.md` exists; bootstrap rule points to `LiNKdev/skills/` not flat `.cursor/skills/` bodies.

## Section 7 — Product program

Confirm `LiNKdev/product/programs/<product-id>/PROGRAM.md` exists for this repo. **Draft** status is OK pre-Go. Do not run Planner in this session.

## Proof commands (this session)

```bash
LiNKdev/factory/scripts/verify.sh
```

Must exit 0. Paste summary into `WIRE-SESSION.md`.

## Completion message to Principal (only output)

When done, print **only**:

> **Wire Step A complete.** Dispatch install is pending (Step B).  
> Add **`CURSOR_API_KEY`** in GitHub Actions secrets if not already set.  
> Tell this Cursor agent: `Execute the EXECUTE-LINKDEV-DISPATCH-INSTALL.md prompt in LiNKdev/factory/install/`  
> When Step B is done: `Execute the EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md prompt in LiNKdev/factory/install/`

Do not ask the Principal to confirm checklist items. Do not say **Go**.
