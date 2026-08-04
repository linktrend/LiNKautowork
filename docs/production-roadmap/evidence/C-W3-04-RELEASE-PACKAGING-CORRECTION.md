# C-W3-04 — release packaging and legacy retirement correction

**Scope:** Wave 3 independent-audit corrections for release topology, retired compatibility surfaces, disposable evaluator recovery, and pre-VPS validation. No VPS, DNS, TLS, GSM, database, payment, customer, n8n, or external service was changed.

## Corrected supported topology

- Production Compose now declares persistent NATS JetStream (`nats_jetstream_prod`), gateway, private n8n, Product API, public client site, private operator console, a migration checksum/preflight job, a certified-package publication preflight job, and an authenticated operations scheduler profile.
- Gateway, n8n, NATS, and the operator console have no host port or inline Traefik router. The supplied Traefik template is the only ingress definition: public client/API routes are separate from Tailscale-only n8n/operator routes.
- The Google service account is an externally created Docker secret mounted at `/run/secrets/gcp-service-account`; source-machine paths are not embedded in the production manifest. Actual secret creation, real values, and permission validation remain deployment-authorisation work.
- Runtime base images are pinned to Node `22.13.1-alpine`; n8n and NATS are explicitly versioned. The deployer must record the resolved platform digest for every built/local candidate image in the release manifest before promotion. A local Compose build proves reproducibility, not a published image digest.

## Retired surfaces

- The deprecated daily briefing was removed from the live template manifest and top-level source directory.
- Four live governance templates remain. Direct n8n webhook triggers and the historical event namespace have been removed from the live set. Governed template dispatch is through the gateway-controlled runtime path; live n8n template imports remain inactive until separately authorised.
- The gateway now publishes only `linkautowork.v1.*` events. The old compatibility switch, parallel subjects, legacy template wording, and obsolete Wave 4 runbook were retired.
- Historical JSON stays beneath `automations/templates/archive/` only. Its README now states it must never be imported, activated, published, or treated as a production source.

## Crash-orphan containment

The disposable evaluator labels both primary and restore Docker volumes `com.linktrend.linkautowork.disposable-eval=true`. `ops/reconcile-disposable-eval-resources.sh` filters exclusively on that exact label and never invokes broad `docker system prune` or volume pruning. The regression test proves both volume creations have the label and the runtime command sequence has no broad-prune operation.

## Local evidence

Executed on the uncommitted Wave 3 candidate worktree on 2026-08-04:

```text
npm --prefix packages/automation-eval-runner run test                 PASS (8)
docker compose -f deploy/prod/docker-compose.yml --env-file deploy/prod/.env.example build product-api client-web operator-console migration-preflight certified-package-publisher   PASS
local `prod-client-web` and `prod-operator-console` `/healthz` container probes  PASS
npm run release:check                                                PASS
ops/validate-env-contract.sh                                         PASS
docker compose ... config                                            PASS (expected blank secret-value warnings only)
npm run validate:templates                                           PASS (4 manifest entries)
npm run typecheck -- --pretty false                                  PASS
npm test -- --run gateway/tests/event-bridge.test.ts                 PASS (2)
git diff --check                                                     PASS
```

The completed container build is structural pre-VPS proof only. It does not prove live authentication/session validation, a real PostgREST backing store, TLS/DNS routing, Docker-secret provisioning, outbound egress policy, scheduler credentials, actual n8n import, migration apply, payment, or alert delivery.

## Remaining authorised deployment inputs

Before a real deployment, the Principal must approve the VPS/network boundary, external Docker secret creation from GSM, the live Product API Platform issuer/JWKS/session/PostgREST values, public/private DNS and Traefik/TLS routes, migration command, scheduler identity, backup target, monitoring/alert destinations, and the immutable image digests to record in the candidate manifest.
