# SLO and Reliability Targets (MVO)

Targets:

- Critical workflow success >= 99%
- Non-critical workflow success >= 97%
- Urgent ingest-to-dispatch p95 <= 30s
- Scheduled briefing jobs complete within 5 minutes of scheduled start
- RTO <= 60 minutes
- RPO <= 15 minutes

Instrumentation surface:

- `linkautowork_ingress_dispatch_latency_ms`
- `linkautowork_execution_outcome_total`
- `linkautowork_killswitch_events_total`

Alert rules baseline is in `ops/alerts/prometheus-rules.yml`.
