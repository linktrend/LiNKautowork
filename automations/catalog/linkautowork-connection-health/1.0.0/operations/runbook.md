# Connection health canary runbook

1. Confirm the exact draft package digests and inactive workflow.
2. Bind the owner-issued Header Auth credential to `x-link-connection-health-token` during a separately approved import.
3. Configure the dedicated gateway secret reference outside the package.
4. Submit only `status_collection` or `precheck` under the exact read-only policy profile.
5. Read the provider status and receipt. A `running` state without a receipt is ambiguous and requires manual reconciliation; do not replay to trigger another call.
6. If dispatch or a replay returns HTTP 503 with `recovery_required`, retain the request ID and use the returned recovery reference. Read status/events and reconcile manually; do not resubmit or dispatch it again. An accepted request whose claim could not be safely terminalized remains durable for operator recovery. A confirmed failed claim is terminalized as `unavailable` with a receipt error code `dispatch_claim_failed`; no webhook call was made.

This canary does not establish repository, consumer, service-wide, or production health.
