import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const templateDir = path.join(root, 'automations', 'templates');
const manifestPath = path.join(templateDir, 'manifest.json');
const requiredTemplates = [
  'ritual-gates-unified.json',
  'urgent-event-ingestion.json',
  'heartbeat-triage.json',
  'security-exception-response.json',
  'promotion-review-governance.json',
  'restore-authorization-governance.json',
  'hot-cold-migration.json',
];
const tenantUuid = '00000000-0000-0000-0000-000000000001';

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

const files = fs.readdirSync(templateDir).filter((file) => file.endsWith('.json'));
const names = new Set();
for (const file of files) {
  const fullPath = path.join(templateDir, file);
  const raw = fs.readFileSync(fullPath, 'utf8');
  const parsed = JSON.parse(raw);

  if (file !== 'manifest.json') {
    if (!parsed.name || !Array.isArray(parsed.nodes) || typeof parsed.connections !== 'object') {
      fail(`invalid workflow shape in ${file}`);
    }
    if (names.has(parsed.name)) {
      fail(`duplicate workflow name: ${parsed.name}`);
    }
    names.add(parsed.name);
  }

  if (file !== 'manifest.json' && file !== 'daily-chairman-briefing.json') {
    if (!raw.includes(tenantUuid)) {
      fail(`canonical tenant UUID not found in ${file}`);
    }
  }
}

console.log(`Template validation passed for ${files.length} JSON files.`);
