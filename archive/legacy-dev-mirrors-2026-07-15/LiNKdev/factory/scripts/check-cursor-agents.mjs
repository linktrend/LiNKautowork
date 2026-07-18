#!/usr/bin/env node
/**
 * LiNKdev — inspect Cursor Cloud Agents (list + optional run status).
 * Requires CURSOR_API_KEY. Used by linkdev-cursor-status workflow and local debug.
 *
 * Usage:
 *   node check-cursor-agents.mjs [--agent bc-...] [--limit 20]
 */
const API = 'https://api.cursor.com/v1';

function parseArgs(argv) {
  const out = { agent: null, limit: 20 };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--agent') out.agent = argv[++i];
    else if (a === '--limit') out.limit = Number(argv[++i]);
    else throw new Error(`Unknown argument: ${a}`);
  }
  return out;
}

async function api(path) {
  const apiKey = process.env.CURSOR_API_KEY;
  if (!apiKey) throw new Error('CURSOR_API_KEY is not set');
  const auth = Buffer.from(`${apiKey}:`, 'utf8').toString('base64');
  const res = await fetch(`${API}${path}`, {
    headers: { Authorization: `Basic ${auth}` },
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    json = { raw: text };
  }
  if (!res.ok) {
    throw new Error(`Cursor API ${res.status} ${path}: ${JSON.stringify(json)}`);
  }
  return json;
}

async function main() {
  const args = parseArgs(process.argv);
  const me = await api('/me').catch((err) => ({ error: err.message }));
  console.log('CURSOR_ME', JSON.stringify(me, null, 2));

  if (args.agent) {
    const agent = await api(`/agents/${args.agent}`);
    console.log('AGENT', JSON.stringify(agent, null, 2));
    const runId = agent?.latestRunId;
    if (runId) {
      const run = await api(`/agents/${args.agent}/runs/${runId}`);
      console.log('RUN', JSON.stringify(run, null, 2));
    }
    return;
  }

  const list = await api(`/agents?limit=${args.limit}`);
  console.log('AGENTS', JSON.stringify(list, null, 2));
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
