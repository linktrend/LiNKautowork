# ADR 0002: Golden Automation Package source authority and manifest cutover

- **Status:** Accepted for implementation; no live-template conversion has occurred.
- **Date:** 2026-08-04
- **Decision owner:** LiNKautowork
- **Related:** `docs/specs/GOLDEN-AUTOMATION-PACKAGE-v0.1.md`, WP-01

## Context

The current `automations/templates/manifest.json` and top-level workflow JSON files are a governance-only compatibility inventory. They are adequate for the original MVO, but they do not record the complete release contract needed for reusable internal automations and client-specific hosted instances: versioned contracts, provenance, executable evaluation, monitoring, deployment policy, and configuration boundaries.

Keeping a workflow editable in both a top-level template file and a package would make it unclear which source is authoritative. An n8n UI export is evidence, never a second editable source.

## Decision

For every converted automation release, its Golden Automation Package is the only editable source authority. The package's `workflow.json` is the workflow source imported to n8n. The generated operator catalogue is a read model, and an n8n export is operational evidence only.

The legacy manifest remains a compatibility surface only while the five current workflows are being converted. It must not be expanded with new product automations after the package validator exists.

## Cutover rules for one workflow

1. Inventory the current workflow hash, manifest record, lifecycle status, and import behaviour.
2. Create a candidate GAP containing a byte-preserved workflow copy unless an explicitly approved functional change is separate.
3. Validate package structure, safety, provenance, and all referenced contracts.
4. Run the required executable evaluation and record a release-bound receipt.
5. Obtain independent certification/promotion approval appropriate to the risk.
6. Update the importer so it imports the package workflow, then record the old-to-new source mapping.
7. Remove the workflow from the legacy manifest in the same atomic source-authority change, or mark the legacy entry as generated compatibility metadata that cannot be edited independently.
8. Verify that exactly one editable source remains. The generated catalogue and n8n export must point to the package digest.

The old manifest cannot point to a different editable JSON copy after cutover.

## Rollback rules

Rollback changes the active runtime pointer to the prior certified package release or restores the documented legacy manifest state if the cutover itself is being rolled back. It does not edit a deployed workflow in place.

If cutover fails before import, retain the legacy authority untouched and discard the unapproved candidate. If it fails after import but before activation, deactivate/delete only the newly imported inactive candidate workflow and retain the legacy version. If it fails after activation, use the recorded deployment receipt to restore the prior known-good release, preserve audit evidence, and open a maintenance issue.

No rollback may make both legacy and package paths independently editable.

## Consequences

- WP-02 must implement deterministic package validation and a catalogue index before a broad migration.
- Existing `scripts/validate-templates.mjs` remains active until all live templates are converted deliberately.
- Import/export scripts, runtime binding, and database registry changes are later owned work; this ADR does not modify them.
