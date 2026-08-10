---
name: api-patterns
description: Design and review APIs, contracts, request/response shapes, versioning, and interface boundaries.
version: 1.0.0
status: active
tags: [api, contracts, interfaces, integration]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/api-patterns
  - addyosmani/agent-skills/skills/api-and-interface-design
---

# API Patterns

Use this skill when designing, implementing, or reviewing an API or interface boundary.

## Use When

- creating REST, GraphQL, tRPC, RPC, or internal module APIs
- changing request or response shapes
- defining integration contracts
- adding pagination, filtering, auth, or error handling
- reviewing backward compatibility

## Design Checklist

- consumer and use case are clear
- request shape is explicit
- response shape is stable and typed
- errors are predictable and documented
- auth and authorization are accounted for
- pagination/rate limits exist when needed
- versioning or migration path is clear for breaking changes
- tests cover contract behavior

## Rules

- Prefer the repo's existing API style.
- Avoid breaking public consumers without a migration path.
- Keep transport details separate from business logic where practical.
- Validate inputs at boundaries.
- Return errors that callers can act on.
- Document material behavior changes.

## Proof

Useful evidence includes:

- contract tests
- request/response examples
- type checks
- integration tests
- updated API docs

## Progressive Disclosure

Read existing API patterns near the target boundary before introducing a new style. Do not redesign unrelated endpoints.
