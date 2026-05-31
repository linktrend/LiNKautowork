# Reviewer role

Validate executor output against the **issue spec** and **proof block**. Default runtime: **Cursor dispatch** (GitHub Actions → Cloud Agents API).

## Trigger

Label `linkdev:review-ready` on issue or PR.

## Checks (DS-B2, B3, B10, B21)

- [ ] Report exists at `report_path` with proof block filled
- [ ] **Trajectory / debug (DS-B10)** section present — session id, log path, or failure hypothesis when blocked; not empty on blocked issues
- [ ] **No vacuous PASS** — every claim has command output or artifact path
- [ ] Each acceptance criterion mapped to evidence
- [ ] Changes stay inside `allowed_files`; no `prohibited_files` touched
- [ ] No secrets in diff
- [ ] **Tier A gates passed** — re-run or confirm executor ran:

```bash
export LINKDEV_TIER=<issue tier>
export LINKDEV_REPORT=<report_path>
LiNKdev/factory/scripts/run-gates.sh --tier A --report "$LINKDEV_REPORT"
```

Reject if tier A fails even when executor claimed verify passed.

## Outcomes

| Result | Action |
|--------|--------|
| Pass | Comment approval; leave `linkdev:review-ready` for Integrator or add review-ready note |
| Fail | Remove merge-ready if set; comment gaps (include tier A gate failures); recommend `linkdev:blocked` or return to executor |

## Skills

`code-review-checklist`, `gstack/review`, `systematic-debugging` on failures.
