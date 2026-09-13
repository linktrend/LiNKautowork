import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DockerN8nRuntime, FileReceiptStore, runEvaluation } from '../packages/automation-eval-runner/src/run.mjs';
import { canonicalJson, evaluateAcceptanceSuite, sha256 } from '../deploy/test/fixtures/server01-runtime-acceptance/mock-runtime.mjs';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const profile = process.argv.find((value) => value.startsWith('--profile='))?.split('=')[1] ?? 'full';
const forcedFailures = process.argv
  .filter((value) => value.startsWith('--force-failure='))
  .map((value) => value.slice('--force-failure='.length));

if (profile === 'smoke') {
  const result = evaluateAcceptanceSuite();
  for (const observation of result.results) {
    if (forcedFailures.includes(observation.caseId)) observation.passed = false;
  }
  result.verdict = result.results.every((item) => item.passed) ? 'passed' : 'failed';
  result.envelope.receipt.verdict = result.verdict;
  delete result.envelope.receipt.receiptDigest;
  result.receiptDigest = sha256(canonicalJson(result.envelope.receipt));
  const receiptDir = fs.mkdtempSync(path.join(os.tmpdir(), 'linkautowork-eval-receipts-'));
  const evidence = path.join(receiptDir, `${result.receiptDigest.slice(7)}.json`);
  fs.writeFileSync(evidence, `${JSON.stringify(result.envelope, null, 2)}\n`, { mode: 0o600 });
  process.stdout.write(`${JSON.stringify({
    verdict: result.verdict,
    receiptDigest: result.receiptDigest,
    runtime: result.envelope.receipt.environment,
    evidence,
    restoreManifest: null,
    fixture: 'automations/evals/server01-runtime-acceptance',
  })}\n`);
  if (result.verdict !== 'passed') process.exitCode = 1;
} else {
  const verifierKey = crypto.randomBytes(32);
  const receiptDir = fs.mkdtempSync(path.join(os.tmpdir(), 'linkautowork-eval-receipts-'));
  const runtime = new DockerN8nRuntime();
  const restoreDir = fs.mkdtempSync(path.join(os.tmpdir(), 'linkautowork-eval-restore-'));
  const result = runEvaluation({
    packageDir: path.join(repoRoot, 'automations/packages/_golden-template'),
    profile,
    forcedFailures,
    verifierKey,
    runtime,
    receiptStore: new FileReceiptStore(receiptDir),
    restoreOutputDir: restoreDir,
  });
  process.stdout.write(`${JSON.stringify({ verdict: result.envelope.receipt.verdict, receiptDigest: result.envelope.receipt.receiptDigest, runtime: result.envelope.receipt.runtime, evidence: result.evidence, restoreManifest: result.restore.file })}\n`);
  if (result.envelope.receipt.verdict !== 'passed') process.exitCode = 1;
}
