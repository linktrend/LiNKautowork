---
name: documentation-and-adrs
description: Create and maintain durable documentation and decision records for architecture, APIs, workflows, and operational changes.
version: 1.0.0
status: active
tags: [documentation, adr, decisions, handoff]
source_adapted_from:
  - addyosmani/agent-skills/skills/documentation-and-adrs
  - link-antigravity-kit/.codex/skills/documentation-templates
---

# Documentation And ADRs

Use this skill when work changes behavior, architecture, APIs, workflows, setup, or operational expectations that future agents need to understand.

## Use When

- making architecture decisions
- changing public APIs or command surfaces
- adding setup or operational requirements
- writing handoff or release notes
- updating user-facing or agent-facing docs

## Documentation Rules

- Put docs near the owning layer.
- Update indexes when discoverability matters.
- Prefer concise durable facts over narrative.
- State dates or versions when timing matters.
- Record decisions, tradeoffs, and alternatives for architecture changes.
- Do not duplicate source of truth across multiple docs.

## ADR Shape

- context
- decision
- alternatives considered
- consequences
- validation or rollback path

## Proof

Documentation work is verified when:

- links/paths resolve
- affected indexes are updated
- wording matches current behavior
- old guidance is removed or clearly marked legacy

## Progressive Disclosure

Read the owning layer README/index, the artifact being changed, and directly linked docs. Do not rewrite broad docs unless requested.
