# LiNKdev

Portable AI software factory. **Copy `.cursor/` + `LiNKdev/`** into a new repo.

## Structure (v2 — 2026-05-30)

```
LiNKdev/
  AGENTS.md              # Start here
  factory/               # Same on every repo
    SPEC.md STATE.md BORROW-PACK.md
    contracts/ templates/ scripts/ install/ prompts/ agents/ rules/
    programs/bootstrap/
    reports/bootstrap/
  product/               # Filled per repo (LiNKtrend content today)
    grounding/           # Vision, ship criteria, decisions, plans
    programs/<program-id>/modules/.../phases/.../issues/
    reports/<program>/<module>/<phase>/<issue>.md
  skills/
    gstack/              # Required template
    host/                # Empty in virgin template
  archive/               # Read-only history
```

## First run

1. Wire Step A — `factory/install/EXECUTE-WIRE-LINKDEV.md`
2. Dispatch — `factory/install/EXECUTE-LINKDEV-DISPATCH-INSTALL.md` + `factory/docs/DISPATCH.md`
3. Post-dispatch proof — `factory/install/EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md`
4. Go — Planner cloud (`factory/prompts/planner/ROLE.md`)

See `factory/SPEC.md`.
