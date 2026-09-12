# Operations Runbook (MVO) — source topology (AW-05)

Owner: LiNKtrend Platform  
Last updated: 2026-09-12

This runbook describes the **source-only** Server01 production Compose contract.
It does not authorise SSH, Tailscale mutation, GSM resolve, registry pull,
provider dispatch, or a live Server01 install. Those remain **HOLD** for AW-08
after Phase Packager integration and Platform receipts.

## Settled initial-release topology

Services started in the default production project:

- `nats` on `autowork-events` with volume `nats_jetstream_prod` (no host port)
- `gateway` on `autowork-edge`, `autowork-runtime`, and `autowork-events`
- `n8n` on `autowork-runtime` only (private operator route via Traefik template)
- `product-api` (`PRODUCT_API_PORT=8080`, unpublished) and `operator-console` on `autowork-edge` (private)
- `operations-scheduler` behind `--profile operations` on `autowork-events`

Release jobs (`migration-preflight`, `certified-package-publisher`) stay on
`--profile release-jobs`. Migration mode is `dry-run` and refuses SQL apply.
`client-web` is `--profile retained-images` only: it may be built and kept with
the release; it is **not** an initial-release route.

The runtime dispatcher is an **in-process gateway module** (AW-01/AW-03). It is
not a Compose service or image.

AW-01 database role names in `deploy/prod/.env.example` are placeholders.
Platform owns live grants. Broad `service_role` is not a production runtime
identity.

## Names-only configuration (disposable / local)

1. Validate GSM **names**: `ops/render-env-from-gsm.sh prod --placeholders`
2. Render a mode-`0600` placeholder runtime file **outside git**:
   `ops/render-runtime-env-from-gsm.sh prod --placeholders --output /tmp/linkautowork-runtime-aw05/prod.env.runtime`
3. Render Compose without starting anything:
   `docker compose -f deploy/prod/docker-compose.yml --env-file deploy/prod/.env.example config`
4. Source-only stack helper: `ops/deploy-stack.sh prod --dry-run --print-release-layout`
5. Acceptance verifier (read-only): `ops/verify-server01-acceptance.sh --environment prod`
6. Source topology suite (Vitest): `npx vitest run scripts/tests/deployment-readiness.test.mjs`

Do not pass `--up`, `--live`, or `--resolve-gsm`. Those helpers print HOLD and
exit 2 without applying anything.

Do not pass a canary id. If `--canary <id>` is supplied to the acceptance
verifier, it still stays read-only: it prints a HOLD row, mutates no n8n
binding, and exits 0 (`PASS with N HOLD row(s)`). Live canary activation remains
AW-08.

## Atomic release pointer (not applied in this packet)

Intended host layout after AW-08 authority:

- `/srv/linktrend/deploy/linkautowork/releases/<commit>`
- `/srv/linktrend/deploy/linkautowork/current` → that release
- `/srv/linktrend/deploy/linkautowork/previous` retained until final acceptance
- `/srv/linktrend/runtime/linkautowork/*.env.runtime` mode `0600`

Rollback retargets `current` to `previous` and starts that Compose definition.
Database recovery is Platform-owned; this packet never applies SQL down.

## Promote / live start

**HOLD.** Do not run `docker compose up` against Server01 from this packet.
Do not import or activate n8n packages. Do not create public DNS/TLS routes.

When AW-08 is authorised, the deployer records image IDs into
`deploy/prod/release-identity.json`, switches `current` atomically, and starts
only private routes from `deploy/templates/`.

## Kill Switch

- Scoped: call `/v1/control/killswitch/scoped` with `action=activate`.
- Global: call `/v1/control/killswitch/global` with `action=activate`.
- Live invocation of these endpoints on Server01 is HOLD until AW-08.

## Backup and Restore Drill

- Backup: `ops/run-backup.sh` (AW-06/AW-08)
- Drill: `ops/restore-drill.sh <db-backup.sql.gz> <templates-backup.tar.gz>`
- Presence of live backup artifacts on Server01 is HOLD in AW-05.

## Security Verification

- Secret hygiene scan: `ops/security/scan-secrets.sh`
- Runtime env files with resolved secrets must stay outside git, mode `0600`.
- Protected ports `5678`, `8080`, `4222`, `8222` are unpublished on the host.

## Ingress

There is no approved live hostname, Tailscale Serve policy, or Traefik load in
this packet. Use placeholders in `deploy/templates/`. Keep `N8N_PORT=5678` as
the container listen port; TLS terminates only on an authorised reverse proxy
later. Public client-web routing is out of initial-release scope.
