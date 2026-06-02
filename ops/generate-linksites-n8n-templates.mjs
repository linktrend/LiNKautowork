#!/usr/bin/env node
/**
 * Generates LinkSites n8n workflow JSON from canonical autowork handles.
 * Webhook path = handle without autowork. prefix, dots → dashes.
 */
import { writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HANDLES = [
  "autowork.linksites.artifact_write_local",
  "autowork.linksites.supabase_mirror_upsert",
  "autowork.linksites.payload_sync_local",
  "autowork.linksites.preview_readiness_check",
  "autowork.linksites.crm_ready_to_contact_mark",
];

function toWebhookPath(handle) {
  return handle.replace(/^autowork\./, "").replace(/\./g, "-");
}

function buildWorkflow(handle) {
  const webhookPath = toWebhookPath(handle);
  const title = handle.replace(/^autowork\./, "").replace(/\./g, " / ");
  return {
    name: `LinkSites ${title}`,
    nodes: [
      {
        name: "Webhook",
        type: "n8n-nodes-base.webhook",
        typeVersion: 2,
        position: [240, 300],
        parameters: { httpMethod: "POST", path: webhookPath, responseMode: "responseNode" },
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
          jsonBody:
            "={{ { tenant_id: $json.body.tenant_id || $json.tenant_id, run_id: $json.body.run_id || $json.run_id, stage_id: $json.body.stage_id || $json.stage_id, workflow_handle: '" +
            handle +
            "', inputs: $json.body.inputs || $json.inputs || {}, lease_id: $json.body.lease_id || $json.lease_id, idempotency_key: $json.body.idempotency_key || $json.idempotency_key } }}",
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
    meta: { workflow_handle: handle, webhook_path: webhookPath },
  };
}

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "automations", "templates");
for (const handle of HANDLES) {
  const file = `${toWebhookPath(handle)}.json`;
  writeFileSync(join(root, file), `${JSON.stringify(buildWorkflow(handle), null, 2)}\n`);
  console.log(`wrote ${file}`);
}
