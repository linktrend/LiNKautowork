---
name: deployment-procedures
description: Plan, execute, verify, and roll back deployments with explicit gates and evidence.
version: 1.0.0
status: active
tags: [deployment, release, rollback, operations]
source_adapted_from:
  - link-antigravity-kit/.codex/skills/deployment-procedures
  - addyosmani/agent-skills/skills/shipping-and-launch
---

# Deployment Procedures

Use this skill when deploying, preparing deployment automation, or reviewing deployment readiness.

## Use When

- deploying to staging or production
- changing deployment configuration
- adding release automation
- validating rollout or rollback plans
- diagnosing deployment failures

## Deployment Checklist

- target environment is explicit
- current branch/version is known
- required tests and checks passed
- config and secrets are present outside the repo
- migration or data changes are accounted for
- rollback path is known
- post-deploy verification is defined

## Rules

- Do not deploy from an ambiguous repository or branch state.
- Do not hide skipped checks.
- Do not mix unrelated changes into a deployment.
- Escalate destructive migrations, security-sensitive changes, and irreversible operations.
- Record verification evidence after deployment.

## Output

- deployment target
- commands or workflow used
- pre-deploy checks
- post-deploy verification
- rollback or recovery note
- blockers or residual risk

## Progressive Disclosure

Read deployment docs, CI/CD workflow, environment notes, and changed files relevant to the deployment. Do not inspect unrelated infrastructure unless the deployment depends on it.
