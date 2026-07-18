# Release Gate Checklist (LiNKautowork)

Use on first VPS bring-up (prefer stage / `deploy/dev` against `linkplatform-stage`).

- [ ] `npm run ci` green on the deploy SHA
- [ ] Env contract check passed (`ops/validate-env-contract.sh`)
- [ ] GSM secret names validated (`ops/render-env-from-gsm.sh <env>`)
- [ ] Runtime env rendered outside repo (`ops/render-runtime-env-from-gsm.sh`)
- [ ] Tailscale-only firewall for `5678`, `8080`, `4222`, `8222`
- [ ] Stack up: `ops/deploy-stack.sh <env> --build`
- [ ] Templates imported + activated (`ops/import-templates-to-n8n.sh`)
- [ ] Gateway `/health` OK; kill-switch snapshot present
- [ ] Kill-switch scoped activate → ingress 503 → release; row in `lautowork.killswitch_events`
- [ ] Representative audit row in `lautowork.audit_runs`
- [ ] Backup/restore drill evidence attached
- [ ] Deploy pinned to immutable tag/SHA (n8n `2.30.0` + git SHA)
