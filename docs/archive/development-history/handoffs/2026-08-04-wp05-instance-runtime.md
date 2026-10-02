# WP-05 handoff — instance runtime

Implemented the v2 org-scoped bound-instance execution path and controlled n8n copy-provisioning primitives.

- V2 execution accepts only input plus an idempotency key; it derives binding, deployment, workflow controls, and secret references from durable control records.
- It fails closed for missing/wrong bindings, instance/release state, digest drift, kill switches, and dispatch failure. It returns acceptance/correlation, not completion.
- Provisioning creates an inactive per-instance workflow copy, smoke-tests before activation, and compensates on failure. The service provides lock/state/replay seams for durable storage.
- Legacy `/v1/ingress/:workflowId` remains the documented compatibility surface; v2 is the supported model.

Validation: WP-05 tests and `npm run typecheck` pass. Root CI currently stops on the automation-catalog Golden Automation Package `package_digest_mismatch` (outside WP-05 ownership).
