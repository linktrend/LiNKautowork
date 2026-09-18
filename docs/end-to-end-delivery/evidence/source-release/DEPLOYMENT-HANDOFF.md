# Deployment handoff (source candidate → AW-08)

This is a source receipt, not a live install grant.

## Candidate to install later

- Repository: `linktrend/LiNKautowork`
- Work branch: `issue/165-prepare-linkautowork-1-0-release-candidate-and-d`
- Starting commit/tree for this packet:
  `20f3d4cc03445ca443e31c41f22d34347c866acf` /
  `95bec98a0d65ca30889e595a7bcaa85ddfe52b47`
- Hosted CI on that SHA: https://github.com/linktrend/LiNKautowork/actions/runs/34955615212 (`success`)
- Compose: `deploy/prod/docker-compose.yml` project `linkautowork-prod`
- Names-only env: `deploy/prod/.env.example`
- Migration package: `docs/contracts/server01/MIGRATION-PACKAGE.json`
- Private routes: `deploy/templates/traefik-dynamic.yml.example`,
  `deploy/templates/tailscale-boundary.env.example`

## AW-08 must still do (all HOLD here)

1. Record host image IDs/digests into `deploy/prod/release-identity.json`.
2. Render runtime env from GSM to mode-`0600` files outside git.
3. Platform-apply the ordered SQL package and persist
   `lautowork.server01_live_fingerprint()`.
4. Create least-privilege DB grants for the named `svc_lautowork_*` roles.
5. Install inactive stack under `/srv/linktrend/deploy/linkautowork`.
6. Import the technical fixture inactive; activate one canary only with
   explicit founder/Platform authority.
7. Run `ops/verify-server01-acceptance.sh --environment prod` on the host.
8. Prove backup/isolated restore and application rollback to `previous`.

## Explicitly not authorised by this packet

Live Server01, Platform, provider, credential, database, Docker, protected-branch,
or production actions. Public DNS/TLS, Slack/email, payments, and Program
business automations remain later expansion unless separately approved.
