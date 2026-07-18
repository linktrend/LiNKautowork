# Import automation templates to n8n (linkdroplet-00)

**Wave 4 deliverable 4.7** — canonical templates under `automations/templates/` imported to production n8n on `linkdroplet-00`.

## Prerequisites

- SSH access to `linkdroplet-00`
- `gcloud` authenticated to GSM project `linkbot-901208`
- LiNKautowork repo at latest `development` (or release branch) with updated `manifest.json`

## Local proof (no VPS)

```bash
cd /Users/linktrend/Projects/LiNKautowork
npm run validate:templates
```

Expected: `Template validation passed for N JSON files (M manifest entries).`

Regenerate templates if handles change:

```bash
node ops/generate-linksites-n8n-templates.mjs
node scripts/scaffold-linksuitegen-templates.mjs
node scripts/scaffold-linkdeveloper-templates.mjs
npm run validate:templates
```

## VPS import (linkdroplet-00)

```bash
# On operator machine with repo + gcloud
cd /Users/linktrend/Projects/LiNKautowork
git pull origin development   # or target release branch

# Sync repo to VPS (if not already deployed via CI/CD)
rsync -avz --delete \
  automations/templates/ \
  linkdroplet-00:/opt/linkautowork/automations/templates/

# On VPS (or via SSH one-liner)
ssh linkdroplet-00 'cd /opt/linkautowork && GCP_PROJECT_ID=linkbot-901208 ops/import-templates-to-n8n.sh prod'
```

Alternative one-liner from local machine (requires env file on VPS path):

```bash
ssh linkdroplet-00 'cd /opt/linkautowork && GCP_PROJECT_ID=linkbot-901208 bash ops/import-templates-to-n8n.sh prod'
```

## Post-import verification

1. List workflows in n8n UI (`https://n8n.linktrend.internal`) — count should match `manifest.json` entries minus `manifest.json` itself.
2. Spot-check webhook paths:
   - `linksites-artifact_write_local`
   - `linksuitegen-orchestrator_cycle`
   - `linkdeveloper-run_validation`
   - `linkdeveloper-product_run_bootstrap`
3. Optional live invoke:

```bash
cd /Users/linktrend/Projects/LiNKtrend-System
export LINKAUTOWORK_INVOKE_SECRET="$(gcloud secrets versions access latest --project linkbot-901208 --secret LINKTREND_AIOS_PROD_AUTOWORK_INVOKE_TOKEN)"
VERIFY_N8N_WEBHOOK=1 ./scripts/verify-linkautowork-live.sh
```

## Manifest parity

`scripts/validate-templates.mjs` enforces:

- Every `*.json` workflow file is listed in `manifest.json`
- Every manifest entry exists on disk
- Wave 4 required templates (LinkSites, LiNKsuitegen factory + CRM proof, LiNKdeveloper adapter + workflow-map) are present
- Canonical tenant UUID `00000000-0000-0000-0000-000000000001` appears in each template `meta`

## Rollback

Re-import prior `automations/live/prod/` export snapshot via n8n API or restore from backup volume on linkdroplet-00.
