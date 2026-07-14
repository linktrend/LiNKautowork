# Agent Report: DS-000

- **Issue:** DS-000
- **Runtime used:** cursor | codex
- **Branch:** 
- **Last commit:** 
- **Status:** complete | blocked

## Summary

2–4 sentences of what was done.

## Files changed

- `path/to/file`

## Commands run

| Command | Exit code | Notes |
|---------|-----------|-------|
| `example` | 0 | |

## Proof block (DS-B5)

```json
{
  "acceptance_criteria": [
    {
      "id": "AC-1",
      "description": "",
      "verified": true,
      "evidence": "command output or artifact path"
    }
  ],
  "commands": [
    {
      "command": "",
      "exit_code": 0,
      "artifact_path": ""
    }
  ]
}
```

## Trajectory / debug (DS-B10) — required

Executor must fill this section on every report. Reviewer rejects vacuous or missing trajectory on blocked issues.

- **Session id:** (if available)
- **Log path:** path to agent log, terminal capture, or debug artifact
- **Commands attempted:** brief list when debugging failures
- **Failure hypothesis:** (required if status is `blocked`)

## Blockers

None | describe blocker and what Principal or Orchestrator must decide

## Next step

What Integrator or Orchestrator should do next.
