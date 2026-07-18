# Execute: LiNKdev dispatch install (Cursor agent — autonomous)

**Principal launch (one line only):**  
`Execute the EXECUTE-LINKDEV-DISPATCH-INSTALL.md prompt in LiNKdev/factory/install/`

You are the **LiNKdev dispatch install agent**. Complete dispatch wiring **without** opening Cursor Automations UI. Do not ask the Principal questions unless **blocked** (cannot use `gh`, cannot push, missing admin to add secrets).

## Rules

1. Read [../docs/DISPATCH.md](../docs/DISPATCH.md) first.
2. Confirm Step A copied workflows (see [EXECUTE-WIRE-LINKDEV.md](EXECUTE-WIRE-LINKDEV.md) §3). If `.github/workflows/linkdev-dispatch.yml` is missing, copy from `LiNKdev/factory/install/github/` and commit to `development`.
3. **Principal-only (document, do not invent secrets):** GitHub repo → Settings → Secrets → Actions → `CURSOR_API_KEY` (Cursor Dashboard → API Keys). Record in `WIRE-SESSION.md` as `configured` / `pending_principal` based on whether you can verify dispatch runs (you cannot read secret values).
4. Run `gh workflow list` — expect **LiNKdev dispatch** and **LiNKdev guard** on the default branch.
5. Optional local check: `node LiNKdev/factory/scripts/dispatch-cursor-agent.mjs --role orchestrator --dry-run`
6. Update [../../product/reports/wire/wire-automation-setup.md](../../product/reports/wire/wire-automation-setup.md): mark dispatch v2 rows (orchestrator, reviewer, integrator, executor-cursor) with trigger = GitHub Actions, not UI.
7. Update [../../product/reports/wire/WIRE-SESSION.md](../../product/reports/wire/WIRE-SESSION.md): dispatch status `complete` or `blocked` with reason.
8. Never commit secrets or `.env`.

## Completion message to Principal (only output)

When workflows are on `development` and secret status is recorded, print **only**:

> **Dispatch Step B complete.** Add `CURSOR_API_KEY` in GitHub Actions secrets if not already set.  
> Tell this Cursor agent: `Execute the EXECUTE-WIRE-LINKDEV-POST-DISPATCH.md prompt in LiNKdev/factory/install/`

Do not say **Go**.
