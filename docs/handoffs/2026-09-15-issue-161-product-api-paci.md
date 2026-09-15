# Issue 161 Product API PACI checkpoint

Issue 161 starts from protected parent `fbf3f3965de52a57364e68af3e1ccbdead3a2b2a`
and tree `4b30d090165c7a65b312d2cd07a01545255e70f1`. This is a source checkpoint only;
it does not claim protected integration, independent review, deployment, or live
acceptance.

The Product API production verifier now accepts only the canonical Platform PACI
ES256 `paci+jwt` envelope through `jose` for an exact root issuer,
`linkautowork-product-api` audience,
configured organisation, service `autowork`, and operation `read`. It verifies
the exact nested claim binding, a bounded same-origin JWKS key, and an uncached
RFC 7662 response authenticated with endpoint-bound `private_key_jwt`. The client
private key is referenced by a pinned numeric GSM SecretVersion and resolved only
inside the Product API ADC boundary.

PACI authorizes only organisation-scoped client GET routes. It is never converted
to a browser, operator, or approver role, so mutation and operator-wide routes
remain denied. The existing HS256 role fixture remains confined to `NODE_ENV=test`.
RS256 and `PRODUCT_API_SESSION_URL` have been removed from the production contract.

Focused Product API typecheck and all 39 Product API tests pass. The 14-test
deployment-readiness suite, release-readiness check, Compose YAML parse, and
`git diff --check` pass using an existing repository dependency installation.
The legacy and managed fixture-aware secret scans pass after the official
candidate-bound fixture refresh. No dependency was installed and Docker was not
run.

Live use remains blocked on Platform admitting an exact Product API introspection
ACL. Platform Issue 282 currently denies introspection for that client, while the
inspected Issue 290 ref is still identical to current protected development and
contains no successor grant. The coordinator owns independent exact-candidate
review and completion-gate review-ready processing after this checkpoint.
