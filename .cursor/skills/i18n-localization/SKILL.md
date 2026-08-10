---
name: i18n-localization
description: Add or review internationalization, localization, locale files, formatting, and RTL readiness.
version: 1.0.0
status: active
tags: [i18n, localization, locale, translation]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/i18n-localization
---

# I18n Localization

Use this skill when user-facing text, locale behavior, or translation support is in scope.

## Use When

- extracting hardcoded UI text
- adding locale files
- reviewing translation keys
- handling dates, numbers, currency, or plurals
- checking RTL or language-specific layout risk

## Rules

- Follow existing i18n framework and key naming.
- Do not invent a localization system if one exists.
- Avoid concatenating translated fragments in ways that break grammar.
- Include fallback behavior.
- Check layout for longer translated text when relevant.

## Proof

Useful evidence includes:

- locale switch result
- key lookup test
- screenshot in affected locale
- missing-key check
- formatting examples

## Progressive Disclosure

Read existing locale files, i18n config, and touched UI components. Do not refactor unrelated text.
