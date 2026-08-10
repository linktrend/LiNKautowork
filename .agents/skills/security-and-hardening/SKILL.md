---
name: security-and-hardening
description: Identify and reduce security, privacy, authorization, input, dependency, and operational risks in development work.
version: 1.0.0
status: active
tags: [security, hardening, privacy, authorization]
source_adapted_from:
  - addyosmani/agent-skills/skills/security-and-hardening
  - link-antigravity-kit/.codex/skills/vulnerability-scanner
---

# Security And Hardening

Use this skill when a change touches trust boundaries, user input, authentication, authorization, secrets, data storage, external services, or deployment.

## Security Checklist

- inputs are validated at boundaries
- authorization is checked server-side
- secrets are not logged, committed, or exposed to clients
- errors do not leak sensitive internals
- dependencies and external calls are bounded and handled safely
- file, shell, network, and database operations are constrained
- tenant or user data boundaries are preserved
- audit/logging exists where risk requires it

## Rules

- Treat user input as untrusted.
- Do not store secrets in repository files.
- Do not rely on client-side checks for authorization.
- Do not weaken existing security controls for convenience.
- Escalate destructive, irreversible, or high-impact side effects.
- Record residual risk in proof or review.

## Proof

Useful evidence includes:

- security-focused tests
- permission checks
- validation examples
- dependency audit result
- manual threat note
- review finding resolution

## Blockers

Stop when required security decisions, credentials, access policies, or legal/compliance inputs are missing.

## Progressive Disclosure

Read the active issue, affected boundary code, auth/data-access rules, and relevant security docs. Do not perform broad security audit unless requested.
