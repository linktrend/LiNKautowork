# Tailscale-Only Hardening Runbook (source contract)

## Objective

Keep LiNKautowork production interfaces private. This packet records the
Compose and template contract only. **Live Tailscale, firewall, SSH, and
Server01 mutation remain HOLD (AW-08).**

## Protected Ports (must not bind 0.0.0.0 on the host)

- `5678` (n8n editor/webhooks) — `autowork-runtime` only
- `8080` (gateway / Product API / operator console) — `autowork-edge` only
- `4222` (NATS client) — `autowork-events` only
- `8222` (NATS monitor) — unpublished

Production Compose publishes **no** host `ports:` mappings.

## Source contract

- Private Traefik routers: `deploy/templates/traefik-dynamic.yml.example`
  (Tailscale CIDR allow-list). No public `client-web` router in the initial
  release.
- Boundary placeholders: `deploy/templates/tailscale-boundary.env.example`
- Compose networks: `autowork-edge`, `autowork-runtime`, `autowork-events`

Do not treat `N8N_TAILSCALE_IP` as a parser that rewrites n8n URLs to a raw
IP. Operator URLs come from authorised DNS placeholders (`TRAEFIK_N8N_HOST`).
Empty `N8N_TAILSCALE_IP` in `.env.example` is intentional.

## Host install (AW-08 HOLD)

The following is **not** executed by AW-05:

```bash
# HOLD — Server01 only after founder/Platform authority
# ops/security/install-tailscale-firewall-service.sh
```

## Deploy flow (canonical source-only)

```bash
ops/deploy-stack.sh prod --dry-run --print-release-layout
ops/verify-server01-acceptance.sh --environment prod
```

Expected behaviour:

1. Validates `*_SECRET_NAME` placeholders (no GSM read).
2. Writes a disposable mode-`0600` placeholder runtime env **outside git**.
3. Renders Compose config if Docker is available. Does not `up`.
4. Prints the atomic `current` → `releases/<commit>` layout without applying it.

## Verification (local / disposable)

```bash
docker compose -f deploy/prod/docker-compose.yml --env-file deploy/prod/.env.example config
npm run test -- scripts/tests/deployment-readiness.test.mjs
```

Do not `docker exec` a production container from this packet. Do not scan a live
tailnet. Image digests stay `HOLD` in `deploy/prod/release-identity.json` until
an authorised host build records them. Registry credentials are not required
(`NOT_APPLICABLE` for the initial path).
