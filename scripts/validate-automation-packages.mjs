import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateCatalog } from '../packages/automation-catalog/src/catalog.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const result = validateCatalog(root);

if (result.errors.length > 0) {
  for (const error of result.errors) {
    console.error(`Automation validation failed [${error.code}] ${error.packageDir ?? ''}/${error.file}: ${error.message}`.replace(/^\s+/, ''));
  }
  process.exit(1);
}

console.log(`Automation package validation passed (${result.results.length} catalogue release${result.results.length === 1 ? '' : 's'})`);
