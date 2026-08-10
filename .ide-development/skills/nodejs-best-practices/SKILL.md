---
name: nodejs-best-practices
description: Apply practical Node.js service, script, async, package, and runtime patterns.
version: 1.0.0
status: active
tags: [nodejs, javascript, typescript, backend, scripts]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/nodejs-best-practices
---

# Node.js Best Practices

Use this skill when writing or reviewing Node.js, JavaScript, or TypeScript runtime code.

## Rules

- Follow existing package manager and module conventions.
- Prefer simple async control flow over clever concurrency.
- Validate inputs at service and script boundaries.
- Handle process exits and errors deliberately in CLIs.
- Avoid adding dependencies without clear value.
- Keep environment variables documented and parsed safely.

## Checklist

- scripts are discoverable in `package.json` when appropriate
- errors are actionable
- async work is awaited or intentionally detached
- tests cover behavior or edge cases
- generated files are ignored or documented
- runtime version assumptions are clear

## Proof

Useful evidence includes:

- test output
- type check
- build output
- script sample run
- lint result

## Progressive Disclosure

Read nearby JS/TS code, `package.json`, config files, and existing tests. Do not restructure the runtime without a clear issue requirement.
