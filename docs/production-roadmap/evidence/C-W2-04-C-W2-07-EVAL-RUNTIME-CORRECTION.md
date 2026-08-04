# C-W2-04 / C-W2-07 — Real n8n evaluation and restore correction

## Corrected proof

- The evaluator now fails closed unless Docker can inspect and start `n8nio/n8n:2.30.0`, the process reports version `2.30.0`, and the exact package workflow imports successfully.
- Runtime evidence records the inspected image ID and repository digest, imported-workflow state, real CLI execution timestamps/status/final output, and a digest of that execution evidence.
- Package and workflow identities use the canonical WP-02 `calculatePackageDigest` and `calculateWorkflowDigest` functions and must equal the declared WP-01 identity before runtime starts.
- Every suite assertion has an executable evaluator. Unknown prose assertions fail; fixtures cannot provide a generic `passed` value.
- Receipts bind the canonical package/workflow/suite/fixture hashes and real runtime evidence, are authenticated with an injected verifier key, and are written immutably by the file-store adapter. Tampering fails verification.
- The disposable restore path exports n8n workflow state plus catalogue identity, signed eval envelope, and secret-free configuration metadata, imports the export into a fresh n8n volume, and re-executes it. WP-08 retains control-database restore ownership.

## Adversarial regression coverage

Tests reproduce and reject a fake image/version claim, canonical fixture/package digest drift, receipt tampering, and a forced failing case. Official root and GitHub CI smoke/full profiles invoke Docker; runtime/image unavailability or mismatch exits nonzero.

## Truthful boundary

The packaged pilot is intentionally side-effect-free. Its exact workflow is imported and executed by real n8n, and its output/privacy/safety assertions use that execution evidence. Validation, idempotency, binding, missing-secret, and fake-upstream classifications remain package-contract/preflight assertions over explicit synthetic fixtures; they are not proof of a live connector or client integration. No stage, production, client data, credentials, or live external service was used.
