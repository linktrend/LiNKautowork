import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { extname } from 'node:path';

import type { ApprovedSource, IntakeAssessment } from './types.js';

const SECRET_KEYS = /(?:^|[_-])(password|token|api[_-]?key|authorization|credential|connection[_-]?string|private[_-]?key|access[_-]?key|client[_-]?secret|cookie)(?:$|[_-])/i;
const CUSTOMER_KEYS = /(?:^|[_-])(email|phone|customer|client[_-]?name|address|contact)(?:$|[_-])/i;
const SECRET_VALUE = /(?:-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{12,}|(?:sk|ghp|xox[baprs])[-_A-Za-z0-9]{12,})/i;

/** The persisted lifecycle states for a quarantined source intake record. */
export const intakeStates = ['submitted', 'quarantined', 'assessed', 'accepted_for_adaptation', 'rejected', 'mapped_to_candidate', 'archived'] as const;
export type IntakeState = typeof intakeStates[number];

const intakeTransitions: Readonly<Record<IntakeState, readonly IntakeState[]>> = {
  submitted: ['quarantined', 'rejected'],
  quarantined: ['assessed', 'rejected'],
  assessed: ['accepted_for_adaptation', 'rejected', 'archived'],
  accepted_for_adaptation: ['mapped_to_candidate', 'rejected', 'archived'],
  rejected: ['archived'],
  mapped_to_candidate: ['archived'],
  archived: [],
};

/** Returns whether an intake transition is allowed without reopening an archived or rejected source. */
export function canTransitionIntake(from: IntakeState, to: IntakeState): boolean {
  return intakeTransitions[from].includes(to);
}

/** Returns a lowercase SHA-256 digest of exact bytes without exposing the content. */
export function sha256(value: string | Buffer): string {
  return `sha256:${createHash('sha256').update(value).digest('hex')}`;
}

/** Hashes a quarantined file or archive by exact bytes. It never extracts or executes an archive. */
export async function hashIntakeArtifact(filePath: string): Promise<{ digest: string; isArchive: boolean }> {
  const bytes = await readFile(filePath);
  const isArchive = ['.zip', '.tgz', '.gz', '.tar', '.7z'].includes(extname(filePath).toLowerCase());
  return { digest: sha256(bytes), isArchive };
}

/** Recursively scans untrusted source content and returns redacted finding counts only. */
export function scanIntakeContent(content: string): { secretFindingCount: number; customerDataFindingCount: number } {
  let parsed: unknown = content;
  try {
    parsed = JSON.parse(content) as unknown;
  } catch {
    // Textual sources are scanned as text below.
  }

  let secretFindingCount = 0;
  let customerDataFindingCount = 0;
  const hasMaterialValue = (value: unknown): boolean => {
    if (typeof value === 'string') return value.trim().length > 0;
    if (typeof value === 'number') return true;
    if (Array.isArray(value)) return value.length > 0;
    return Boolean(value && typeof value === 'object' && Object.keys(value as Record<string, unknown>).length > 0);
  };
  const visit = (value: unknown, key?: string): void => {
    if (key && SECRET_KEYS.test(key) && key !== 'secret_ref' && key !== 'secret_reference' && hasMaterialValue(value)) secretFindingCount += 1;
    if (key && CUSTOMER_KEYS.test(key) && hasMaterialValue(value)) customerDataFindingCount += 1;
    if (typeof value === 'string') {
      if (SECRET_VALUE.test(value)) secretFindingCount += 1;
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => visit(item));
      return;
    }
    if (value && typeof value === 'object') {
      Object.entries(value as Record<string, unknown>).forEach(([childKey, child]) => visit(child, childKey));
    }
  };
  visit(parsed);
  if (typeof parsed === 'string') {
    if (SECRET_VALUE.test(parsed)) secretFindingCount += 1;
    if (/\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b/.test(parsed)) customerDataFindingCount += 1;
  }
  return { secretFindingCount, customerDataFindingCount };
}

/** Extracts safe source metadata; it does not return source values, credentials, or customer data. */
export function extractSourceMetadata(source: ApprovedSource): Pick<IntakeAssessment, 'detectedNodeTypes' | 'componentCount'> {
  let detectedNodeTypes: string[] = [];
  try {
    const parsed = JSON.parse(source.content) as { nodes?: Array<{ type?: unknown }> };
    if (Array.isArray(parsed.nodes)) {
      detectedNodeTypes = [...new Set(parsed.nodes.flatMap((node) => typeof node.type === 'string' ? [node.type] : []))].sort();
    }
  } catch {
    // Non-JSON source descriptors may be mapped manually through source.components.
  }
  return { detectedNodeTypes, componentCount: source.components.length || detectedNodeTypes.length };
}

/** Assess a source in quarantine. A failed scan results in a rejected assessment. */
export function assessSource(source: ApprovedSource): IntakeAssessment {
  const findings = scanIntakeContent(source.content);
  const metadata = extractSourceMetadata(source);
  return {
    sourceId: source.sourceId,
    contentDigest: sha256(source.content),
    detectedNodeTypes: metadata.detectedNodeTypes,
    componentCount: metadata.componentCount,
    secretFindingCount: findings.secretFindingCount,
    customerDataFindingCount: findings.customerDataFindingCount,
    status: findings.secretFindingCount || findings.customerDataFindingCount ? 'rejected' : 'assessed',
  };
}
