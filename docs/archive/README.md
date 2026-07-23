# Archive — superseded by the current source-of-truth documents

Everything under `docs/archive/` is retained for history but is **no longer authoritative**. Some of it (two-schema control model, pre-persistence kill-switch, custom-image assumptions, early ADR findings about undeployed writers) is factually stale relative to the code as it stands today.

**Do not confuse this folder with** `archive/legacy-dev-mirrors-2026-07-15/` at the repo root — that tree is a separate, pre-existing bulk archive and is left untouched by documentation cleanups.

**Current source of truth (2026-07-19):**

- [`../LINKAUTOWORK-INTENT.md`](../LINKAUTOWORK-INTENT.md) — why LiNKautowork exists, scope, and what "done" means.
- [`../LINKAUTOWORK-TECHNICAL-PRD.md`](../LINKAUTOWORK-TECHNICAL-PRD.md) — the exhaustive technical reference for how the system actually works, including a §12 table of exactly where these archived documents have drifted from the real code.
- [`../LINKAUTOWORK-OPERATIONS-MANUAL.md`](../LINKAUTOWORK-OPERATIONS-MANUAL.md) — plain-English handbook for the Principal.
- [`../OPEN-ISSUES.md`](../OPEN-ISSUES.md) — the append-only engineering build / compliance log (formerly root `IMPLEMENTATION_AGAINST_PRD.md`).

**Still live (not archived):** `../DEPLOY_READINESS.md`, `../SLO.md`, `../runbooks/*` — operational procedures still used for real bring-up and reliability targets.

## What's here

- `root-docs/` — original root PRD, plain-English explainer, and short git-strategy note.
- `UPSTREAM.md` — **retired** former fork policy (stock upstream n8n only as of 2026-07-23; see Technical PRD §5).
- `AUTOMATION_LIFECYCLE.md` / `CONTRACTS.md` — former contract snippets (now Technical PRD §§7–10).
- `DOCUMENTATION_GOVERNANCE.md` — former docs process (superseded by this archive convention + the four SoT documents).
- `RELEASE_GATE_CHECKLIST.md` — former first-bring-up checklist (content retained in runbooks + Deploy Readiness).
- `BRANCHING_AND_DEPLOYMENT_POLICY.md` — former branching prose (operative rules remain in `.cursor/rules/01-git-branching.mdc`, `AGENTS.md`, and `.github/workflows/branch-source-policy.yml`; summary also in Technical PRD §14).
- `adr/0001-adopt-shared-platform-org-model.md` — historical ADR rationale for the shared org model; decisions are implemented in migrations + gateway. Consult the Technical PRD for current state.

If something here conflicts with the Intent, Technical PRD, or Operations Manual, **those three documents win.**
