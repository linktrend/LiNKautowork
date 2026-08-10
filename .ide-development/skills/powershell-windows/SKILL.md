---
name: powershell-windows
description: Use PowerShell and Windows shell patterns safely when a task targets Windows environments.
version: 1.0.0
status: active
tags: [powershell, windows, shell, cli]
source_adapted_from:
  - link-antigravity-kit/.agent/skills/powershell-windows
---

# PowerShell Windows

Use this skill only when the target environment is Windows or PowerShell-specific.

## Rules

- Prefer explicit paths and parameters.
- Use `-WhatIf` for risky commands when supported.
- Do not assume Unix utilities exist.
- Treat execution policy and permissions as environment constraints.
- Avoid destructive filesystem commands without explicit confirmation.
- Record Windows-specific assumptions.

## Checklist

- shell is PowerShell, not Bash
- paths use compatible syntax
- environment variables are accessed correctly
- command works in the target Windows version
- output is suitable for proof

## Output

- command used
- target environment
- result
- blockers or compatibility notes

## Progressive Disclosure

Read Windows-specific docs or scripts only when the task targets Windows. Otherwise prefer the repository's normal shell conventions.
