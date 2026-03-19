import { Counter, Histogram, Registry } from 'prom-client';

const registry = new Registry();

export const ingressLatencyMs = new Histogram({
  name: 'linkautowork_ingress_dispatch_latency_ms',
  help: 'Ingress dispatch latency in milliseconds',
  buckets: [5, 10, 25, 50, 100, 250, 500, 1000, 5000],
  registers: [registry],
});

export const executionOutcome = new Counter({
  name: 'linkautowork_execution_outcome_total',
  help: 'Execution outcomes by criticality and status',
  labelNames: ['criticality', 'status'] as const,
  registers: [registry],
});

export const killSwitchEvents = new Counter({
  name: 'linkautowork_killswitch_events_total',
  help: 'Kill switch event count',
  labelNames: ['scope', 'action'] as const,
  registers: [registry],
});

export function getMetricsRegistry(): Registry {
  return registry;
}
