# WP-05 — Instance Lifecycle, n8n Provisioner, and Linked Invocation

## Objective

Replace caller-selected workflow routing with explicit organisation-scoped instance bindings; implement safe workflow-copy provisioning and versioned execution receipts against the shared managed n8n runtime.

## Dependencies

Wave 1 PASS, especially catalogue, contracts, and data model.

## Owned paths

- `gateway/src/services/instances/**`
- `gateway/src/services/provisioning/**`
- `gateway/src/contracts/automation-*.ts`
- `gateway/src/integrations/n8n-client.ts`
- Relevant gateway routes and tests
- Provisioning runbook

## Required behavior

1. Add a versioned execute route addressing a known instance/binding. Resolve workflow ID/path, criticality, secret references, timeout, retry, and schemas server-side.
2. Authenticate caller identity/organisation/operation through the Platform-compatible claim adapter and service binding; retain existing internal signed ingress only as an explicit compatibility path.
3. Reject wrong org, wrong service/system, unbound operation, disabled instance, uncertified/deprecated release, drifted deployment, invalid input, kill switch, or duplicate non-idempotent request before n8n dispatch.
4. Implement n8n create/update-copy/get/activate/deactivate APIs needed for controlled provisioning. Never expose n8n API credentials to callers.
5. Provision one unique n8n workflow copy per instance with unique deployment record, configuration digest, webhook/schedule mapping, and secret bindings.
6. Do not send high-sensitivity raw secrets as ordinary n8n execution input. Define brokered connector or native per-instance credential path; store references only.
7. Run pre-activation smoke eval, persist deployment receipt, then activate. Failure leaves inactive state and executes compensation.
8. Make provisioning durable/idempotent with locks, retry states, receipts, and safe replay.
9. Return an accepted execution receipt and later completion correlation; do not report dispatch acceptance as completed business work.
10. Detect source/deployed workflow digest drift.

## Test matrix

- Two organisations with same definition but different instances/credentials.
- Correct bound invocation.
- Cross-org and cross-system denial.
- Caller attempts arbitrary workflow path/criticality/secret name.
- Duplicate idempotency request.
- n8n import failure, activation failure, smoke failure, compensation, and replay.
- Drift detection and inactive/deprecated release rejection.
- Scoped/global kill-switch behavior.
- Secret redaction across logs, receipts, and errors.

## Acceptance criteria

- No v2 caller controls raw workflow routing or required secret names.
- Provisioned instances are distinct and org-scoped.
- Activation requires certified hash-matching release and smoke receipt.
- Compatibility routes are documented, bounded, and scheduled for retirement.
- Full gateway unit/integration suite passes.
