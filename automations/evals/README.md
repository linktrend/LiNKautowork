# Eval Assets

This folder stores versioned eval assets required by the MVO Karpathy loop.

- `scenarios/urgent-event-ingestion-dirty-data.json`: 120 dirty-data scenarios for stress testing.
- `replays/known-failures.json`: replay set for known historical failure classes.

Promotion policy for candidate workflow versions:

1. 100% pass on synthetic eval scenarios.
2. 100% pass on known failure replays.
3. Evidence summarized into audit artifacts and LiNKbrain logs.
