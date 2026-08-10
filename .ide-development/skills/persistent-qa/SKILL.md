---
name: persistent-qa
description: Perform independent QA that records defects, verification evidence, and regression concerns across execution loops.
version: 1.0.0
status: active
tags: [qa, verification, proof, review]
source_adapted_from:
  - LiNKskills/skills/persistent-qa
---

# Persistent QA

Use this skill when work needs independent quality assurance before review or completion.

## Use When

- validating issue proof
- checking a module definition of done
- verifying bug fixes
- testing user-facing workflows
- recording recurring defects or regression risks

## QA Standard

QA must produce evidence, not confidence.

Evidence can include:

- test command and result
- browser or UI verification
- screenshot path
- log excerpt
- reproduction steps
- before/after behavior
- proof artifact references

## Workflow

1. Read the target issue, proof, or module definition of done.
2. Map each acceptance criterion to a verification action.
3. Run the smallest sufficient checks.
4. Record pass, fail, or blocked for each criterion.
5. Identify regressions, missing tests, or incomplete proof.
6. Recommend review pass only when evidence is sufficient.

## Rules

- Do not accept "looks good" without evidence.
- Do not require exhaustive testing when focused proof is enough.
- Do not expand scope beyond the acceptance criteria unless a regression risk is visible.
- A failed check must name the exact failing behavior and reproduction path.
- A blocked check must name the missing dependency or unavailable environment.

## Output

- criteria-to-evidence map
- tests/checks performed
- defects found
- blocked checks
- residual risk
- recommended review verdict

## Progressive Disclosure

Read the target artifact, its proof, and directly relevant acceptance criteria. Do not inspect unrelated issues unless dependency or regression risk requires it.
