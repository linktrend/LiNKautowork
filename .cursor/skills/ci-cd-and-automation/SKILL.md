---
name: ci-cd-and-automation
description: Design, repair, and review CI/CD workflows and automation gates that support verified delivery.
version: 1.0.0
status: active
tags: [ci, cd, automation, github-actions, delivery]
source_adapted_from:
  - addyosmani/agent-skills/skills/ci-cd-and-automation
---

# CI CD And Automation

Use this skill when adding, changing, or debugging automated checks, build pipelines, deployment workflows, or repository automation.

## Use When

- adding CI checks
- fixing failing automation
- defining release gates
- automating tests, builds, lint, or deployments
- reviewing GitHub Actions or similar workflows

## Rules

- Prefer existing automation style.
- Keep checks meaningful and fast enough for their gate.
- Do not hide failures with broad ignores.
- Separate validation from deployment when risk requires it.
- Do not add secrets to workflow files.
- Record required environment variables and permissions.

## Checklist

- trigger is appropriate
- permissions are least-privilege
- cache behavior is safe
- commands match local validation
- artifacts/logs are useful for debugging
- deployment has rollback or manual gate if needed

## Proof

Useful evidence includes:

- local command parity
- workflow syntax validation
- CI run result
- failure log analysis
- deployment dry-run or staging result

## Progressive Disclosure

Read workflow files, scripts they call, and package commands. Do not inspect unrelated pipelines unless the failure crosses workflows.
