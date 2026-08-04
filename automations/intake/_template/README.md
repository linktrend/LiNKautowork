# Quarantined automation intake template

Use this folder shape for a source submitted to the Automation Architect. It is quarantine only: never import it into n8n, copy it to `automations/templates`, or place raw credentials/customer data in Git.

1. Keep the raw artefact outside the repository or in an approved encrypted evidence store.
2. Create a metadata-only intake record from `automations/schemas/automation-intake-v0.1.schema.json`.
3. Hash the exact source file/archive before assessment.
4. Record provenance, licence state, and source-to-target mapping.
5. Stop on unknown/restricted licence, secret-shaped content, customer data, unsupported effects, or missing output requirements.

Only redacted metadata and the final candidate report may enter the repository.
