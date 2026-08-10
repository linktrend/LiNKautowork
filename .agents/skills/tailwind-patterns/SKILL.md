---
name: tailwind-patterns
description: Apply Tailwind CSS patterns consistently with project tokens, responsive constraints, and maintainable class structure.
version: 1.0.0
status: active
tags: [tailwind, css, frontend, design-system]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/tailwind-patterns
---

# Tailwind Patterns

Use this skill when writing or reviewing Tailwind CSS.

## Rules

- Follow existing Tailwind version and project conventions.
- Prefer design tokens and existing utility patterns.
- Use responsive constraints deliberately.
- Avoid one-off color palettes unless the design system allows them.
- Keep class lists readable.
- Extract components only when reuse or clarity justifies it.

## Checklist

- spacing and sizing align with existing UI
- responsive behavior is explicit
- states are represented: hover, focus, disabled, selected, loading where relevant
- dark mode or theme behavior is preserved if present
- no layout shifts from dynamic content

## Proof

Useful evidence includes:

- screenshot
- viewport check
- build/lint result
- visual comparison

## Progressive Disclosure

Read existing components and Tailwind config before introducing new patterns.
