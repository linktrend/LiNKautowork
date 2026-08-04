# C-W3-01 — Disposable evaluator cleanup correction

## Defect and correction

The real Docker smoke evaluator could complete its disposable n8n run and then fail during final cleanup when Docker reported that the named disposable volume was already absent. `DockerN8nRuntime` now treats only Docker's explicit missing-resource response as successful volume cleanup. Its normal `--rm` containers remain ephemeral; the cleanup helper also recognises the equivalent missing-container response if a named container cleanup is added later.

Cleanup is now settled once per primary runtime. Repeated `stop()` calls do not issue a second Docker removal. The restore-volume finalizer uses the same missing-resource handling. Any other Docker cleanup error still fails the evaluation; if an evaluation and cleanup both fail, both errors are retained in an `AggregateError` rather than masking the evaluation fault.

## Regression proof

The evaluator unit suite covers an absent volume, repeated `stop()`, and an unexpected cleanup error with an exact single cleanup invocation by `runEvaluation`. The smoke and full profiles execute the pinned, disposable `n8nio/n8n:2.30.0` container and restore rehearsal locally. This correction does not use or modify a VPS, DNS, credentials, databases, payments, or a production n8n instance.
