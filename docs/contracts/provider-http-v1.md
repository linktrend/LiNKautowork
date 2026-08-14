# Provider HTTP v1

All `/v1/provider/*` routes require the existing internal service token and a
valid Platform invocation claim. The claim-derived organization is authoritative;
an invocation whose embedded Platform organization differs fails closed. Discovery
returns compact catalogue summaries; exact detail, status, receipt and cursor data
are requested individually. The source-local route service uses the AW-01 schemas
and CR-01 persistence boundary only. It cannot activate external assistance: that
capability remains `hold` until exact Brain handoff delivery and a supported provider
activation interface are separately configured and proven.

The current `ide-repository-status@1.0.0` source candidate is a read-only
canary definition. Its definition and configuration digests are derived from
the canonical content in `gateway/src/services/provider-route-service.ts`; an
unknown version, a changed digest, and `latest` all fail closed.

Responses contain only bounded metadata and opaque evidence references. They never
prove a consumer Issue, Ledger, Gate, branch, PR, deployment, approval, publication,
or external side effect. MCP and OKF do not apply to this operational HTTP surface.
