# Create Cursor automations (Codex computer use)

You are configuring **Cursor** automations for LiNKdev. Use computer use to navigate the Cursor UI. Do not store secrets in the repo.

## Prerequisites

- Wire completed (`factory/install/CHECKLIST.md`)
- GitHub labels installed (`factory/scripts/install-labels.sh`)

## For each row in AUTOMATION-MANIFEST.md (Cursor section)

1. Open Cursor → Automations (or Cloud Agents) → Create automation.
2. Name exactly as manifest (e.g. `LiNKdev-orchestrator`).
3. Set trigger per manifest.
4. System prompt: read and follow the linked `factory/prompts/<role>/ROLE.md` from the repo.
5. Restrict context to repository; prefer issue branch when executor.
6. Save and enable.

## Verify

- Triggers visible in UI
- Test label `linkdev:review-ready` on a dry-run issue does not run until Reviewer automation exists

## Handoff

Report automation names created in `LiNKdev/product/reports/wire-automation-setup.md` (create if missing).
