# LiNKautowork — Historical Deploy-Readiness Snapshot

**Status:** superseded for release decisions by WP-12 evidence.
**Purpose:** retain earlier implementation context only; it is not evidence of a live environment or deployment authority.

## Architecture closed

| Item | Status |
|------|--------|
| Control and isolation schemas | Local migration source exists; live application requires authorisation |
| Compose `DB_POSTGRESDB_SCHEMA=lautowork_n8n` | Fixed (retired `_prod` suffix removed) |
| Pinned n8n image `2.30.0` (not `:latest`) | Done |
| Stock upstream n8n only (no `link-n8n` fork/submodule) | Done (2026-07-23) |
| Kill-switch + lifecycle persisted to DB + hydrate on boot | Done (8A) |
| Historical Program shells removed from live set | Archived as non-authoritative evidence |
| Secrets contract = GSM `*_SECRET_NAME` only in `.env.example` | Cleaned |
| `N8N_PUBLIC_API_DISABLED=false` | Intentional (import + global kill-switch); Tailscale-bind required |
| Integration branch | Verify from Git at release time |

## Historical operator sequence

1. Install Docker + Tailscale; run `ops/security/install-tailscale-firewall-service.sh` for ports `5678`, `8080`, `4222`, `8222`.
2. Place GCP credentials for GSM at the path in `.env`.
3. Ensure GSM secrets exist for every `*_SECRET_NAME` in the env example.
4. Render runtime env and start stack (`ops/deploy-stack.sh`).
5. Import templates; activate governance workflows.
6. Smoke test:
   - `GET /health` on gateway
   - Activate scoped kill-switch → confirm ingress blocked → release
   - Confirm rows in `lautowork.killswitch_events` and `lautowork.audit_runs`
7. Backup drill: `ops/run-backup.sh` + `ops/restore-drill.sh` (stage first).

## Current external inputs

- Choosing / provisioning the VPS
- Filling real GSM secret values and Traefik hostnames
- Slack channel wiring (optional for first smoke)

## Current release checklist

Use `docs/runbooks/PRODUCTION_RELEASE_GATES.md`, `docs/runbooks/OPERATIONS.md`, and the WP-12 VPS Deployment Input Register. No live step is authorised by this historical snapshot.
