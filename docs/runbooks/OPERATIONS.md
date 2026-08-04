# Operations Runbook (MVO)

Owner: LiNKtrend Platform  
Last updated: 2026-04-01

## Deployment sequence (authorised environment only)

1. Configure `deploy/dev/.env` with non-secret config and `*_SECRET_NAME` entries.
2. Validate GSM-backed secret references: `ops/render-env-from-gsm.sh dev`.
3. Render runtime env outside repo codebase: `ops/render-runtime-env-from-gsm.sh dev --output /opt/linktrend/runtime/linkautowork/dev.env.runtime`.
4. Start stack with GSM-resolved runtime env: `ops/deploy-stack.sh dev --build`.
5. Verify gateway: `curl http://localhost:8080/health`.
6. Start the recurring operations profile with the generated runtime environment: `docker compose -f deploy/prod/docker-compose.yml --env-file /approved/runtime.env --profile operations up -d operations-scheduler`.
7. Preflight certified packages with no network action: `ops/publish-certified-packages.sh --environment stage --dry-run`.

## Promote To Prod

1. Ensure lifecycle approvals are complete (Auditor, Head of Quality, COO, and Principal for protected actions).
2. Configure `deploy/prod/.env` with non-secret config and `*_SECRET_NAME` entries.
3. Set `TRAEFIK_N8N_HOST=n8n.linktrend.internal` in `deploy/prod/.env` for Traefik ingress (preferred). Optional `N8N_TAILSCALE_IP` keeps direct `:5678` fallback when Traefik is unavailable.
4. Validate GSM-backed secret references: `ops/render-env-from-gsm.sh prod`.
5. Render runtime env outside repo codebase: `ops/render-runtime-env-from-gsm.sh prod --output /opt/linktrend/runtime/linkautowork/prod.env.runtime`.
6. Start/refresh the approved stack and its required scheduler profile: `docker compose -f deploy/prod/docker-compose.yml --env-file /approved/runtime.env --profile operations up -d`.
7. Run a no-network publisher preflight: `ops/publish-certified-packages.sh --environment prod --dry-run`.
8. In the approved release window only, set the approved target and authorisation reference in the generated runtime environment, then run `docker compose -f deploy/prod/docker-compose.yml --env-file /approved/runtime.env --profile release-jobs run --rm certified-package-publisher ./ops/publish-certified-packages.sh --environment prod --activate`.
9. Export runtime evidence: `ops/export-live-from-n8n.sh prod`.

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

## Security Verification

- Secret hygiene scan in repository: `ops/security/scan-secrets.sh`
- Confirm runtime env files with resolved secrets are outside repo path and mode `600`.
- Confirm n8n/browser ingress is tailscale-only for protected ports (`5678`, `8080`, `4222`, `8222`).

## Ingress

There is no approved VPS, hostname, Tailscale boundary, or Traefik route in this repository. Use only the placeholders in `deploy/templates/` after their values are authorised and recorded. Keep `N8N_PORT=5678`: a reverse proxy terminates TLS externally and forwards to that internal port.
