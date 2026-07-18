# Council summary — {{program_id}} — {{gate}}

- **Gate:** {{gate}} — {{gate_description}}
- **Program:** {{program_id}}
- **Reviewed at:** {{reviewed_at}}
- **Summary status:** {{summary_status}}
- **Report JSON:** {{report_json_path}}

## Subject artifacts

| Artifact | Path |
|----------|------|
| {{artifact_1_label}} | {{artifact_1_path}} |
| {{artifact_2_label}} | {{artifact_2_path}} |

## Combined verdict

{{combined_verdict_paragraph}}

## Advisor roll-up

| Advisor | Verdict | Summary |
|---------|---------|---------|
| security-advisor | {{security_verdict}} | {{security_summary}} |
| architecture-advisor | {{architecture_verdict}} | {{architecture_summary}} |
| dx-advisor | {{dx_verdict}} | {{dx_summary}} |
| qa-advisor | {{qa_verdict}} | {{qa_summary}} |
| product-advisor | {{product_verdict}} | {{product_summary}} |

## Blockers

{{#if blockers}}
| Advisor | Blocker |
|---------|---------|
{{#each blockers}}
| {{persona_id}} | {{message}} |
{{/each}}
{{else}}
None.
{{/if}}

## Warnings

{{#if warnings}}
| Advisor | Warning |
|---------|---------|
{{#each warnings}}
| {{persona_id}} | {{message}} |
{{/each}}
{{else}}
None.
{{/if}}

## Evidence index

### security-advisor

{{security_evidence}}

### architecture-advisor

{{architecture_evidence}}

### dx-advisor

{{dx_evidence}}

### qa-advisor

{{qa_evidence}}

### product-advisor

{{product_evidence}}

## Gate decision

| Outcome | Action |
|---------|--------|
| **PASS** | Proceed to next factory step for {{gate}} |
| **WARN** | Proceed if gate allows WARN; log warnings in program STATUS |
| **BLOCKER** | Halt — resolve blockers and re-run Council with new report JSON |

**Validation command:**

```bash
LiNKdev/factory/scripts/validate-council.sh {{report_json_path}} --gate {{gate}}
```

## Next step

{{next_step}}
