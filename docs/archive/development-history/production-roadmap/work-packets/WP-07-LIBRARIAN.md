# WP-07 — Institutional Librarian: Automation Mode

## Objective

Add an automation-specific mode to the institutional Librarian. It consumes evaluation and production evidence, identifies a bounded improvement opportunity, and creates a reviewable candidate change. It must not edit, promote, or deploy a live workflow by itself.

## Plain-English outcome

The Librarian is the learning loop. It studies what happened, proposes a safer or better future version, and leaves evidence for independent review. The same institutional Librarian service may also support LiNKskills and LiNKbrain, but automation records, policies, queues, permissions, prompts, and decisions remain strictly separated.

## Dependencies

- WP-01 Golden Automation Package and role separation.
- WP-04 automation/version/evaluation records.
- WP-05 instance and deployment records.
- WP-06 evaluation receipts and production telemetry.

## Owned paths

- `packages/automation-librarian/**`
- `gateway/src/services/librarian/**`
- `gateway/src/contracts/librarian-*.ts`
- Automation-mode policy, prompts, fixtures, and tests

Do not modify LiNKskills or LiNKbrain repositories. If a shared institutional endpoint is unavailable, implement a tested LiNKautowork adapter and document the external contract; do not create a second institutional identity system.

## Inputs and outputs

Accepted inputs are immutable references to package versions, eval receipts, execution projections, incidents, maintenance results, operator feedback, and approved aggregate performance measures. Raw credentials and unrestricted client payloads are forbidden.

The output is an `automation_improvement_candidate` containing: source automation/version; evidence references; diagnosed failure or opportunity class; proposed change scope; changed package artifact or machine-readable patch; expected benefit; risk level; required eval suites; provenance; redaction record; and lifecycle status.

## Required implementation

1. Implement the automation-domain queue and adapter with explicit `domain=automation` routing. Reject skill/brain records and unknown domains.
2. Enforce organisation and visibility boundaries. Cross-client learning may use only explicitly approved, de-identified aggregate signals; raw client runs never become another client's candidate fixture.
3. Implement trigger policies for repeated deterministic failures, SLO regression, incident closure, dependency deprecation, operator feedback, and scheduled review. Noise and one-off transient failures must not generate uncontrolled candidate churn.
4. Implement bounded analysis and candidate creation. Every assertion must cite evidence. Unsupported conclusions are labelled uncertain.
5. Route proposed package changes through the same WP-02 validator and WP-06 eval runner as human-authored changes.
6. Enforce separation of duties: the actor that proposes a candidate cannot be its sole certifier, publisher, promoter, or production deployer.
7. Implement candidate states: `proposed`, `validation_failed`, `ready_for_eval`, `eval_failed`, `awaiting_review`, `approved`, `rejected`, `superseded`. Approval does not itself deploy.
8. Add deterministic deduplication so the same evidence does not create repeated candidates.
9. Persist model/provider/version, prompt/policy version, tool activity summary, evidence hashes, cost/usage metadata when available, and redaction result.
10. Add a kill switch and per-automation pause. When disabled, telemetry continues to be retained but no new AI candidate is generated.

## Prohibited shortcuts

- No silent mutation of a published package or n8n workflow.
- No direct use of production credentials by the Librarian.
- No shared mixed catalogue with LiNKskills or LiNKbrain.
- No automatic promotion based only on an AI score.
- No client-data training or reuse without an explicit future policy.

## Test matrix

- Correct automation evidence creates one candidate.
- Duplicate evidence returns the existing candidate.
- Skill/brain domain input is rejected.
- Cross-org raw evidence is rejected.
- Redacted aggregate evidence follows its policy.
- Failed validation/eval blocks review-ready status.
- Kill switch and per-automation pause prevent creation.
- Proposer cannot certify or deploy its own candidate.
- Missing/contradictory evidence produces uncertainty or no candidate.

## Acceptance criteria

- A failing local eval can produce a bounded candidate, which then passes through validation and evaluation without touching a published version.
- Domain and organisation isolation tests pass.
- A complete audit trail explains what evidence caused the proposal and who/what advanced every state.
- Disabling the Librarian has no effect on ordinary automation execution.

## Evidence required at handoff

Changed files, tests and results, one redacted candidate lifecycle example, separation-of-duty proof, kill-switch proof, known limitations, and rollback instructions.

## Stop conditions

Stop rather than inventing policy if institutional Librarian authentication, approved cross-system message format, or data-use rules are required but not documented. A local adapter and contract test may proceed; live cross-repository wiring may not.
