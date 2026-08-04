# Automation intake and Automation Architect runbook

## Purpose

This runbook governs conversion of external automation material into a **candidate-only** LiNKautowork Golden Automation Package (GAP). It supports create, adapt, compose, and refine work. It does not authorize a live n8n import, deployment, credential write, certification, or production change.

## Intake process

1. Record the source locator, exact revision, kind, and SHA-256 of the exact quarantined file/archive. Never execute or import a received archive during intake.
2. Keep raw source material outside Git when it can contain credentials, customer data, or licence-restricted content. Commit only redacted metadata after the scanner passes.
3. Complete the v0.1 intake record and source-to-target map. Every source component is explicitly marked as **reused** (`reference_only`), **replaced** (`reimplemented`), or **rejected** (`not_used`). Each mapping includes the exact source digest, target reference, and reason. A source component cannot be silently omitted.
4. Record the source licence and commercial-use decision. Unknown or restricted licence is a hard stop. Every contributing source of a commercial-capable candidate requires cleared commercial use.
5. Run the deterministic secret/customer-data scan. Do not copy detected values into tickets, reports, logs, fixtures, or commits. A finding is a hard stop until the source is safely re-obtained or fully redacted outside the candidate process.
6. Write the target brief: expected output, input/configuration boundaries, side effects, exclusions, n8n capabilities, GSM secret-reference design, and evidence references. Missing expected output, unsupported side effect, or unavailable capability is a hard stop.
7. Submit only a strict machine-readable Architect request. Unknown fields, malformed IDs/versions, invalid output field names, and malformed validator reports stop the request; natural-language instructions cannot bypass this boundary. Its workflow is recreated as an inactive candidate scaffold whose mode is visible in its workflow, redacted evaluation fixture, and suite; source nodes, credentials, and customer records are not copied automatically.
8. Run WP-02 package validation and WP-06 evaluation when their command adapters are available. A missing runner is reported as unavailable, never as passing evidence.
9. Open a branch/PR with the candidate report, source map, provenance, digest, validation/eval evidence, and explicit stop conditions. The only valid Architect output status is `candidate`.
10. Route candidate promotion through independent evaluation, Librarian review, risk-based approval, canary, and controlled rollout. The Architect cannot certify or deploy its own candidate.

## Required stops

- Unknown or restricted licence.
- Embedded credential, private key, connection string, access token, or customer data.
- Missing expected output.
- Unsupported side effect or unavailable n8n runtime capability.
- Direct request to edit production or label a candidate certified/deployed.
- A synchronous-response result requested without a webhook trigger; this combination cannot be represented safely in n8n.
- Adapt/refine with anything other than exactly one approved source; compose with fewer than two.
- Refine without redacted evaluation, incident, telemetry, API-change, or approved-requirement evidence.

## Resumption

Persist the machine-readable Architect report and use its deterministic `resumeKey`. Re-run from the same request only after the recorded stop condition is resolved. Never resume by bypassing an earlier stop or by copying the old source into a live workflow.
