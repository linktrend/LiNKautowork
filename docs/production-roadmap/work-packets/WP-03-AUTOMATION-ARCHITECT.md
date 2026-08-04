# WP-03 — Automation Architect and Source Intake

## Objective

Implement an AI-facing, deterministic-support workflow for creating, adapting, composing, and refining candidate automation packages without granting production mutation or self-certification authority.

## Dependencies

WP-01 contract. Final verification consumes WP-02 commands.

## Owned paths

- `agents/automation-architect/**`
- `packages/automation-architect/**`
- `automations/intake/_template/**`
- `automations/fixtures/intake/**`
- `docs/runbooks/AUTOMATION-INTAKE.md`

Do not edit production workflows, deploy n8n, access live credentials, or implement Librarian hosting.

## Modes

- `create`: new package from an approved brief.
- `adapt`: convert one Make/Zapier/GitHub/n8n/documented source into n8n and the Golden format.
- `compose`: combine approved portions of multiple sources.
- `refine`: create a new version from eval, incident, telemetry, API-change, or approved requirement evidence.

## Required implementation

1. Define a machine-readable Architect request and report schema with task ID, mode, target ID/version, approved sources, requirements, exclusions, runtime, and evidence references.
2. Implement source intake states: submitted, quarantined, assessed, accepted/rejected, mapped, archived.
3. Implement deterministic intake helpers for file/archive hashing, secret scanning, metadata extraction, licence-state capture, and source-to-target mapping.
4. Require the Architect to record reused, replaced, and rejected behaviors from every source.
5. Require credentials/customer data removal and GSM-reference design before candidate generation.
6. Scaffold a candidate package from WP-01 without copying source secrets or unsupported nodes.
7. Compose mode must retain individual provenance and licensing restrictions for every contributing source.
8. Refine mode consumes redacted evidence and produces a version diff plus regression eval additions.
9. Run WP-02 validation and later WP-06 eval commands; never forge receipts when a runner is unavailable.
10. Produce a branch/PR-ready candidate report. The output status is `candidate`, never `certified` or `deployed`.
11. Encode stop conditions for unknown licence, embedded secret, missing expected output, unsupported side effect, unavailable runtime capability, or request to mutate production directly.

## Test matrix

- Create from valid brief.
- Adapt sanitized n8n source.
- Adapt Make/Zapier-shaped source descriptor into a mapped candidate.
- Compose two compatible sources and preserve both attributions.
- Reject unknown commercial licence.
- Reject embedded credential/customer data.
- Refine from a failure and add a regression case.
- Reject direct-production/self-certification request.
- Resume safely from persisted candidate state.

## Acceptance criteria

- All four modes produce deterministic machine-readable reports and valid candidate layouts.
- No mode can change a live n8n workflow, credential, deployment pointer, or certification row.
- Licence/provenance and source-map omissions are hard stops.
- Validation failures remain failures in the report.
- Exports and public functions have JSDoc and tests.

## Audit focus

The Wave 1 auditor must confirm that natural-language prompts cannot bypass deterministic stop conditions or label output certified.
