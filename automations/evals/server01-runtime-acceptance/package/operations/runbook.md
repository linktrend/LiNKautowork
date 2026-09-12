# Server01 runtime acceptance runbook

This package is a **source-only mock fixture**. It is not imported, activated,
canaried, certified, or rolled back on Server01 or any live n8n.

Operators run the mock under `deploy/test/fixtures/server01-runtime-acceptance/`
with `--self-test`, or `node scripts/run-automation-evals.mjs --profile=smoke`.
Those commands execute deterministic schema, admission, transition, callback,
and receipt checks in-process. They never start Docker, never open a network
path to n8n, never read credentials, and never write a live workflow.

GAP deployment-profile fields such as `canary_required` and
`previous_certified_release_required` remain schema-shaped metadata only.
They do **not** authorize a live canary, certified release, or production
rollback from this fixture. Live import, digest verification against a real
n8n export, and founder canary authority stay on HOLD (see `HOLD.md`).
