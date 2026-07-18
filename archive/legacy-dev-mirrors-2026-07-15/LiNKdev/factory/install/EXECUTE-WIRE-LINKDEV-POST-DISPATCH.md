# Execute: Wire LiNKdev post–dispatch (Cursor agent — autonomous)

**Principal launch (one line only, after Step B):**  
`Execute the EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md prompt in LiNKdev/factory/install/`

You are the **LiNKdev wire completion agent**. Step B (dispatch install + `CURSOR_API_KEY`) is done or documented as pending. Finish wire **without** Principal input unless blocked.

## Rules

1. Read [../../product/reports/wire/wire-automation-setup.md](../../product/reports/wire/wire-automation-setup.md) — dispatch v2 rows must show GitHub Actions triggers (not Cursor Automations UI). If `CURSOR_API_KEY` is pending, **STOP** with a clear blocker (Principal must add the secret).
2. Complete [CHECKLIST.md](CHECKLIST.md) **§9** (proof of wire):
   - Create or use a **dry-run test issue** with labels `linkdev:ready` + `runtime:cursor`.
   - Confirm **LiNKdev dispatch** workflow ran successfully (Actions run URL in report), or document equivalent API dispatch evidence.
   - Run `LiNKdev/factory/scripts/verify.sh` — must pass.
3. Update `WIRE-SESSION.md`: wire status `complete_pending_go`; §8 still **not** executed until Principal says **Go**.
4. Do **not** set program STATE to `running` or say **Go** to the Principal.
5. Commit/push wire reports to `development` if changed.

## Completion message to Principal (only output)

> **LiNKdev is wired.** Dispatch v2 and wire proof are recorded.  
> When you are ready to start the program, say **Go** (cloud Planner — `linkdev-go` command).  
> Do not say Go until you intend to start the product program.
