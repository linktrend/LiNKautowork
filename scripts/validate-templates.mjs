import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const templateDir = path.join(root, 'automations', 'templates');
const manifestPath = path.join(templateDir, 'manifest.json');
// heartbeat-triage.json, security-exception-response.json and
// hot-cold-migration.json were archived on 2026-07-15 (see
// automations/templates/archive/README.md): they referenced undefined Supabase
// RPCs (linkautowork_health / _open_incident / _find_inactive_files /
// _persist_pointer / _delete_file) with no current Program need. They are no
// longer required live templates.
const requiredTemplates = [
  'ritual-gates-unified.json',
  'urgent-event-ingestion.json',
  'promotion-review-governance.json',
  'restore-authorization-governance.json',
];
const wave4RequiredTemplates = [
  'linksites-artifact_write_local.json',
  'linksites-supabase_mirror_upsert.json',
  'linksites-payload_sync_local.json',
  'linksites-preview_readiness_check.json',
  'linksites-crm_ready_to_contact_mark.json',
  'linksuitegen-discovery_collect.json',
  'linksuitegen-ranking_persist.json',
  'linksuitegen-factory_generate.json',
  'linksuitegen-factory_validate.json',
  'linksuitegen-factory_export.json',
  'linksuitegen-admin_handoff.json',
  'linksuitegen-orchestrator_cycle.json',
  'linksuitegen-crm_step.json',
  'linksuitegen-odoo_lead_create.json',
  'linkdeveloper-run_validation.json',
  'linkdeveloper-status_sync.json',
  'linkdeveloper-starter_generation.json',
  'linkdeveloper-notification.json',
  'linkdeveloper-report_generation.json',
  'linkdeveloper-run_task.json',
  'linkdeveloper-deploy_scaffold.json',
  'linkdeveloper-product_run_bootstrap.json',
  'linkdeveloper-issue_dispatch.json',
  'linkdeveloper-validation_record.json',
  'linkdeveloper-artifact_write.json',
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

for (const requiredFile of [...requiredTemplates, ...wave4RequiredTemplates]) {
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
    fail(`manifest references missing file: ${entry.file}`);
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

  if (!tenantExemptFiles.has(file)) {
    if (!raw.includes(tenantUuid)) {
      fail(`canonical tenant UUID not found in ${file}`);
    }
  }

  if (file !== 'manifest.json' && !manifestFiles.has(file)) {
    fail(`template file not listed in manifest.json: ${file}`);
  }
}

for (const waveFile of wave4RequiredTemplates) {
  if (!manifestFiles.has(waveFile)) {
    fail(`wave 4 template missing from manifest: ${waveFile}`);
  }
}

console.log(`Template validation passed for ${files.length} JSON files (${manifestEntries.length} manifest entries).`);
