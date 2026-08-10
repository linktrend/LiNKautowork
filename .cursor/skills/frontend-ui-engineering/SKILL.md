---
name: frontend-ui-engineering
description: Build and review production-quality user interfaces with responsive layout, accessible interactions, and repo-consistent patterns.
version: 1.0.0
status: active
tags: [frontend, ui, accessibility, responsive, design]
source_adapted_from:
  - addyosmani/agent-skills/skills/frontend-ui-engineering
  - link-antigravity-kit/.codex/skills/frontend-design
  - anthropics/skills/skills/frontend-design
  - linktrend/LiNKtrend-System/docs/workspace/MVO-UI-POLICY.md
---

# Frontend UI Engineering

Use this skill when building or modifying user-facing web interfaces.

## Use When

- creating components
- changing layouts
- implementing interactive states
- improving accessibility
- converting a design or requirement into UI
- reviewing visual polish or usability

## UI Quality Checklist

- layout works at expected viewport sizes
- text fits inside containers
- controls have clear affordance and state
- keyboard and focus behavior are acceptable
- color, spacing, typography, and density match the app's domain
- loading, empty, error, and success states are handled where relevant
- visual changes are verified in a browser when possible

## Centralized UI System Rule

Before implementing UI, identify which UI system governs the surface:

- Operator or internal application UI: use the app's centralized shell, shared components, tokens, icon system, and composites.
- Customer, marketing, or public-template UI: use that surface's own template/design system, not the internal operator shell.
- External or upstream product UI: link, embed, or integrate at the boundary; do not rebuild a parallel version unless explicitly assigned.

For operator or internal application UI, page code should compose the central system. It should not define a parallel local design system.

Required behavior:

- Prefer existing shared primitives and composites before writing new markup.
- Use centralized shadcn/ui primitives when the repo provides them, typically under paths like `components/ui` or `@/components/ui/*`.
- Use lucide icons through the repo's established icon/button components when available.
- Use central tokens, formatting helpers, shell layout, navigation, page headers, status pills, form components, tables, action queues, cards, and metric components when they exist.
- Put reusable changes in the central component layer so the fix applies everywhere.
- If a needed reusable pattern does not exist, create the smallest central component or composite that fits the existing system, export it, and document usage where the repo convention expects it.
- Do not hand-roll one-off buttons, tables, breadcrumbs, page titles, status pills, icons, form controls, or card systems when centralized equivalents exist.
- Do not copy an operator/admin component system into public marketing templates unless the product explicitly requires that adaptation.
- Do not rebuild upstream product interfaces inside the local app when the correct product behavior is traceability, status, or a deep link.

When a repo has a UI authority file, component README, design-system doc, component index, or Cursor/Codex rule for UI standards, read that first and treat it as binding for the active issue.

## Rules

- Follow the existing design system before inventing new patterns.
- Prefer centralized component-system changes over page-local fixes when the same pattern appears in more than one place.
- Prefer domain-appropriate UI density and restraint over generic decorative layouts.
- Do not add marketing-style hero sections for operational tools unless the product requires it.
- Do not use UI cards inside other cards.
- Do not declare visual work complete without browser or screenshot verification when tooling is available.
- Keep changes scoped to the active issue.

## Proof

Useful evidence includes:

- screenshot paths
- browser route tested
- viewport sizes checked
- centralized components, tokens, or design-system paths used or changed
- confirmation that no duplicate one-off component was introduced when a central component existed
- accessibility notes
- test or build output
- before/after behavior

## Progressive Disclosure

Read the active issue, UI authority/design-system docs, relevant shared component docs, existing components, and nearby UI patterns. Do not scan unrelated screens unless the flow depends on them.
