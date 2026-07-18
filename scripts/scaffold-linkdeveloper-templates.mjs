#!/usr/bin/env node
/**
 * Scaffold LiNKdeveloper n8n workflow templates (webhook → LiNKaios autowork invoke).
 * Covers adapter workflow keys (§7.2) and workflow-map handles (suites/linkdeveloper).
 */
import { writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const TENANT_UUID = "00000000-0000-0000-0000-000000000001";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outDir = path.join(root, "automations/templates");

/** Adapter keys from LiNKdeveloper internal spec §7.2 + deploy_scaffold/run_task. */
const ADAPTER_KEYS = [
  "run_validation",
  "status_sync",
  "starter_generation",
  "notification",
  "report_generation",
  "run_task",
  "deploy_scaffold",
];

/** Workflow-map handles from suites/linkdeveloper/workflow.md. */
const WORKFLOW_MAP_HANDLES = [
  "product_run_bootstrap",
  "issue_dispatch",
  "validation_record",
  "artifact_write",
];

function toHandle(slug) {
  return `autowork.linkdeveloper.${slug}`;
}

function toWebhookPath(slug) {
  return `linkdeveloper-${slug}`;
}

function template(slug, handle) {
  const webhookPath = toWebhookPath(slug);
  return {
    name: `LiNKdeveloper / ${slug}`,
    nodes: [
      {
        name: "Webhook",
        type: "n8n-nodes-base.webhook",
        typeVersion: 2,
        position: [240, 300],
        parameters: {
          httpMethod: "POST",
          path: webhookPath,
          responseMode: "responseNode",
        },
      },
      {
        name: "Invoke LiNKaios Handler",
        type: "n8n-nodes-base.httpRequest",
        typeVersion: 4,
        position: [520, 300],
        parameters: {
          method: "POST",
          url: "={{ $env.LINKAIOS_AUTOWORK_INVOKE_URL }}",
          sendBody: true,
          sendHeaders: true,
          headerParameters: {
            parameters: [
              { name: "content-type", value: "application/json" },
              {
                name: "x-linkautowork-invoke-secret",
                value: "={{ $env.LINKAUTOWORK_INVOKE_SECRET }}",
              },
            ],
          },
          jsonBody: `={{ { tenant_id: $json.body.tenant_id || $json.tenant_id, run_id: $json.body.run_id || $json.run_id, stage_id: $json.body.stage_id || $json.stage_id, workflow_handle: '${handle}', inputs: $json.body.inputs || $json.inputs || {}, lease_id: $json.body.lease_id || $json.lease_id, idempotency_key: $json.body.idempotency_key || $json.idempotency_key } }}`,
        },
      },
      {
        name: "Respond",
        type: "n8n-nodes-base.respondToWebhook",
        typeVersion: 1,
        position: [800, 300],
        parameters: {
          respondWith: "json",
          responseBody: "={{ $json }}",
        },
      },
    ],
    connections: {
      Webhook: { main: [[{ node: "Invoke LiNKaios Handler", type: "main", index: 0 }]] },
      "Invoke LiNKaios Handler": { main: [[{ node: "Respond", type: "main", index: 0 }]] },
    },
    settings: { executionOrder: "v1" },
    meta: {
      tenant_uuid: TENANT_UUID,
      workflow_handle: handle,
      webhook_path: webhookPath,
    },
  };
}

const allSlugs = [...ADAPTER_KEYS, ...WORKFLOW_MAP_HANDLES];
for (const slug of allSlugs) {
  const handle = toHandle(slug);
  const file = path.join(outDir, `${toWebhookPath(slug)}.json`);
  writeFileSync(file, `${JSON.stringify(template(slug, handle), null, 2)}\n`);
  console.log("wrote", file);
}
