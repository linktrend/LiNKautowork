# Tailscale-Only Hardening Runbook

## Objective
Restrict LiNKautowork production interfaces to tailnet-only access and prevent public exposure drift on redeploy.

## Production publish contract

Production Compose (`deploy/prod/docker-compose.yml`) publishes **no host ports**. n8n still listens on container port `5678` for in-stack and Traefik upstreams; that is not a host `:5678` listener. Gateway health stays on container `:8080`. NATS remains on in-stack `:4222` only: the production command is `-js -sd /data` and does not enable or publish the HTTP monitor (`:8222`).

Operator HTTPS is the placeholder Traefik/Tailscale templates under `deploy/templates/`, not a Compose-published n8n port.

## One-time setup on host
Run from repo root on the VPS:

```bash
ops/security/install-tailscale-firewall-service.sh
```

This installs a systemd unit that reapplies DOCKER-USER rules on boot.

## Required env in `deploy/prod/.env`
- Approved Traefik DNS placeholders belong in the generated runtime environment (`TRAEFIK_N8N_HOST=<OPERATOR_N8N_DNS_NAME>` after that hostname is authorised). `ops/deploy-stack.sh` may rewrite `N8N_HOST`, `N8N_EDITOR_BASE_URL`, and `WEBHOOK_URL` to match; those are URL variables only and do not publish a host port.
- `N8N_TAILSCALE_IP` is not a production host `:5678` fallback. Compose does not bind n8n to the host, and the deploy script does not add a port mapping.

## Deploy flow (canonical)

```bash
ops/deploy-stack.sh prod --build
```

Behavior:
1. Resolves `*_SECRET_NAME` values from GSM.
2. Writes runtime env to `/opt/linktrend/runtime/linkautowork/prod.env.runtime` (outside repo).
3. Canonicalizes n8n URL variables when Traefik or Tailscale identity is present; it never publishes n8n on the host.
4. Starts compose stack with runtime substitutions.

## Verification

```bash
# DOCKER-USER policy present
iptables -S DOCKER-USER

# n8n URL vars in running container
docker exec prod-n8n-1 /bin/sh -lc 'printenv N8N_HOST N8N_EDITOR_BASE_URL WEBHOOK_URL'

# local parity checks
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

## Secret hygiene checks

```bash
ops/security/scan-secrets.sh
```

- Runtime env files with resolved secrets must stay outside repo path.
- Never commit `.env.runtime` files.
