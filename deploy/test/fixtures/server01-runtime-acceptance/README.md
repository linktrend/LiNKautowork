# Server01 runtime-acceptance mock

Safe mock of n8n/AW-03 callback behavior for AW-04. It never starts Docker,
never calls n8n, never reads credentials, and never claims Server01 or production.

```bash
node deploy/test/fixtures/server01-runtime-acceptance/mock-n8n.mjs --self-test
```

Optional HTTP listener (loopback only):

```bash
node deploy/test/fixtures/server01-runtime-acceptance/mock-n8n.mjs
```

Default bind is `127.0.0.1:18081`. The process refuses secret-shaped headers and
always reports `workflow.active=false` and `n8n_dispatched=false`.
