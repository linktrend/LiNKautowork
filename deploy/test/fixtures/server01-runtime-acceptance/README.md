# Server01 runtime-acceptance mock

In-process mock of AW-02 admission and AW-03 callback/receipt behavior for AW-04.
It never starts Docker, never calls n8n, never reads credentials, and never
claims Server01, canary, certified release, or production.

```bash
node deploy/test/fixtures/server01-runtime-acceptance/mock-n8n.mjs --self-test
node --test deploy/test/fixtures/server01-runtime-acceptance/mock-runtime.test.mjs
node scripts/run-automation-evals.mjs --profile=smoke
```

Optional HTTP listener (loopback only):

```bash
node deploy/test/fixtures/server01-runtime-acceptance/mock-n8n.mjs
```

Default bind is `127.0.0.1:18081`. The process refuses secret-shaped headers and
always reports `workflow.active=false` and `n8n_dispatched=false`.
