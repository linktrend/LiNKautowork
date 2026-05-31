# Execute: Wire LiNKdev (Cursor agent — autonomous)

**Principal launch (one line only):**  
`Execute the EXECUTE-WIRE-LINKDEV.md prompt in LiNKdev/factory/install/`

You are the **LiNKdev wire agent**. Complete every step you can **without** Principal input and **without** opening Cursor or Codex provider automation UIs (that is the Codex UI agent). Do not ask the Principal questions unless a step is **blocked** (missing auth, missing tool access, hard failure after retry).

## Rules

1. Follow [CHECKLIST.md](CHECKLIST.md) sections **0–3** and **6–7** only. **Skip §4–5** (mark `pending_codex_ui` in the wire report).
2. Do **not** run §8 (**Go**) or §9 (proof of wire) in this session — those run after UI automations (see [EXECUTE-WIRE-LINKDEV-POST-UI.md](EXECUTE-WIRE-LINKDEV-POST-UI.md)).
3. Paths and answers come from `LiNKdev/` only. Do not change product application code outside `LiNKdev/` and `.cursor/` shim fixes if required for wire.
4. Never commit secrets or `.env`.
5. Run commands yourself (`gh`, `git`, `LiNKdev/factory/scripts/*`). Record commands and output in [../../product/reports/wire/WIRE-SESSION.md](../../product/reports/wire/WIRE-SESSION.md).
6. When finished, **commit and push** wire artifacts to `development` if the repo is dirty only under `LiNKdev/product/reports/wire/` and allowed install paths.

## Section 0 — Prerequisites (verify, do not interview)

| Check | Action |
|-------|--------|
| Branches | `git branch -a` — expect `development`, `staging`, `main` (or document equivalents in wire report) |
| GitHub remote | `gh repo view` — must resolve |
| Cursor/Codex accounts | **Assume enabled** for this deployed instance; note in report if you cannot verify (not a blocker for this session) |
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

Must show all `linkdev:*` labels from [../contracts/labels.md](../contracts/labels.md). Legacy `swarm:*` labels may remain; automations must use **`linkdev:`** only.

## Section 3 — GitHub Actions guard

Confirm `.github/workflows/linkdev-guard.yml` exists on the default branch you are wiring (`development`). Note in report: enabled when workflow file is on `development` (no Principal toggle required).

## Sections 4–5 — Defer to Codex UI agent

Do **not** configure Cursor or Codex cloud automations. In `WIRE-SESSION.md` set:

```markdown
## UI automations (Step B)
- Status: pending_codex_ui
- Principal launches: Execute the EXECUTE-LINKDEV-UI-AUTOMATIONS.md prompt in LiNKdev/factory/install/
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

> **Wire Step A complete.** Codex UI automations are pending (Step B).  
> Tell the Codex agent: `Execute the EXECUTE-LINKDEV-UI-AUTOMATIONS.md prompt in LiNKdev/factory/install/`  
> When Step B is done, tell this Cursor agent: `Execute the EXECUTE-WIRE-LINKDEV-POST-UI.md prompt in LiNKdev/factory/install/`

Do not ask the Principal to confirm checklist items. Do not say **Go**.
