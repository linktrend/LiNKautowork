#!/usr/bin/env bash
set -euo pipefail

# This is deliberately a release-window command, not an automatic deployment
# hook.  It imports only packages that are already certified in source, and
# activation is a separately guarded, explicit operation.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

environment=""
package_selector=""
dry_run=false
activate=false

usage() {
  cat <<'USAGE'
Usage: ops/publish-certified-packages.sh --environment <stage|prod> [--package <automation-id@version>] [--dry-run] [--activate]

Default mode is a fail-closed preflight: it validates package/catalogue state
and prints the exact certified packages that would be imported. It never makes
a network request. --activate is rejected unless an approved target and a
release-window authorisation are supplied through the runtime environment.
USAGE
}

while (($#)); do
  case "$1" in
    --environment) environment="${2:-}"; shift 2 ;;
    --package) package_selector="${2:-}"; shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    --activate) activate=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
done

if [[ "$environment" != "stage" && "$environment" != "prod" ]]; then
  echo "--environment must be exactly stage or prod" >&2
  exit 64
fi
if [[ "$activate" == true && "$dry_run" == true ]]; then
  echo "--activate and --dry-run cannot be combined" >&2
  exit 64
fi

npm run validate:automations >/dev/null
npm run catalog:check >/dev/null

certified_packages() {
  LINKAUTOWORK_PACKAGE_SELECTOR="$package_selector" node --input-type=module <<'NODE'
import fs from 'node:fs';
import path from 'node:path';
const root = process.cwd();
const selected = process.env.LINKAUTOWORK_PACKAGE_SELECTOR ?? '';
for (const entry of fs.readdirSync(path.join(root, 'automations/packages'), { withFileTypes: true })) {
  if (!entry.isDirectory() || entry.name.startsWith('_')) continue;
  const file = path.join(root, 'automations/packages', entry.name, 'automation.json');
  if (!fs.existsSync(file)) continue;
  const manifest = JSON.parse(fs.readFileSync(file, 'utf8'));
  const id = `${manifest.automation_id}@${manifest.release.version}`;
  if (manifest.release.lifecycle === 'certified' && (!selected || selected === id)) {
    console.log(`${id}\t${path.relative(root, path.join(path.dirname(file), manifest.runtime.workflow_ref))}`);
  }
}
NODE
}

packages=()
while IFS= read -r package; do
  [[ -z "$package" ]] || packages+=("$package")
done < <(certified_packages)

if [[ -n "$package_selector" && ${#packages[@]} -eq 0 ]]; then
  echo "No certified package matches --package ${package_selector}" >&2
  exit 65
fi

if [[ "$dry_run" == true || "$activate" == false ]]; then
  printf 'Certified-package preflight passed for %s. No n8n request was made.\n' "$environment"
  if ((${#packages[@]})); then printf '%s\n' "${packages[@]}"; else echo 'No certified packages are available to import.'; fi
  echo 'To import into an approved target, rerun with --activate inside an authorised release window.'
  exit 0
fi

: "${LINKAUTOWORK_APPROVED_TARGET:?approved target identifier required}"
: "${LINKAUTOWORK_RELEASE_AUTHORIZATION:?release-window authorisation reference required}"
: "${N8N_BASE_URL:?N8N_BASE_URL required from the generated runtime environment}"
: "${N8N_API_KEY:?N8N_API_KEY required from the generated runtime environment}"
if [[ "$LINKAUTOWORK_APPROVED_TARGET" != "$environment" && "$LINKAUTOWORK_APPROVED_TARGET" != "${environment}:"* ]]; then
  echo "Approved target must be ${environment} or begin ${environment}:" >&2
  exit 65
fi
if ((${#packages[@]} == 0)); then
  echo 'No certified packages are available to activate.' >&2
  exit 65
fi

for entry in "${packages[@]}"; do
  package_id="${entry%%$'\t'*}"; workflow_rel="${entry#*$'\t'}"; workflow="$ROOT_DIR/$workflow_rel"
  [[ -f "$workflow" ]] || { echo "Certified workflow is absent: $workflow_rel" >&2; exit 66; }
  echo "Importing certified package ${package_id} into approved ${LINKAUTOWORK_APPROVED_TARGET}"
  response="$(curl --fail-with-body --silent --show-error -X POST "${N8N_BASE_URL%/}/api/v1/workflows" -H "x-n8n-api-key: $N8N_API_KEY" -H 'content-type: application/json' --data-binary "@$workflow")"
  workflow_id="$(node -e 'const data=JSON.parse(process.argv[1]); if (!data.id) process.exit(1); process.stdout.write(String(data.id))' "$response")" || { echo "n8n import returned no workflow id for ${package_id}" >&2; exit 67; }
  # Workflows are imported inactive first; this guarded patch is the sole
  # activation point and is auditable through the release authorisation value.
  curl --fail-with-body --silent --show-error -X PATCH "${N8N_BASE_URL%/}/api/v1/workflows/${workflow_id}" -H "x-n8n-api-key: $N8N_API_KEY" -H 'content-type: application/json' --data '{"active":true}' >/dev/null
  echo "Activated ${package_id} as n8n workflow ${workflow_id}"
done
