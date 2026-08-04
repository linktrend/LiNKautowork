# WP-10 — Internal Operator Console evidence

## Delivered boundary

`apps/operator-console` is a deployable, non-root private web application. It receives an externally issued LiNKplatform bearer session, calls only the finite WP-09 operator routes, and has no built-in operator identity, fixture actor, generic table proxy, n8n access, or credential input. Its screens cover overview, catalogue, instances, provisioning, executions, incidents, releases, Librarian candidates, and audit/health.

The console renders API success, denial, unavailable, redacted, and correlation states. Typed resource-specific actions require a reason, explicit confirmation, and the correct role. Promotion remains disabled for an operator without the separate approver role. Secret-, token-, authorization-, and workflow-shaped fields are replaced with `[redacted]` before display.

## Executable proof

- Package tests: 3 passed for finite route construction, role/action separation, confirmation, error states, and redaction.
- Strict typecheck and production build passed; output is isolated under ignored `dist/` and no JavaScript is emitted beside TypeScript source/tests.
- The canonical real-Chrome journey starts an isolated disposable Postgres/PostgREST project, serves the compiled console, and uses the concrete `PostgrestProductApiService`.
- A client-member session received a real 403 and no operator action controls.
- An operator loaded a durable incident, saw only `[redacted]`, submitted a reasoned acknowledgement through the real Product API, received HTTP 200/a visible receipt, and the database recorded the state transition.
- A non-approver operator saw release promotion disabled while provisioning remained a separate operational area.
- Semantic headings, landmarks, labelled controls, native dialog behavior, visible status text, keyboard-operable controls, and responsive layout assertions ran in the browser.

The production image builds from pinned `node:22.13.1-alpine`, runs as a non-root user, and exposes `/healthz`. The production Compose service has no public port or inline Traefik route.

## Live boundary

This proves the application and local durable integration. It does not prove the live platform issuer/JWKS/session service, approved DNS/Tailscale route, production PostgREST project, GSM values, or a deployed operator URL.
