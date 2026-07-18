import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const templateDir = path.join(root, 'automations', 'templates');
const manifestPath = path.join(templateDir, 'manifest.json');
// Live set is governance-only (2026-07-18). Legacy LiNKsites / suitegen /
// linkdeveloper shells that called shelved LiNKaios invoke URLs were archived
// to automations/templates/archive/legacy-program-shells-2026-07-18/.
const requiredTemplates = [
  'ritual-gates-unified.json',
  'urgent-event-ingestion.json',
  'promotion-review-governance.json',
  'restore-authorization-governance.json',
];
const tenantUuid = '00000000-0000-0000-0000-000000000001';
const tenantExemptFiles = new Set(['manifest.json', 'daily-chairman-briefing.json']);

function fail(message) {
  console.error(`Template validation failed: ${message}`);
  process.exit(1);
}

if (!fs.existsSync(manifestPath)) {
  fail('manifest.json is missing');
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
if (manifest?.active_tenant?.tenant_uuid !== tenantUuid) {
  fail('manifest active tenant UUID mismatch');
}

for (const requiredFile of requiredTemplates) {
  const fullPath = path.join(templateDir, requiredFile);
  if (!fs.existsSync(fullPath)) {
    fail(`required template missing: ${requiredFile}`);
  }
}

const manifestEntries = manifest?.templates;
if (!Array.isArray(manifestEntries) || manifestEntries.length === 0) {
  fail('manifest templates array is missing or empty');
}

const manifestFiles = new Set();
for (const entry of manifestEntries) {
  if (!entry?.file || typeof entry.file !== 'string') {
    fail('manifest entry missing file');
  }
  if (manifestFiles.has(entry.file)) {
    fail(`duplicate manifest file entry: ${entry.file}`);
  }
  manifestFiles.add(entry.file);

  const fullPath = path.join(templateDir, entry.file);
  if (!fs.existsSync(fullPath)) {
    fail(`manifest references missing template: ${entry.file}`);
  }
}

const topLevelJson = fs
  .readdirSync(templateDir)
  .filter((name) => name.endsWith('.json'));

for (const file of topLevelJson) {
  if (file === 'manifest.json') continue;
  if (!manifestFiles.has(file)) {
    fail(`template file not listed in manifest: ${file}`);
  }
}

for (const file of topLevelJson) {
  if (tenantExemptFiles.has(file)) continue;
  const content = fs.readFileSync(path.join(templateDir, file), 'utf8');
  if (!content.includes(tenantUuid)) {
    fail(`template missing canonical tenant UUID: ${file}`);
  }
}

console.log(
  `Template validation passed (${manifestEntries.length} manifest entries, ${topLevelJson.length} JSON files)`,
);
