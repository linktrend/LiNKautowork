# Cursor automations

Create four automations in Cursor (Cloud Agents) for this repository.

## 1. LiNKdev-orchestrator

- **Trigger:** Pull request merged to branch `development`
- **Prompt file:** Load `LiNKdev/factory/prompts/orchestrator/ROLE.md` + read `LiNKdev/factory/STATE.md` + active `programs/*/PROGRAM.md`
- **Model:** Composer 2.5 Standard (or current default)
- **Scope:** May edit `LiNKdev/factory/STATE.md`, apply GitHub labels via `gh` CLI in instructions

## 2. LiNKdev-reviewer

- **Trigger:** Issue or PR labeled `linkdev:review-ready`
- **Prompt:** `LiNKdev/factory/prompts/reviewer/ROLE.md` + issue spec + PR diff
- **Reject vacuous PASS** per SPEC

## 3. LiNKdev-integrator

- **Trigger:** PR labeled `linkdev:merge-ready`
- **Precondition in prompt:** verify `LiNKdev/factory/scripts/verify.sh` passed (check PR body or CI)
- **Action:** Merge to `development` if Reviewer approved

## 4. LiNKdev-executor-cursor

- **Trigger:** Issue labeled `linkdev:ready` and `runtime:cursor`
- **Prompt:** `LiNKdev/factory/prompts/executor-cursor/ROLE.md` + linked issue spec under `LiNKdev/product/programs/`

## Principal UI checklist (one-time)

1. Open **Cursor → Settings → Cloud Agents → Automations** for repo `linktrend/LiNKtrend-System`.
2. Confirm GitHub labels exist (agent created 13 `linkdev:*`, `runtime:*`, `tier:*` labels via `gh`).
3. Create four automations per sections 1–4 above; paste prompts from `LiNKdev/factory/prompts/*/ROLE.md`.
4. Set default branch context to `development` for orchestrator/integrator triggers.
5. Export automation names or screenshots into this folder (no secrets).

## Export

Store automation JSON or screenshots in this folder when configured (no secrets).
