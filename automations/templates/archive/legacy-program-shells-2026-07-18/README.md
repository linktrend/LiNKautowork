# Archived: legacy Program shells (2026-07-18)

**Reason:** These n8n templates were thin webhook shells that called a shelved LiNKaios invoke URL (`LINKAIOS_AUTOWORK_INVOKE_URL`). LiNKaios / LiNKtrend-System are retired and must not be part of the live architecture. Current LiNKsites no longer owns CRM/outreach via these paths; current LiNKdeveloper does not call LiNKautowork at all.

**Authority:** Principal instruction 2026-07-18 — remove LiNKaios references; archive unused Program shells; keep only governance templates that call this repo's gateway.

These files were moved with `git mv` (history preserved). They are **not** in `manifest.json` and are **not** required by `scripts/validate-templates.mjs`.

## Contents

- `linksites-*.json` (6) — including CRM/outreach leftovers
- `linksuitegen-*.json` (9)
- `linkdeveloper-*.json` (11)

## Restoring

Only restore a template when a **current** Program owns a real, deployed handler for it (not LiNKaios). Then `git mv` back into `automations/templates/`, add to `manifest.json`, and re-run `npm run validate:templates`.
