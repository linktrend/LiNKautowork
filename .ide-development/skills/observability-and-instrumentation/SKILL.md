---
name: observability-and-instrumentation
description: Add or review logs, metrics, traces, and diagnostics so production behavior is explainable.
version: 1.0.0
status: active
tags: [observability, logging, metrics, tracing, diagnostics]
source_adapted_from:
  - addyosmani/agent-skills/skills/observability-and-instrumentation
---

# Observability And Instrumentation

Use this skill when a feature, workflow, service, or integration needs diagnosable runtime behavior.

## Use When

- adding production behavior that may fail
- integrating external services
- adding background jobs or workflows
- debugging is hard without runtime signals
- shipping a feature that needs monitoring

## Signal Checklist

- logs identify important lifecycle events
- errors include actionable context without secrets
- metrics capture volume, latency, failure, or saturation where useful
- traces or correlation IDs connect related operations when available
- dashboards or alerts are considered for production-critical paths

## Rules

- Do not log secrets, tokens, passwords, private payloads, or unnecessary personal data.
- Prefer structured logs over ambiguous strings where the stack supports it.
- Add enough context for debugging, not noisy exhaustive dumps.
- Make failure modes visible.
- Document how to inspect the new signals when useful.

## Proof

Useful evidence includes:

- example log output
- metric name and expected behavior
- trace/correlation note
- test showing instrumentation path
- operational verification steps

## Progressive Disclosure

Read existing logging and monitoring patterns before adding a new style. Do not introduce new observability libraries without architectural justification.
