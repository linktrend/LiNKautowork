#!/usr/bin/env node
/**
 * Poll Cursor Cloud Agents for LiNKdev runs; post GitHub issue/PR status comments.
 * Requires CURSOR_API_KEY and GH_TOKEN (or gh auth).
 *
 * Usage: node sync-agent-watch.mjs [--repo owner/name] [--dry-run]
 */
import { appendFileSync } from 'node:fs';

const API = 'https://api.cursor.com/v1';
const MARKER = '[linkdev-agent-watch]';
const TERMINAL = new Set(['FINISHED', 'ERROR', 'CANCELLED', 'EXPIRED']);

function parseArgs(argv) {
  const out = { repo: process.env.GITHUB_REPOSITORY ?? null, dryRun: false };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--repo') out.repo = argv[++i];
    else if (a === '--dry-run') out.dryRun = true;
    else throw new Error(`Unknown argument: ${a}`);
  }
  if (!out.repo) throw new Error('--repo or GITHUB_REPOSITORY is required');
  return out;
}

async function cursorApi(path) {
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
  if (!res.ok) throw new Error(`Cursor API ${res.status} ${path}: ${JSON.stringify(json)}`);
  return json;
}

async function gh(args) {
  const { spawnSync } = await import('node:child_process');
  const r = spawnSync('gh', args, { encoding: 'utf8' });
  if (r.status !== 0) {
    throw new Error(`gh ${args.join(' ')} failed: ${r.stderr || r.stdout}`);
  }
  return r.stdout;
}

function parseAgentTarget(name, run, issueMap) {
  const issue = name.match(/^LiNKdev-(?:orchestrator|executor|reviewer|integrator)-issue-(\d+)-/);
  if (issue) return { kind: 'issue', number: Number(issue[1]) };
  const pr = name.match(/^LiNKdev-(?:orchestrator|executor|reviewer|integrator)-pr-(\d+)-/);
  if (pr) return { kind: 'pr', number: Number(pr[1]) };
  const branches = run?.git?.branches ?? [];
  for (const b of branches) {
    const branch = b.branch ?? '';
    for (const [ltsId, meta] of Object.entries(issueMap)) {
      if (branch.includes(ltsId)) {
        return { kind: 'issue', number: meta.github_number };
      }
    }
  }
  return null;
}

async function loadIssueMap() {
  const { readFileSync, existsSync } = await import('node:fs');
  const { join } = await import('node:path');
  const candidates = [
    'LiNKdev/product/reports/linktrend-system/github-issues.json',
  ];
  for (const p of candidates) {
    if (!existsSync(p)) continue;
    const data = JSON.parse(readFileSync(p, 'utf8'));
    return data.issues ?? {};
  }
  return {};
}

function statusEmoji(status) {
  if (status === 'RUNNING' || status === 'CREATING') return '🔄';
  if (status === 'FINISHED') return '✅';
  if (status === 'ERROR' || status === 'EXPIRED') return '❌';
  if (status === 'CANCELLED') return '⏹️';
  return 'ℹ️';
}

function buildWatchBody({ agent, run, roleHint }) {
  const status = run.status;
  const emoji = statusEmoji(status);
  const branch = run.git?.branches?.[0]?.branch;
  const prUrl = run.git?.branches?.[0]?.prUrl;
  const lines = [
    `${MARKER} ${emoji} **Agent ${status.toLowerCase()}**`,
    '',
    '| Field | Value |',
    '|-------|-------|',
    `| Agent | \`${agent.id}\` |`,
    `| Name | ${agent.name} |`,
    `| Run | \`${run.id}\` |`,
    `| Status | \`${status}\` |`,
  ];
  if (run.durationMs) lines.push(`| Duration | ${Math.round(run.durationMs / 1000)}s |`);
  if (branch) lines.push(`| Branch | \`${branch}\` |`);
  if (prUrl) lines.push(`| PR | ${prUrl} |`);
  lines.push(`| Cursor | [Open agent](${agent.url}) |`);
  lines.push('');
  if (status === 'FINISHED') {
    lines.push('**Done signal:** Executor should open a PR with `linkdev:review-ready`. Integrator merges after review.');
  } else if (TERMINAL.has(status) && status !== 'FINISHED') {
    lines.push('**Action:** Run failed or stopped. Tell your LiNKdev agent to investigate, or re-dispatch after fixing the blocker.');
  } else {
    lines.push('**Still running.** Next automatic update in ~10 minutes unless status changes.');
  }
  return lines.join('\n');
}

async function recentHasMarker(repo, target, agentId) {
  try {
    let comments;
    if (target.kind === 'issue') {
      comments = JSON.parse(await gh(['issue', 'view', String(target.number), '--repo', repo, '--json', 'comments']));
      const body = comments.comments?.map((c) => c.body).join('\n') ?? '';
      return body.includes(`${MARKER}`) && body.includes(agentId) && body.includes('FINISHED');
    }
    comments = JSON.parse(await gh(['api', `repos/${repo}/issues/${target.number}/comments`, '--paginate']));
    const body = (Array.isArray(comments) ? comments : comments.items ?? [])
      .map((c) => c.body)
      .join('\n');
    return body.includes(MARKER) && body.includes(agentId) && body.includes('FINISHED');
  } catch {
    return false;
  }
}

async function postComment(repo, target, body, dryRun) {
  if (dryRun) {
    console.log('DRY_RUN comment', target, body.slice(0, 120));
    return;
  }
  if (target.kind === 'issue') {
    await gh(['issue', 'comment', String(target.number), '--repo', repo, '--body', body]);
    return;
  }
  await gh(['pr', 'comment', String(target.number), '--repo', repo, '--body', body]);
}

async function applyTerminalLabels(repo, target, status, dryRun) {
  if (target.kind !== 'issue' || dryRun) return;
  if (status === 'ERROR' || status === 'EXPIRED') {
    await gh(['issue', 'edit', String(target.number), '--repo', repo, '--add-label', 'linkdev:blocked']).catch(() => {});
  }
}

async function main() {
  const args = parseArgs(process.argv);
  const issueMap = await loadIssueMap();
  const list = await cursorApi('/agents?limit=50');
  const items = list.items ?? [];
  let updated = 0;

  for (const agent of items) {
    if (!agent.name?.startsWith('LiNKdev-')) continue;
    if (!agent.latestRunId) continue;

    const run = await cursorApi(`/agents/${agent.id}/runs/${agent.latestRunId}`);
    const target = parseAgentTarget(agent.name, run, issueMap);
    if (!target) {
      console.log(`skip unmapped agent ${agent.id} name=${agent.name}`);
      continue;
    }
    const isTerminal = TERMINAL.has(run.status);
    const isActive = run.status === 'RUNNING' || run.status === 'CREATING';

    if (isTerminal && (await recentHasMarker(args.repo, target, agent.id))) {
      continue;
    }

    // Post on terminal always; post on active at most once per hour would need state file — post active every watch cycle is noisy
    // Only post active if no watch comment in last 30 min OR first time — simplify: post if no marker with this run id
    const body = buildWatchBody({ agent, run });
    const shouldPost =
      isTerminal ||
      isActive; // active: will post each cycle — too noisy. Fix: check last comment time

    if (!shouldPost) continue;

    if (isActive) {
      try {
        const json =
          target.kind === 'issue'
            ? JSON.parse(await gh(['issue', 'view', String(target.number), '--repo', args.repo, '--json', 'comments']))
            : { comments: [] };
        const recent = json.comments?.slice(-3) ?? [];
        if (recent.some((c) => c.body?.includes(MARKER) && c.body?.includes(run.status) && c.body?.includes(agent.id))) {
          continue;
        }
      } catch {
        /* post anyway */
      }
    }

    await postComment(args.repo, target, body, args.dryRun);
    await applyTerminalLabels(args.repo, target, run.status, args.dryRun);
    updated += 1;
    console.log(`updated ${target.kind} #${target.number} agent=${agent.id} status=${run.status}`);
  }

  if (process.env.GITHUB_STEP_SUMMARY) {
    appendFileSync(
      process.env.GITHUB_STEP_SUMMARY,
      `## LiNKdev agent watch\n\nUpdated **${updated}** issue/PR thread(s).\n`,
    );
  }
  console.log(`WATCH_OK updated=${updated}`);
}

main().catch((err) => {
  console.error(`WATCH_FAIL: ${err.message}`);
  process.exit(1);
});
