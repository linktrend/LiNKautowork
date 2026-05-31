# Execute: LiNKdev UI automations (Codex agent — autonomous)

**Principal launch (one line only):**  
`Execute the EXECUTE-LINKDEV-UI-AUTOMATIONS.md prompt in LiNKdev/factory/install/`

You are the **LiNKdev UI automations agent**. Configure **all** Cursor and Codex cloud automations in the provider UIs using **computer use**. Do not ask the Principal questions unless you are **blocked** (cannot log in, Automations feature missing, repeated UI failure).

## Rules

1. Read [AUTOMATION-MANIFEST.md](automations/AUTOMATION-MANIFEST.md) first.
2. Execute [automations/CURSOR-CREATE-AUTOMATIONS.md](automations/CURSOR-CREATE-AUTOMATIONS.md) then [automations/CODEX-CREATE-AUTOMATIONS.md](automations/CODEX-CREATE-AUTOMATIONS.md).
3. Use **`linkdev:`** labels only (not legacy `swarm:`).
4. Log every automation in [../../product/reports/wire/wire-automation-setup.md](../../product/reports/wire/wire-automation-setup.md) (name, provider, created Y/N, trigger Y/N, notes).
5. Update [../../product/reports/wire/WIRE-SESSION.md](../../product/reports/wire/WIRE-SESSION.md): set UI automations status to `complete` or `blocked` with reason.
6. Do not modify product application code. Do not commit secrets.
7. **Commit and push** only `LiNKdev/product/reports/wire/*` to `development` when done (if your environment allows).

## Automations to create (minimum)

| Name | Provider | Trigger |
|------|----------|---------|
| `LiNKdev-orchestrator` | Cursor | Merge/push to `development` |
| `LiNKdev-reviewer` | Cursor | Label `linkdev:review-ready` |
| `LiNKdev-integrator` | Cursor | Label `linkdev:merge-ready` |
| `LiNKdev-executor-cursor` | Cursor | Labels `linkdev:ready` + `runtime:cursor` |
| `LiNKdev-executor-codex` | Codex | Labels `linkdev:ready` + `runtime:codex` |

System prompts must reference the matching `LiNKdev/factory/prompts/<role>/ROLE.md` files in **this repository**.

Add any extra Codex automations listed in `LiNKdev/product/programs/*/PROGRAM.md` if present.

## Prerequisites (verify yourself)

- `LiNKdev/factory/scripts/install-labels.sh` already run (labels visible in GitHub).
- Wire Step A recorded in `WIRE-SESSION.md` (optional; proceed if labels exist).

## Completion message to Principal (only output)

When all five automations are created and enabled, print **only**:

> **Step B complete.** UI automations are configured.  
> Tell the Cursor agent: `Execute the EXECUTE-WIRE-LINKDEV-POST-UI.md prompt in LiNKdev/factory/install/`

If blocked, print the blocker and what automation failed; do not ask the Principal to click through with you.
