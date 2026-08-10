---
name: context-engineering
description: Shape the minimum useful context for an agent session so work stays grounded, narrow, and recoverable.
version: 1.0.0
status: active
tags: [context, session, progressive-disclosure, grounding]
source_adapted_from:
  - addyosmani/agent-skills/skills/context-engineering
---

# Context Engineering

Use this skill when starting, resuming, redirecting, or repairing an agent work session.

## Use When

- a session starts from low context
- work quality degrades because too much or too little context is loaded
- a task changes scope
- a handoff must be reconstructed
- an agent needs to decide what to read next

## Context Stack

Load context in this order:

1. entrypoint: `.cursor/README.md` or relevant adapter guide
2. bootstrap or session path
3. active command or workflow
4. active artifact
5. direct dependencies and proof/review/integration artifacts
6. source files only when execution requires them

## Rules

- Prefer progressive disclosure over broad scans.
- Keep confirmed facts separate from assumptions.
- Reconstruct state from artifacts, git, and handoff reports rather than hidden memory.
- Do not load historical reports unless they answer a current question.
- When context is missing, identify the exact missing artifact or decision.

## Output

- active work level
- relevant artifacts loaded
- facts versus assumptions
- next command or skill
- blockers or missing context

## Progressive Disclosure

This skill exists to enforce progressive disclosure. Stop reading once the next safe action is clear.
