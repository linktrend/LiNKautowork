# Wave 4 — LiNKautowork production automations proof

**Date:** 2026-06-06  
**Plan:** `LiNKtrend-System/LiNKdev/product/reports/linktrend-system/STUDIO_FORWARD_PLAN.md` §Wave 4

## Summary

| # | Deliverable | Status | Evidence |
|---|-------------|--------|----------|
| 4.1 | LinkSites templates (5) | **PASS** | `automations/templates/linksites-*.json`; manifest `ops_approved` |
| 4.2 | LiNKsuitegen factory (7) + CRM proof (2) | **PASS** | `linksuitegen-*.json` including `crm_step`, `odoo_lead_create` |
| 4.3 | LiNKdeveloper adapter keys (7) | **PASS** | `linkdeveloper-run_validation.json` … `deploy_scaffold.json` |
| 4.4 | LiNKdeveloper workflow-map (4) | **PASS** | `product_run_bootstrap`, `issue_dispatch`, `validation_record`, `artifact_write` |
| 4.5 | Gateway `linkdeveloper.ts` ingress | **PASS** | `LiNKtrend-System/LiNKautowork/gateway/src/workflows/linkdeveloper.ts` + tests |
| 4.6 | `manifest.json` + CI check | **PASS** | `npm run validate:templates` (33 manifest entries, 34 JSON files) |
| 4.7 | VPS import linkdroplet-00 | **BLOCKED** | n8n reachable; `N8N_PUBLIC_API_DISABLED=true` — see below |

## Local verification

```bash
cd LiNKautowork
npm run validate:templates   # PASS
npm test                     # PASS (13 tests)

cd LiNKtrend-System/LiNKautowork/gateway
npm test -- src/workflows/linkdeveloper.test.ts   # PASS (3 tests)

cd LiNKdeveloper
pnpm test tests/adapters/linkautowork/workflows.test.ts   # PASS (4 tests)
```

## VPS (linkdroplet-00)

- SSH: **reachable**
- n8n container: `prod-n8n-1` on `:5678`
- Import API: **404** — `N8N_PUBLIC_API_DISABLED=true` in container env
- LiNKautowork repo: **not** at `/opt/linkautowork` on VPS (templates not rsynced)

**Unblock 4.7:** Set `N8N_PUBLIC_API_DISABLED=false` (or use supported internal import path), deploy/rsync `automations/templates/`, run `ops/import-templates-to-n8n.sh prod`. See `IMPORT_AUTOMATION_TEMPLATES.md`.

## Template inventory (Wave 4 scope)

- LinkSites: 5
- LiNKsuitegen: 9 (7 factory + 2 CRM proof)
- LiNKdeveloper: 11 (7 adapter + 4 workflow-map)
- Platform/governance: 8 (unchanged)
