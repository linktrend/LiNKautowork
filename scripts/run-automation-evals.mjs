import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRestoreBundle, DockerN8nRuntime, FileReceiptStore, runEvaluation } from '../packages/automation-eval-runner/src/run.mjs';

const profile = process.argv.find((value) => value.startsWith('--profile='))?.split('=')[1] ?? 'full';
const forcedFailures = process.argv
  .filter((value) => value.startsWith('--force-failure='))
  .map((value) => value.slice('--force-failure='.length));
const verifierKey = crypto.randomBytes(32);
const receiptDir = fs.mkdtempSync(path.join(os.tmpdir(), 'linkautowork-eval-receipts-'));
const runtime = new DockerN8nRuntime();
const restoreDir = fs.mkdtempSync(path.join(os.tmpdir(), 'linkautowork-eval-restore-'));
const result = runEvaluation({ profile, forcedFailures, verifierKey, runtime, receiptStore: new FileReceiptStore(receiptDir), restoreOutputDir: restoreDir });
process.stdout.write(`${JSON.stringify({ verdict: result.envelope.receipt.verdict, receiptDigest: result.envelope.receipt.receiptDigest, runtime: result.envelope.receipt.runtime, evidence: result.evidence, restoreManifest: result.restore.file })}\n`);
if (result.envelope.receipt.verdict !== 'passed') process.exitCode = 1;
