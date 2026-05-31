# Ship criteria (program complete)

Checklist for **Program Definition of Done** (DS-B14). Planner fills when building the program after Principal OK on the finished-product narrative.

- [ ] Demo command or URL recorded in `LiNKdev/product/reports/<program-id>/STATUS.md`
- [ ] `LiNKdev/factory/scripts/verify.sh` passes at `LINKDEV_TIER=critical` for release scope
- [ ] Per-issue proof manifest where required (`LiNKdev/factory/scripts/proof-manifest.sh <report.md>`)
- [ ] Program proof manifest (`LiNKdev/factory/scripts/program-proof-manifest.sh <program-id>`)
- [ ] Merge replay traceability (`LiNKdev/factory/scripts/replay-merge-verify.sh <program-id>`)
- [ ] No open `linkdev:blocked` issues in STATE
- [ ] Principal Release OK (human; before staging/main)
