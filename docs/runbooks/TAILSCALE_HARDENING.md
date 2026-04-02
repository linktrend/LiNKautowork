# Tailscale-Only Hardening Runbook

## Objective
Restrict LiNKautowork production interfaces to tailnet-only access and prevent public exposure drift on redeploy.

## Protected Ports
- `5678` (n8n editor/webhooks)
- `8080` (gateway)
- `4222` (NATS client)
- `8222` (NATS monitor)

## One-time setup on host
Run from repo root on the VPS:

```bash
ops/security/install-tailscale-firewall-service.sh
```

This installs a systemd unit that reapplies DOCKER-USER rules on boot.

## Required env in `deploy/prod/.env`
- `N8N_TAILSCALE_IP=<tailnet IPv4>`
- `N8N_HOST` can be any placeholder; runtime rendering will canonicalize to `N8N_TAILSCALE_IP`.

## Deploy flow (canonical)

```bash
ops/deploy-stack.sh prod --build
```

Behavior:
1. Resolves `*_SECRET_NAME` values from GSM.
2. Writes runtime env to `/opt/linktrend/runtime/linkautowork/prod.env.runtime` (outside repo).
3. Canonicalizes n8n URL settings to Tailscale IP.
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
