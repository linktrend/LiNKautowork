import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildCatalogIndex, indexBytes } from '../packages/automation-catalog/src/catalog.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'automations', 'catalog', 'index.json');
const expected = indexBytes(buildCatalogIndex(root));
const check = process.argv.includes('--check');

if (check) {
  const actual = fs.existsSync(output) ? fs.readFileSync(output, 'utf8') : '';
  if (actual !== expected) {
    console.error('Automation catalogue index is stale; run npm run build:catalog.');
    process.exit(1);
  }
  console.log('Automation catalogue index is current.');
} else {
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, expected, 'utf8');
  console.log(`Wrote ${path.relative(root, output)}.`);
}
