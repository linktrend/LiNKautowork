---
name: architecture
description: Make and review architecture decisions with explicit tradeoffs, constraints, and integration boundaries.
version: 1.0.0
status: active
tags: [architecture, design, tradeoffs, decisions]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/architecture
  - addyosmani/agent-skills/skills/documentation-and-adrs
---

# Architecture

Use this skill when a decision affects system structure, module boundaries, data flow, deployment, or long-term maintainability.

## Use When

- selecting an architecture pattern
- changing module or service boundaries
- introducing shared abstractions
- making build/deploy/runtime decisions
- documenting an important tradeoff

## Decision Checklist

- problem and constraints are explicit
- alternatives are named
- tradeoffs are compared
- dependencies and blast radius are understood
- rollout and rollback are considered
- proof or validation approach is defined
- decision is recorded where future agents can find it

## Rules

- Prefer existing architecture unless it blocks the goal.
- Do not add abstractions without a concrete simplification or risk reduction.
- Separate reversible implementation choices from durable architecture decisions.
- Avoid architecture work inside small-change tasks unless necessary.
- Record significant decisions in the relevant artifact or documentation.

## Output

- recommended approach
- alternatives considered
- tradeoffs
- affected artifacts/modules
- validation plan
- open risks

## Progressive Disclosure

Read the active program/module, nearby architecture docs, and affected code boundaries. Do not scan the entire system unless the decision crosses system-wide boundaries.
