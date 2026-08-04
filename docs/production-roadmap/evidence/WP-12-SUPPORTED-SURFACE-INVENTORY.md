# WP-12 supported-surface inventory

Generated/reviewed from repository source at release time. This is a support inventory, not a claim that external targets exist.

| Kind | Supported surface | Owner | Verification |
| --- | --- | --- | --- |
| Service | Gateway (`gateway/`, port 8080 private) | Platform | gateway Vitest, `/health` |
| Service | stock n8n `n8nio/n8n:2.30.0` | Operations | exact-reference Compose health and disposable eval |
| Service | NATS JetStream `nats:2.10.26-alpine` | Platform | compose health, event-bridge tests |
| Product | typed product API (`apps/product-api`) | Product API | package tests/typecheck |
| Product | private operator console (`apps/operator-console`) | Operations | package tests/build/typecheck |
| Product | client product surface (`apps/web`) | Client product | package tests/build/typecheck |
| Routes | gateway `/health`, `/metrics`, signed ingress, control, callback, instance, librarian and operations routes | Gateway | `gateway/tests/*` |
| Routes | product public reads, authenticated client actions, operator mutations, signed provider webhook | Product API | `apps/product-api/tests/app.test.ts` |
| Jobs | migration verify/restore rehearsal, evaluator smoke/full, template/package validation | Release engineering | root CI scripts |
| Schema | `lautowork`, `lautowork_n8n`, `platform` contracts | Data owner | disposable DB verification; live apply blocked |
| Package | automation contracts, architect, operations, eval runner, librarian | Respective packet owners | package test/typecheck scripts |
| Workflow | four governance templates in `automations/templates/manifest.json` | Automation operations | template validator and n8n import/export after approval |
| Secret names | `*_SECRET_NAME` keys in `deploy/{dev,prod}/.env.example` | GSM owner | env contract; live access blocked |
| Integrations | Supabase, GSM, NATS, n8n; optional Slack; platform JWT/JWKS; payment | Platform/Principal | local fakes only unless separately approved |
| Deployment | Compose, gateway Dockerfile, Traefik/Tailscale templates, ops scripts | Release engineering | `release:check`, compose config after inputs |

## Explicitly unsupported

- A retired historical automation runtime, its invoke URLs, its scaffold generators, and its cross-repository template sync scripts are absent from supported source. Historical evidence remains only under clearly labelled archive directories.
- Direct public n8n, NATS, database, GSM, and operator-console exposure is unsupported.
- No customer payment, credentials intake, live identity issuer, stage/prod migration, or public product API deployment is authorised by this inventory.

## Discovery command

Run `npm run release:check`, then use `rg --files gateway apps packages automations deploy ops scripts supabase .github` to regenerate the file list before any release candidate. The command fails if a retired runtime marker returns to a supported root.
