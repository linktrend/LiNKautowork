#!/usr/bin/env node
/**
 * On PR merge to development: label GitHub issue linkdev:done and sync STATE.md.
 *
 * Usage: node sync-state-on-merge.mjs --repo owner/name --pr <number> [--state LiNKdev/factory/STATE.md] [--dry-run]
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';

function parseArgs(argv) {
  const out = {
    repo: process.env.GITHUB_REPOSITORY ?? null,
    pr: null,
    statePath: 'LiNKdev/factory/STATE.md',
    mappingPath: 'LiNKdev/product/reports/linktrend-system/github-issues.json',
    dryRun: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--repo') out.repo = argv[++i];
    else if (a === '--pr') out.pr = Number(argv[++i]);
    else if (a === '--state') out.statePath = argv[++i];
    else if (a === '--mapping') out.mappingPath = argv[++i];
    else if (a === '--dry-run') out.dryRun = true;
    else throw new Error(`Unknown argument: ${a}`);
  }
  if (!out.repo || !out.pr) throw new Error('--repo and --pr are required');
  return out;
}

async function gh(args) {
  const { spawnSync } = await import('node:child_process');
  const r = spawnSync('gh', args, { encoding: 'utf8' });
  if (r.status !== 0) {
    throw new Error(`gh ${args.join(' ')} failed: ${r.stderr || r.stdout}`);
  }
  return r.stdout.trim();
}

function parseState(text) {
  const m = text.match(/```json\s*(\{[\s\S]*?\})\s*```/);
  if (!m) throw new Error('STATE.md missing JSON block');
  return { json: JSON.parse(m[1]), block: m[1], prefix: text.slice(0, m.index), suffix: text.slice(m.index + m[0].length) };
}

function resolveLtsId(pr, mapping) {
  const titleHit = (pr.title ?? '').match(/^(LTS-\d+)\b/);
  if (titleHit && mapping[titleHit[1]]) return titleHit[1];
  const head = pr.headRefName ?? '';
  for (const ltsId of Object.keys(mapping)) {
    if (head.includes(ltsId.toLowerCase()) || head.includes(ltsId)) return ltsId;
  }
  const bodyMatches = [...(pr.body ?? '').matchAll(/\b(LTS-\d+)\b/g)].map((x) => x[1]);
  const unique = [...new Set(bodyMatches)];
  if (unique.length === 1 && mapping[unique[0]]) return unique[0];
  return null;
}

async function main() {
  const args = parseArgs(process.argv);
  const pr = JSON.parse(
    await gh(['pr', 'view', String(args.pr), '--repo', args.repo, '--json', 'title,headRefName,body,mergedAt,baseRefName']),
  );
  if (!pr.mergedAt || pr.baseRefName !== 'development') {
    console.log('MERGE_SYNC_SKIP not merged to development');
    return;
  }

  const mapping = existsSync(args.mappingPath)
    ? JSON.parse(readFileSync(args.mappingPath, 'utf8')).issues ?? {}
    : {};
  const ltsId = resolveLtsId(pr, mapping);
  if (!ltsId) {
    console.log('MERGE_SYNC_SKIP no LTS id resolved from PR');
    return;
  }

  const issueNum = mapping[ltsId]?.github_number;
  if (!issueNum) {
    console.log(`MERGE_SYNC_SKIP no github_number for ${ltsId}`);
    return;
  }

  if (!args.dryRun) {
    await gh(['issue', 'edit', String(issueNum), '--repo', args.repo, '--add-label', 'linkdev:done']).catch(() => {});
    for (const lab of ['linkdev:ready', 'linkdev:in-progress', 'linkdev:review-ready', 'linkdev:merge-ready', 'linkdev:principal-stop', 'runtime:cursor']) {
      await gh(['issue', 'edit', String(issueNum), '--repo', args.repo, '--remove-label', lab]).catch(() => {});
    }
    const body = `[linkdev-merge-sync] PR #${args.pr} merged to development — issue marked done. Orchestrator may advance the program.`;
    await gh(['issue', 'comment', String(issueNum), '--repo', args.repo, '--body', body]);
  }

  if (!existsSync(args.statePath)) {
    console.log('MERGE_SYNC_OK labels only (no STATE file)');
    return;
  }

  const stateText = readFileSync(args.statePath, 'utf8');
  const { json, block, prefix, suffix } = parseState(stateText);
  const row = json.issues?.[ltsId];
  if (!row) {
    console.log(`MERGE_SYNC_OK labels only (${ltsId} not in STATE)`);
    return;
  }
  if (row.status === 'done') {
    console.log(`MERGE_SYNC_OK already done (${ltsId})`);
    return;
  }

  row.status = 'done';
  row.last_pr = args.pr;
  row.done_at = new Date().toISOString();
  json.updated_at = row.done_at;

  const readyLeft = Object.entries(json.issues ?? {}).filter(([, v]) => v?.status === 'ready' || v?.status === 'in_progress' || v?.status === 'in-progress');
  if (readyLeft.length === 0 && json.phase === 'running') {
    json.next_orchestrator_trigger = 'merge_to_development';
  }

  const nextBlock = JSON.stringify(json, null, 2);
  const nextText = `${prefix}\`\`\`json\n${nextBlock}\n\`\`\`${suffix}`;
  if (!args.dryRun) {
    writeFileSync(args.statePath, nextText);
  }
  console.log(`MERGE_SYNC_OK ${ltsId} issue=#${issueNum} pr=#${args.pr} state_updated=${!args.dryRun}`);
}

main().catch((err) => {
  console.error(`MERGE_SYNC_FAIL: ${err.message}`);
  process.exit(1);
});
