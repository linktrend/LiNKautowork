#!/usr/bin/env node
/**
 * Deterministic wave advance after integrator merge to development.
 * Reads PROGRAM.md DAG + STATE.md — no cloud orchestrator required for labels.
 *
 * Usage:
 *   node advance-wave-on-merge.mjs --program <id> [--state PATH] [--program-md PATH] [--repo owner/name] [--apply-labels] [--clear-handoff] [--dry-run]
 */
import { readFileSync, writeFileSync, existsSync, renameSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { createGhClient } from './linkdev-gh-api.mjs';

const HANDOFF_PATH = '.linkdev/handoff/orchestrator-wave-ready.json';
const HANDOFF_PROCESSED = '.linkdev/handoff/orchestrator-wave-ready.processed.json';
const DEFAULT_CAP = 10;

function parseArgs(argv) {
  const out = {
    programId: null,
    statePath: 'LiNKdev/factory/STATE.md',
    programPath: null,
    repo: process.env.GITHUB_REPOSITORY ?? null,
    applyLabels: false,
    clearHandoff: true,
    dryRun: false,
    waveCap: DEFAULT_CAP,
    waveCapExplicit: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--program') out.programId = argv[++i];
    else if (a === '--state') out.statePath = argv[++i];
    else if (a === '--program-md') out.programPath = argv[++i];
    else if (a === '--repo') out.repo = argv[++i];
    else if (a === '--apply-labels') out.applyLabels = true;
    else if (a === '--clear-handoff') out.clearHandoff = true;
    else if (a === '--no-clear-handoff') out.clearHandoff = false;
    else if (a === '--dry-run') out.dryRun = true;
    else if (a === '--wave-cap') {
      out.waveCap = Number(argv[++i]);
      out.waveCapExplicit = true;
    } else throw new Error(`Unknown argument: ${a}`);
  }
  if (!out.programId) throw new Error('--program is required');
  if (!out.programPath) {
    out.programPath = `LiNKdev/product/programs/${out.programId}/PROGRAM.md`;
  }
  return out;
}

function parseState(text) {
  const m = text.match(/```json\s*(\{[\s\S]*?\})\s*```/);
  if (!m) throw new Error('STATE.md missing JSON block');
  const prefix = text.slice(0, m.index);
  const suffix = text.slice(m.index + m[0].length);
  return { json: JSON.parse(m[1]), prefix, suffix };
}

function writeState(statePath, json, prefix, suffix, dryRun) {
  const nextBlock = JSON.stringify(json, null, 2);
  const nextText = `${prefix}\`\`\`json\n${nextBlock}\n\`\`\`${suffix}`;
  if (!dryRun) writeFileSync(statePath, nextText);
  return nextText;
}

/** @param {string} programPath */
function parseProgramIssues(programPath) {
  const text = readFileSync(programPath, 'utf8');
  /** @type {Record<string, { depends: string[], wave: number, runtime: string, tier: string, report?: string }>} */
  const issues = {};
  for (const line of text.split('\n')) {
    const m = line.match(/^\|\s*(LTS-\d+)\s*\|/);
    if (!m) continue;
    const parts = line.split('|').map((p) => p.trim());
    if (parts.length < 7) continue;
    const id = parts[1];
    const runtime = parts[3] || 'cursor';
    const tier = parts[4] || 'standard';
    const depcol = parts[5] ?? '';
    const waveCol = parts[6] ?? '';
    const depends =
      !depcol || depcol === '[]' || depcol === '—'
        ? []
        : depcol.split(',').map((d) => d.trim()).filter(Boolean);
    const waveMatch = waveCol.match(/W(\d+)/);
    const wave = waveMatch ? Number(waveMatch[1]) : 999;
    issues[id] = { depends, wave, runtime, tier };
  }
  return issues;
}

/** Read active wave cap from PROGRAM.md (## Active wave cap section). */
function parseWaveCapFromProgram(programPath, fallback = DEFAULT_CAP) {
  const text = readFileSync(programPath, 'utf8');
  const section = text.match(/## Active wave cap[\s\S]*?(?=\n## |\n*$)/);
  if (!section) return fallback;
  const concurrent = section[0].match(/\*\*(\d+)\*\*\s+concurrent/i);
  if (concurrent) return Number(concurrent[1]);
  const atMost = section[0].match(/at most\s+\*\*(\d+)\*\*/i);
  if (atMost) return Number(atMost[1]);
  return fallback;
}

function issueStatus(state, id) {
  return state.issues?.[id]?.status ?? null;
}

function isDone(state, id) {
  const s = issueStatus(state, id);
  return s === 'done';
}

function isActive(state, id) {
  const s = issueStatus(state, id);
  return s === 'ready' || s === 'in_progress' || s === 'in-progress';
}

function allDepsDone(state, programIssues, id) {
  const deps = programIssues[id]?.depends ?? [];
  return deps.every((d) => isDone(state, d) || (programIssues[d] && isDone(state, d)));
}

function countActive(state) {
  return Object.keys(state.issues ?? {}).filter((id) => isActive(state, id)).length;
}

function clearHandoffMarker(dryRun) {
  if (!existsSync(HANDOFF_PATH)) {
    console.log('ADVANCE_WAVE handoff marker absent — skip clear');
    return false;
  }
  if (dryRun) {
    console.log(`ADVANCE_WAVE would clear ${HANDOFF_PATH}`);
    return true;
  }
  renameSync(HANDOFF_PATH, HANDOFF_PROCESSED);
  console.log(`ADVANCE_WAVE cleared handoff → ${HANDOFF_PROCESSED}`);
  return true;
}

function applyLabels(programId, repo, dryRun) {
  if (dryRun) {
    console.log(`ADVANCE_WAVE would apply labels for ${programId} on ${repo}`);
    return;
  }
  const r = spawnSync(
    'bash',
    [
      'LiNKdev/factory/scripts/apply-wave-labels-from-state.sh',
      programId,
      '--repo',
      repo,
    ],
    { encoding: 'utf8', stdio: 'inherit' },
  );
  if (r.status !== 0) throw new Error('apply-wave-labels-from-state.sh failed');
}

function defaultReportPath(programId, ltsId) {
  return `LiNKdev/product/reports/${programId}/${ltsId}.md`;
}

/**
 * @param {ReturnType<typeof parseArgs>} args
 * @param {object} stateJson
 * @param {Record<string, { depends: string[], wave: number, runtime: string, tier: string }>} programIssues
 */
function computePromotions(stateJson, programIssues, waveCap) {
  const active = countActive(stateJson);
  const slots = Math.max(0, waveCap - active);
  if (slots === 0) return [];

  const doneIds = new Set(Object.entries(stateJson.issues ?? {}).filter(([, v]) => v?.status === 'done').map(([k]) => k));

  /** @type {string[]} */
  const candidates = Object.keys(programIssues)
    .filter((id) => !doneIds.has(id) && !isActive(stateJson, id))
    .filter((id) => {
      const deps = programIssues[id].depends;
      return deps.every((d) => doneIds.has(d));
    })
    .sort((a, b) => {
      const wa = programIssues[a].wave;
      const wb = programIssues[b].wave;
      if (wa !== wb) return wa - wb;
      return a.localeCompare(b);
    });

  if (candidates.length === 0) return [];

  return candidates.slice(0, slots);
}

async function main() {
  const args = parseArgs(process.argv);
  if (!existsSync(args.statePath)) {
    console.log('ADVANCE_WAVE_SKIP no STATE file');
    return;
  }
  if (!existsSync(args.programPath)) {
    console.log(`ADVANCE_WAVE_SKIP no PROGRAM at ${args.programPath}`);
    return;
  }

  const programIssues = parseProgramIssues(args.programPath);
  if (!args.waveCapExplicit) {
    args.waveCap = parseWaveCapFromProgram(args.programPath, args.waveCap);
  }
  const stateText = readFileSync(args.statePath, 'utf8');
  const { json, prefix, suffix } = parseState(stateText);
  if (!json.issues) json.issues = {};

  const promoted = computePromotions(json, programIssues, args.waveCap);
  let changed = false;

  for (const ltsId of promoted) {
    const meta = programIssues[ltsId];
    json.issues[ltsId] = {
      status: 'ready',
      runtime: meta.runtime,
      tier: meta.tier,
      depends_on: meta.depends,
      report: json.issues[ltsId]?.report ?? defaultReportPath(args.programId, ltsId),
    };
    changed = true;
    console.log(`ADVANCE_WAVE promote ${ltsId} → ready (DAG-unblocked, W${meta.wave})`);
  }

  json.next_orchestrator_trigger = 'none';
  json.updated_at = new Date().toISOString();

  if (changed) {
    writeState(args.statePath, json, prefix, suffix, args.dryRun);
    console.log(`ADVANCE_WAVE state_updated promoted=${promoted.length}`);
  } else {
    console.log('ADVANCE_WAVE no promotions (wave cap full or no unblocked issues)');
  }

  if (args.clearHandoff) {
    clearHandoffMarker(args.dryRun);
  }

  if (args.applyLabels && args.repo && promoted.length > 0) {
    applyLabels(args.programId, args.repo, args.dryRun);
  }

  console.log(`ADVANCE_WAVE_OK program=${args.programId} promoted=${promoted.join(',') || 'none'}`);
}

main().catch((err) => {
  console.error(`ADVANCE_WAVE_FAIL: ${err.message}`);
  process.exit(1);
});
