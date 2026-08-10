---
name: webapp-testing
description: Verify web application behavior through browser checks, user-flow testing, screenshots, and frontend diagnostics.
version: 1.0.0
status: active
tags: [web, testing, browser, frontend, qa]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/webapp-testing
  - anthropics/skills/skills/webapp-testing
---

# Webapp Testing

Use this skill when validating user-facing web behavior.

## Use When

- testing a local web app
- verifying UI changes
- reproducing browser-only bugs
- checking responsive behavior
- validating forms, navigation, dialogs, loading states, or error states

## Test Workflow

1. Identify the target URL and expected behavior.
2. Start or locate the dev server if needed.
3. Exercise the user flow in a real browser when available.
4. Check console/network errors when relevant.
5. Capture screenshots or observations for proof.
6. Record exact failures with reproduction steps.

## Coverage Checklist

- main happy path
- important error path
- loading/empty states
- mobile or narrow viewport when relevant
- accessibility basics for interactive controls
- no obvious console errors

## Rules

- Do not rely only on static code inspection for visual or interaction claims.
- Use screenshots or browser observations for UI proof when possible.
- Keep browser testing focused on acceptance criteria.
- If browser tooling is unavailable, record the limitation and use the best available fallback.

## Output

- tested URL or route
- user flow exercised
- screenshot paths or observations
- console/network findings
- pass/fail/blocker result

## Progressive Disclosure

Read the active issue, UI code touched, and local run instructions. Do not inspect unrelated screens unless the flow depends on them.
