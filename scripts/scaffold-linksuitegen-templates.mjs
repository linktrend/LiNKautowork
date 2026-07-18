#!/usr/bin/env node
/**
 * Scaffold LiNKsuitegen n8n workflow templates (webhook → gateway invoke).
 */
import { writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outDir = path.join(root, "automations/templates");

const TENANT_UUID = "00000000-0000-0000-0000-000000000001";

const HANDLES = [
  ["discovery_collect", "autowork.linksuitegen.discovery_collect"],
  ["ranking_persist", "autowork.linksuitegen.ranking_persist"],
  ["factory_generate", "autowork.linksuitegen.factory_generate"],
  ["factory_validate", "autowork.linksuitegen.factory_validate"],
  ["factory_export", "autowork.linksuitegen.factory_export"],
  ["admin_handoff", "autowork.linksuitegen.admin_handoff"],
  ["orchestrator_cycle", "autowork.linksuitegen.orchestrator_cycle"],
  ["crm_step", "autowork.linksuitegen.crm_step"],
  ["odoo_lead_create", "autowork.linksuitegen.odoo_lead_create"],
];

function template(webhookPath, handle) {
  return {
    name: `LiNKsuitegen / ${webhookPath}`,
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
      "Invoke LiNKaios Handler": {
        main: [[{ node: "Respond", type: "main", index: 0 }]],
      },
    },
    settings: { executionOrder: "v1" },
    meta: {
      tenant_uuid: TENANT_UUID,
      workflow_handle: handle,
      webhook_path: webhookPath,
    },
  };
}

for (const [slug, handle] of HANDLES) {
  const webhookPath = `linksuitegen-${slug}`;
  const file = path.join(outDir, `${webhookPath}.json`);
  writeFileSync(file, `${JSON.stringify(template(webhookPath, handle), null, 2)}\n`);
  console.log("wrote", file);
}
