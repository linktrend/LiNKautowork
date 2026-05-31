#!/usr/bin/env node
/**
 * LiNKdev dispatch v2 — launch a Cursor Cloud Agent for a factory role.
 * Node 22+. No npm dependencies (uses global fetch).
 *
 * Usage:
 *   node dispatch-cursor-agent.mjs --role <orchestrator|executor|reviewer|integrator> \
 *     [--repo owner/name] [--issue N] [--pr N] [--dry-run]
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const FACTORY_ROOT = join(__dirname, '..');
const API_URL = 'https://api.cursor.com/v1/agents';

const ROLE_DIRS = {
  orchestrator: 'orchestrator',
  executor: 'executor-cursor',
  reviewer: 'reviewer',
  integrator: 'integrator',
};

function parseArgs(argv) {
  const out = { role: null, repo: process.env.GITHUB_REPOSITORY ?? null, issue: null, pr: null, dryRun: false };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--role') out.role = argv[++i];
    else if (a === '--repo') out.repo = argv[++i];
    else if (a === '--issue') out.issue = Number(argv[++i]);
    else if (a === '--pr') out.pr = Number(argv[++i]);
    else if (a === '--dry-run') out.dryRun = true;
    else if (a === '-h' || a === '--help') {
      console.log(`Usage: node dispatch-cursor-agent.mjs --role <orchestrator|executor|reviewer|integrator> [--repo owner/name] [--issue N] [--pr N] [--dry-run]`);
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${a}`);
    }
  }
  if (!out.role || !ROLE_DIRS[out.role]) {
    throw new Error('--role is required (orchestrator|executor|reviewer|integrator)');
  }
  if (!out.repo) {
    throw new Error('--repo or GITHUB_REPOSITORY is required');
  }
  return out;
}

function readRoleMd(role) {
  const dir = ROLE_DIRS[role];
  const path = join(FACTORY_ROOT, 'prompts', dir, 'ROLE.md');
  return readFileSync(path, 'utf8');
}

function buildPrompt({ role, repo, issue, pr }) {
  const roleMd = readRoleMd(role);
  const lines = [
    `You are the LiNKdev **${role}** role for repository **${repo}**.`,
    'Dispatch v2 started you via GitHub Actions and the Cursor Cloud Agents API.',
    'Coordination: GitHub labels + `LiNKdev/factory/STATE.md` (read before acting).',
    '',
  ];
  if (issue) lines.push(`**Issue:** #${issue}`, '');
  if (pr) lines.push(`**Pull request:** #${pr}`, '');
  lines.push('## Role contract (`LiNKdev/factory/prompts/.../ROLE.md)', '', roleMd, '', '---', 'Execute this role now in the repository.');
  return lines.join('\n');
}

function repoPayload({ repo, issue, pr }) {
  const url = `https://github.com/${repo}`;
  const entry = { url };
  if (pr) {
    entry.prUrl = `${url}/pull/${pr}`;
  } else {
    entry.startingRef = process.env.LINKDEV_DISPATCH_REF ?? 'development';
  }
  return [entry];
}

async function dispatchAgent(prompt, repoConfig) {
  const apiKey = process.env.CURSOR_API_KEY;
  if (!apiKey) {
    throw new Error('CURSOR_API_KEY is not set');
  }
  const auth = Buffer.from(`${apiKey}:`, 'utf8').toString('base64');
  const body = {
    prompt: { text: prompt },
    repos: repoConfig,
    name: `LiNKdev-${repoConfig[0]?.url?.split('/').pop() ?? 'repo'}`,
  };
  const res = await fetch(API_URL, {
    method: 'POST',
    headers: {
      Authorization: `Basic ${auth}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    json = { raw: text };
  }
  if (!res.ok) {
    throw new Error(`Cursor API ${res.status}: ${JSON.stringify(json)}`);
  }
  return json;
}

async function main() {
  const args = parseArgs(process.argv);
  const prompt = buildPrompt(args);
  const repos = repoPayload(args);

  if (args.dryRun) {
    console.log('DRY_RUN: would POST /v1/agents');
    console.log('role:', args.role);
    console.log('repo:', args.repo);
    console.log('repos:', JSON.stringify(repos, null, 2));
    console.log('prompt_chars:', prompt.length);
    process.exit(0);
  }

  const result = await dispatchAgent(prompt, repos);
  const agentId = result?.agent?.id ?? result?.id ?? 'unknown';
  console.log(`DISPATCH_OK role=${args.role} agent=${agentId}`);
}

main().catch((err) => {
  console.error(`DISPATCH_FAIL: ${err.message}`);
  process.exit(1);
});
