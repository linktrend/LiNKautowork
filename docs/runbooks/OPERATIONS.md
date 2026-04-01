# Operations Runbook (MVO)

Owner: LiNKtrend Platform  
Last updated: 2026-04-01

## Deploy Dev

1. Configure `deploy/dev/.env` with non-secret config and `*_SECRET_NAME` entries.
2. Render GSM-backed runtime env: `ops/render-env-from-gsm.sh dev`.
3. Start stack: `docker compose --env-file deploy/dev/.env.runtime -f deploy/dev/docker-compose.yml up -d --build`.
4. Verify gateway: `curl http://localhost:8080/health`.
5. Import templates: `ops/import-templates-to-n8n.sh dev`.
6. Export runtime evidence: `ops/export-live-from-n8n.sh dev`.

## Promote To Prod

1. Ensure lifecycle approvals are complete (Auditor, Head of Quality, COO, and Chairman for protected actions).
2. Configure `deploy/prod/.env` with non-secret config and `*_SECRET_NAME` entries.
3. Render GSM-backed runtime env: `ops/render-env-from-gsm.sh prod`.
4. Start/refresh prod stack: `docker compose --env-file deploy/prod/.env.runtime -f deploy/prod/docker-compose.yml up -d --build`.
5. Import approved templates: `ops/import-templates-to-n8n.sh prod`.
6. Export runtime evidence: `ops/export-live-from-n8n.sh prod`.

## Kill Switch

- Scoped: call `/v1/control/killswitch/scoped` with `action=activate`.
- Global: call `/v1/control/killswitch/global` with `action=activate`.
- Global activation deactivates active n8n workflows via API.
- Release operations require governed restore flow and audit evidence.

## Backup and Restore Drill

- Backup: `ops/run-backup.sh`
- Drill validation: `ops/restore-drill.sh <db-backup.sql.gz> <templates-backup.tar.gz>`
- RTO target: `<= 60 min`
- RPO target: `<= 15 min`
