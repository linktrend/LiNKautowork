---
name: bash-linux
description: Use Bash and Unix shell commands safely for repository inspection, scripting, and automation.
version: 1.0.0
status: active
tags: [bash, shell, linux, cli]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/bash-linux
---

# Bash Linux

Use this skill when running shell commands or writing shell scripts.

## Rules

- Prefer `rg` for search when available.
- Quote paths that may contain spaces.
- Avoid destructive commands unless explicitly requested.
- Use dry-run flags when available.
- Keep scripts explicit about working directory.
- Capture and report command failures.
- Do not expose secrets in command output.

## Script Checklist

- shebang if executable
- strict mode when appropriate
- clear arguments
- helpful usage text
- predictable exit codes
- tests or sample runs

## Proof

Useful evidence includes:

- command output summary
- script sample run
- shellcheck or syntax check when available
- error-path behavior

## Progressive Disclosure

Run the smallest command that answers the current question. Do not scan broad filesystem areas unless needed.
