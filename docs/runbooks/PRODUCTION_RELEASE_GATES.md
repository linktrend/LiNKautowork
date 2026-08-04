# LiNKautowork Production Release Gates

The following gates are mandatory before production promotion.

## 1. Security gate
- Fresh clean-checkout evidence is green (`npm run release:check`, `npm run ci`, env contract, secret scan, dependency scan).
- No raw secrets in committed env files.
- GSM secret references validated (`ops/render-env-from-gsm.sh prod`).
- Runtime env rendered from GSM to runtime path outside repo (`ops/render-runtime-env-from-gsm.sh prod --output /opt/linktrend/runtime/linkautowork/prod.env.runtime`).
- Stack started via `ops/deploy-stack.sh prod --build`.
- Tailscale-only firewall policy installed for protected ports (`5678`, `8080`, `4222`, `8222`).

## 2. Lifecycle gate
- Template lifecycle approvals completed (`qa_approved` and `ops_approved`).
- Required templates imported to n8n production and activated.
- Live export evidence captured (`ops/export-live-from-n8n.sh prod`).

## 3. Safety gate
- Kill-switch endpoints validated (scoped + global).
- Backup and restore drill validated (`ops/run-backup.sh`, `ops/restore-drill.sh`).
- Incident/audit lineage confirmed in Supabase `audit_runs`.

## 4. Governance gate
- Protected actions route via Principal approval protocol.
- Slack ops/approval channels are configured and tested.

Promotion is blocked until all gates are checked, the VPS Deployment Input Register is complete, the release manifest records the exact image/package hashes and rollback target, and independent audit returns `PASS_PRE_VPS`.
