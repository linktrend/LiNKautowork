# LiNKautowork Connection Health 1.0.0

This draft is a read-only service-to-n8n dispatch canary. Its only success claim is that the fixed provider webhook returned the exact request ID, request fingerprint, package identity, and n8n execution ID. It does not inspect repositories, consumers, business state, or deployment health.

The workflow remains inactive in source. Before any separately approved import, an operator must bind the n8n Header Auth credential for the fixed `x-link-connection-health-token` header. The package contains no credential reference or secret value. Gateway-side token configuration uses `LINKAUTOWORK_CONNECTION_HEALTH_WEBHOOK_TOKEN_SECRET_NAME`; its default is empty, so the canary stays disabled until an owner supplies an approved Secret Manager reference. The current source change does not import or activate this workflow.

A request transitions durably from `accepted` to `running` using the accepted version. Only the CAS winner may call the fixed webhook. Replays and CAS losses do not dispatch. A timeout or malformed response leaves the request `running`; callers must use status and manual reconciliation. An `accepted` request with no transition means dispatch was never started and also requires manual recovery. The gateway never retries an ambiguous dispatch automatically.
