#!/usr/bin/env node
/**
 * Create or verify the LAW-05 issue branch on GitHub before Cursor executor dispatch.
 * Requires GH_TOKEN and gh CLI.
 *
 * Usage: node prepare-executor-branch.mjs --repo owner/name --issue N [--dry-run]
 * Outputs: branch=<name> to stdout and GITHUB_OUTPUT when set.
 */
import { readFileSync, appendFileSync, existsSync } from 'node:fs';
import { issueBranchName } from './linkdev-dispatch-payload.mjs';

function parseArgs(argv) {
  const out = { repo: process.env.GITHUB_REPOSITORY ?? null, issue: null, dryRun: false };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--repo') out.repo = argv[++i];
    else if (a === '--issue') out.issue = Number(argv[++i]);
    else if (a === '--dry-run') out.dryRun = true;
    else throw new Error(`Unknown argument: ${a}`);
  }
  if (!out.repo || !out.issue) throw new Error('--repo and --issue are required');
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

function loadIssueMap() {
  const path = 'LiNKdev/product/reports/linktrend-system/github-issues.json';
  if (!existsSync(path)) return { issues: {} };
  return JSON.parse(readFileSync(path, 'utf8'));
}

function resolveIssueMeta(issueMap, issueNumber) {
  for (const [id, meta] of Object.entries(issueMap.issues ?? {})) {
    if (meta.github_number === issueNumber) {
      return { id, title: meta.title ?? id, spec_path: meta.spec_path };
    }
  }
  return null;
}

async function main() {
  const args = parseArgs(process.argv);
  const issueMap = loadIssueMap();
  const meta = resolveIssueMeta(issueMap, args.issue);
  if (!meta) {
    throw new Error(`Issue #${args.issue} not found in github-issues.json`);
  }

  const branch = issueBranchName(meta.id, meta.title);
  const base = process.env.LINKDEV_DISPATCH_REF ?? 'development';

  if (args.dryRun) {
    console.log(`DRY_RUN branch=${branch} base=${base}`);
    process.exit(0);
  }

  try {
    await gh(['api', `repos/${args.repo}/git/ref/heads/${branch}`, '--jq', '.ref']);
    console.log(`BRANCH_EXISTS branch=${branch}`);
  } catch {
    const sha = await gh(['api', `repos/${args.repo}/git/ref/heads/${base}`, '--jq', '.object.sha']);
    await gh([
      'api', '-X', 'POST', `repos/${args.repo}/git/refs`,
      '-f', `ref=refs/heads/${branch}`,
      '-f', `sha=${sha}`,
    ]);
    console.log(`BRANCH_CREATED branch=${branch} from=${base}`);
  }

  console.log(`branch=${branch}`);
  if (process.env.GITHUB_OUTPUT) {
    appendFileSync(process.env.GITHUB_OUTPUT, `branch=${branch}\n`);
  }
}

main().catch((err) => {
  console.error(`PREPARE_BRANCH_FAIL: ${err.message}`);
  process.exit(1);
});
