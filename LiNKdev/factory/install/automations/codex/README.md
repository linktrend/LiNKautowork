# Codex automations

Codex executors are **peer automations** to Cursor cloud agents. Same GitHub labels; separate Codex automation entries.

## LiNKdev-executor-codex

- **Trigger:** GitHub issue labeled `linkdev:ready` AND `runtime:codex`
- **Filter:** Issue body or path references `LiNKdev/programs/` (optional narrow filter)
- **Prompt:** `LiNKdev/factory/prompts/executor-codex/ROLE.md` + issue spec from `LiNKdev/factory/programs/bootstrap/issues/<id>.md`
- **Branch:** `dev/minicodex` or `issue/<id>-*`

## Planner checklist

For each Codex issue group in PROGRAM.md, duplicate trigger with same label contract — do not rely on Principal manual launch.

## Proof

Automation run must update `LiNKdev/product/reports/<id>.md` and push branch without Principal starting Codex.

## Principal UI checklist (one-time)

1. Open **Codex → Automations** (or project automations UI) for **this repository** (`{org}/{host-repo}`).
2. Create **LiNKdev-executor-codex** with trigger: issue labels `linkdev:ready` + `runtime:codex`.
3. Point prompt at `LiNKdev/factory/prompts/executor-codex/ROLE.md` and issue spec under `LiNKdev/product/programs/`.
4. Default branch: `dev/minicodex` (or `issue/<id>-*` per issue template).
5. Record automation ID in this folder after save.

## Export

Document Codex automation IDs in this folder after Principal configures UI.
