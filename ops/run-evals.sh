#!/usr/bin/env bash
set -euo pipefail

SCENARIOS_FILE="/Users/linktrend/Projects/LiNKautowork/automations/evals/scenarios/urgent-event-ingestion-dirty-data.json"
REPLAYS_FILE="/Users/linktrend/Projects/LiNKautowork/automations/evals/replays/known-failures.json"

if [[ ! -f "$SCENARIOS_FILE" || ! -f "$REPLAYS_FILE" ]]; then
  echo "Eval assets missing"
  exit 1
fi

TOTAL_SCENARIOS="$(jq 'length' "$SCENARIOS_FILE")"
TOTAL_REPLAYS="$(jq 'length' "$REPLAYS_FILE")"

echo "Dirty-data scenarios: $TOTAL_SCENARIOS"
echo "Known-failure replays: $TOTAL_REPLAYS"
echo "Run these against gateway/n8n test harness and persist outcomes into audit + LiNKbrain."
