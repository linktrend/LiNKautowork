# LiNKautowork — Deploy Readiness (DONE definition)

**As of:** 2026-07-18  
**DONE means:** code + schemas + compose + secrets contract + templates that only call things that exist + release steps that work — ready to drop on a VPS and live-test. A VPS hostname is an ops input, not a software hole.

## Architecture closed

| Item | Status |
|------|--------|
| Control schema `lautowork` on stage/prod | Applied |
| Isolation schema `lautowork_n8n` + role on stage/prod | Applied (this close-out) |
| Compose `DB_POSTGRESDB_SCHEMA=lautowork_n8n` | Fixed (retired `_prod` suffix removed) |
| Pinned n8n image `2.30.0` (not `:latest`) | Done |
| Separate-repo fork model (`link-n8n` submodule) | Documented; stock image for MVO |
| Kill-switch + lifecycle persisted to DB + hydrate on boot | Done (8A) |
| LiNKaios / dead Program shells removed from live set | Archived |
| Secrets contract = GSM `*_SECRET_NAME` only in `.env.example` | Cleaned |
| `N8N_PUBLIC_API_DISABLED=false` | Intentional (import + global kill-switch); Tailscale-bind required |
| Integration branch includes this work | Merged to `development` / `staging` / `main` |

## Operator steps on a new VPS

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

## Still an ops input (not a code hole)

- Choosing / provisioning the VPS
- Filling real GSM secret values and Traefik hostnames
- Slack channel wiring (optional for first smoke)

## Release checklist

Use `docs/RELEASE_GATE_CHECKLIST.md` during the first live bring-up.
