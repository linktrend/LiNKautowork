# Import certified automation templates to n8n

**Deployment-only runbook.** It is not a pre-VPS instruction. Use only after the WP-12 VPS Deployment Input Register is complete and a Principal-authorised change window exists.

## Prerequisites

- SSH/Tailscale access to the approved target
- `gcloud` authenticated to the approved GSM project
- LiNKautowork repo at latest `development` (or release branch) with updated `manifest.json`

## Local proof (no VPS)

```bash
cd /Users/linktrend/Projects/LiNKautowork
npm run validate:templates
```

Expected: `Template validation passed for N JSON files (M manifest entries).`

Current releases never generate historical program shells. Certified package publication is the only supported source for new workflow material.

## Approved-target import

```bash
# On operator machine with repo + gcloud
cd /Users/linktrend/Projects/LiNKautowork
git pull origin development   # or target release branch

ops/import-templates-to-n8n.sh prod
```

Record the selected host, GSM project, exact release manifest, imported workflow IDs, and export receipt in the deployment evidence store.

## Post-import verification

1. List workflows in n8n UI — count must match `manifest.json` entries.
2. Execute the approved canary and record its correlation/audit references.
3. Export the live workflow set immediately after import.

## Manifest parity

`scripts/validate-templates.mjs` enforces:

- Every `*.json` workflow file is listed in `manifest.json`
- Every manifest entry exists on disk
- Wave 4 required templates (LinkSites, LiNKsuitegen factory + CRM proof, LiNKdeveloper adapter + workflow-map) are present
- Canonical tenant UUID `00000000-0000-0000-0000-000000000001` appears in each template `meta`

## Rollback

Re-import prior `automations/live/prod/` export snapshot via n8n API or restore from backup volume on linkdroplet-00.
