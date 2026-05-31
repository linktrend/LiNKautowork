# Execute: Wire LiNKdev post–UI automations (Cursor agent — autonomous)

**Principal launch (one line only, after Step B):**  
`Execute the EXECUTE-WIRE-LINKDEV-POST-UI.md prompt in LiNKdev/factory/install/`

You are the **LiNKdev wire completion agent**. Step B (Codex UI automations) is done. Finish wire **without** Principal input unless blocked.

## Rules

1. Read [../../product/reports/wire/wire-automation-setup.md](../../product/reports/wire/wire-automation-setup.md) — all five core automations must show created + trigger configured. If not, **STOP** and report which row failed (do not ask Principal to fix with you).
2. Complete [CHECKLIST.md](CHECKLIST.md) **§9** (proof of wire) as far as automation allows:
   - Create or use a **dry-run test issue** on GitHub with labels `linkdev:ready` + `runtime:cursor` (and issue spec path in body per factory templates).
   - Confirm executor automation fired OR document evidence (run log, comment, automation history screenshot path in report).
   - Run `LiNKdev/factory/scripts/verify.sh` — must pass.
3. Update `WIRE-SESSION.md`: wire status `complete_pending_go`; §8 still **not** executed until Principal says **Go**.
4. Do **not** set program STATE to `running` or say **Go** to the Principal.
5. Commit/push wire reports to `development` if changed.

## Completion message to Principal (only output)

> **LiNKdev is wired.** UI automations and wire proof are recorded.  
> When you are ready to start the program, say **Go** (cloud Planner — `linkdev-go` command).  
> Do not say Go until you intend to start `<product-id>` program execution.
