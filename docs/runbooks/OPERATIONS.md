# Operations Runbook (MVO)

Owner: LiNKtrend Platform  
Last updated: 2026-04-01

## Deploy Dev

1. Configure `deploy/dev/.env` with non-secret config and `*_SECRET_NAME` entries.
2. Validate GSM-backed secret references: `ops/render-env-from-gsm.sh dev`.
3. Render runtime env outside repo codebase: `ops/render-runtime-env-from-gsm.sh dev --output /opt/linktrend/runtime/linkautowork/dev.env.runtime`.
4. Start stack with GSM-resolved runtime env: `ops/deploy-stack.sh dev --build`.
5. Verify gateway: `curl http://localhost:8080/health`.
6. Import templates: `ops/import-templates-to-n8n.sh dev`.
7. Export runtime evidence: `ops/export-live-from-n8n.sh dev`.

## Promote To Prod

1. Ensure lifecycle approvals are complete (Auditor, Head of Quality, COO, and Principal for protected actions).
2. Configure `deploy/prod/.env` with non-secret config and `*_SECRET_NAME` entries.
3. Set `TRAEFIK_N8N_HOST=n8n.linktrend.internal` in `deploy/prod/.env` for Traefik ingress (preferred). Optional `N8N_TAILSCALE_IP` keeps direct `:5678` fallback when Traefik is unavailable.
4. Validate GSM-backed secret references: `ops/render-env-from-gsm.sh prod`.
5. Render runtime env outside repo codebase: `ops/render-runtime-env-from-gsm.sh prod --output /opt/linktrend/runtime/linkautowork/prod.env.runtime`.
6. Start/refresh prod stack with GSM runtime env: `ops/deploy-stack.sh prod --build`.
7. Install/refresh tailscale-only firewall policy: `ops/security/install-tailscale-firewall-service.sh`.
8. Import approved templates: `ops/import-templates-to-n8n.sh prod`.
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

## Public URL (Traefik on linkdroplet-00)

| Surface | URL | Verify |
|--------|-----|--------|
| n8n editor (preferred) | `https://n8n.linktrend.internal` | Tailscale DNS → Traefik `100.66.84.96:443` |
| Direct fallback | `http://100.66.84.96:5678` | Tailscale IP only; bypasses Traefik |

Traefik routes `Host(n8n.linktrend.internal)` on entrypoint `websecure` to container port `5678` on `linktrend-network`. Compose labels live on the `n8n` service in `deploy/prod/docker-compose.yml`.

Quick check from a Tailscale-connected machine:

```bash
curl -k -H 'Host: n8n.linktrend.internal' -o /dev/null -w '%{http_code}\n' https://100.66.84.96/
# expect: 200

curl -k --resolve n8n.linktrend.internal:443:100.66.84.96 -o /dev/null -w '%{http_code}\n' https://n8n.linktrend.internal/
# expect: 200
```

**Important:** keep `N8N_PORT=5678` in runtime env even when `N8N_PROTOCOL=https` and `N8N_EDITOR_BASE_URL=https://n8n.linktrend.internal`. Setting `N8N_PORT=443` makes n8n bind to 443 inside the container and breaks Traefik (which forwards to 5678) and the Docker healthcheck.
