# Server01 runtime acceptance runbook

This package is a technical acceptance fixture only. Do not import it as a
production automation or bind it to a client.

Evaluators run the mock runtime under `deploy/test/fixtures/server01-runtime-acceptance/`
with `--self-test`. The mock never starts n8n, never writes credentials, and never
activates the workflow.

Live import, digest verification against a real n8n export, and canary activation
remain AW-08. Rollback is deactivation and restore of the last certified workflow.
