# WP-11 — Client Product evidence

## Delivered boundary

`apps/web` is a deployable public site and authenticated client portal. It exposes only explicitly published managed-automation offers, then uses the finite WP-09 lifecycle routes. It has no catalogue search, arbitrary automation invocation, n8n/editor link, workflow JSON, credential field, payment instrument, provider selection, operator/Librarian control, or caller-supplied organisation authority.

The durable local commercial model records the required state vocabulary and transition history: `initiated`, `awaiting_payment`, `payment_not_required`, `paid`, `awaiting_configuration`, `provisioning`, `active`, `suspended`, `cancel_requested`, `cancelled`, and `failed`. The no-payment-required browser path records versioned terms, advances to `awaiting_configuration`, then permits subscription creation. Subscription and WP-05 provisioning reject missing terms, a wrong commercial state, a wrong organisation, or an unapproved target. Provider-event replay, sequence ordering, invalid transitions, and prior-state history are covered in disposable database tests. Payment remains a fake/local adapter; no provider or charge exists.

## One integrated local journey

`npm run test:browser` now:

1. creates an isolated, loopback-only disposable Postgres/PostgREST project;
2. applies all governed migrations through `20260804_000012` and seeds two organisations, one published offering, approved release/instance binding, and operator incident;
3. serves the compiled client and operator applications;
4. constructs the real `PostgrestProductApiService` and `PostgrestProvisioningAdapter`;
5. drives system Chrome through published offer → durable order → terms acceptance → eligible subscription → accepted WP-05 provisioning request;
6. verifies organisation/role denial, idempotent state, incident acknowledgement, redaction, promotion separation, 390-pixel responsive rendering, and accessibility markers; and
7. removes the disposable containers, network, volumes, browser contexts, and local servers.

The canonical database verifier separately proves replay, restart-safe one-instance provisioning, cross-organisation denial, failure/compensation truth, provider event ordering, restore, and rollback. Package tests (10), strict typecheck, production build, and the portable Playwright harness all pass.

## Live boundary

The repository contains a value-free public runtime API configuration and externally supplied bearer-session boundary. Live identity, payment provider/account/legal pricing, secure GSM credential onboarding, Supabase Cloud application, DNS/TLS, customer records, and VPS deployment remain separately authorised inputs. Credential onboarding is honestly operator-assisted until that live process is approved.
