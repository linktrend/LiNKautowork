---
name: source-driven-development
description: Ground implementation decisions in authoritative local or official sources instead of memory or guesses.
version: 1.0.0
status: active
tags: [sources, documentation, verification, research]
source_adapted_from:
  - addyosmani/agent-skills/skills/source-driven-development
---

# Source Driven Development

Use this skill when correctness depends on current APIs, libraries, standards, product docs, or repository-specific conventions.

## Source Priority

1. Local repository code and docs.
2. Official documentation or primary source.
3. Maintainer-authored examples.
4. Existing project patterns.
5. Secondary sources only when primary sources are unavailable.

## Rules

- Do not rely on memory for unstable APIs or current behavior.
- Cite or record the source for material decisions.
- Prefer local patterns over generic advice.
- Verify version-specific behavior when versions matter.
- Treat unsourced assumptions as assumptions, not facts.

## Workflow

1. Identify the claim or decision needing evidence.
2. Find the nearest authoritative source.
3. Extract only the needed facts.
4. Apply the fact to the current issue.
5. Record source and decision in proof or implementation notes.

## Output

- source consulted
- decision grounded by that source
- assumptions or gaps
- implementation implication

## Progressive Disclosure

Read only sources relevant to the current decision. Do not perform broad research unless the issue requires it.
