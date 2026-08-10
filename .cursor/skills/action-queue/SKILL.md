---
name: action-queue
description: Feed-style attention rows for admin/operator shell surfaces. Use when the UI is a task or inbox feed rather than a columnar table.
---

# Action Queue

Use this pattern for full-width feed rows with a left accent stripe.

## Use When

- the surface is an inbox, alerts list, or attention feed
- each row is primarily title, subtitle, and meta
- the row behaves like a card, not a spreadsheet

## Do Not Use When

- the surface is primarily columnar
- users need many visible columns at once

In those cases, use `skills/data-table/SKILL.md`.

## Layout Rules

1. Always render three text lines: title, subtitle, meta.
2. Keep spacing consistent across rows.
3. If there is one action, the whole row should be clickable.
4. If there are multiple actions, put them on the right and disable whole-row navigation.
5. Do not add chevrons or decorative clutter when hover state already communicates affordance.

## Design Intent

- fast scanning
- clear prioritization
- minimal UI noise
- strong consistency across inbox-like surfaces
