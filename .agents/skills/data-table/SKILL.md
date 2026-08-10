---
name: data-table
description: Columnar table guidance for admin/operator shell UI. Use for catalogs, indexes, settings lists, logs, and other structured row-and-column surfaces.
---

# Data Table

Use this pattern for structured tables where column comparison matters.

## Use When

- the user needs to compare multiple attributes across rows
- the UI is a catalog, index, audit log, settings list, or entity table
- alignment and repeatable row structure matter more than feed readability

## Rules

1. Keep columns explicit and stable.
2. Match header alignment to cell alignment.
3. Use consistent row heights unless a multiline description cell is intentional.
4. Prefer truncation and clipped overflow to horizontal scrolling.
5. Use icon actions sparingly and avoid duplicate navigation affordances.
6. Keep headers in Title Case.

## Avoid

- ad hoc inline table styling
- too many columns for the available width
- mixing feed patterns with table patterns

If the surface reads more like a task queue than a grid, use `skills/action-queue/SKILL.md` instead.
