---
name: testing-patterns
description: Choose and structure unit, integration, end-to-end, and regression tests for reliable proof.
version: 1.0.0
status: active
tags: [testing, proof, unit, integration, e2e]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/testing-patterns
---

# Testing Patterns

Use this skill when selecting, writing, reviewing, or repairing tests.

## Test Selection

- **Unit tests**: pure logic, edge cases, error handling, small functions.
- **Integration tests**: API boundaries, database behavior, service interactions, contracts.
- **End-to-end tests**: critical user flows, browser behavior, workflow integration.
- **Regression tests**: previously broken behavior that must stay fixed.

Choose the smallest test level that proves the acceptance criterion.

## Test Structure

Use Arrange, Act, Assert:

1. Arrange known inputs and state.
2. Act by calling the behavior under test.
3. Assert observable output or state.

## Good Test Criteria

- deterministic
- self-checking
- scoped to behavior, not implementation trivia
- clear failure message
- runs at the right speed for its purpose
- protects a meaningful acceptance criterion or risk

## Mocking Guidance

Mock:

- external APIs
- time/randomness
- network calls
- expensive or flaky services

Avoid mocking:

- the behavior being tested
- simple in-memory dependencies
- framework behavior with no local logic

## Proof Guidance

Record:

- test command
- result
- what criterion the test proves
- skipped tests and reason
- remaining risk

## Progressive Disclosure

Read the issue, acceptance criteria, relevant source files, and nearest existing test patterns. Do not invent a new testing style if the repo has an established one.
