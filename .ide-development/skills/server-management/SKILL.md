---
name: server-management
description: Manage server processes, runtime configuration, health checks, logs, and operational diagnostics safely.
version: 1.0.0
status: active
tags: [server, operations, logs, runtime]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/server-management
---

# Server Management

Use this skill when starting, stopping, inspecting, or debugging server/runtime processes.

## Use When

- starting local services
- checking process health
- reading runtime logs
- diagnosing port conflicts
- changing runtime configuration
- preparing operational instructions

## Rules

- Identify the expected service and port before starting another server.
- Prefer project scripts over ad hoc commands.
- Do not kill unrelated processes without clear ownership.
- Do not expose secrets in logs or output.
- Record environment assumptions and missing variables.

## Checklist

- service command
- expected port or socket
- required env vars
- log location
- health endpoint or verification command
- stop/restart behavior

## Output

- current server state
- command run
- health result
- log findings
- blockers or next action

## Progressive Disclosure

Read package scripts, server docs, env examples, and relevant logs. Do not inspect unrelated services unless the failure crosses boundaries.
