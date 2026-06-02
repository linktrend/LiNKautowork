#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 <dev|prod> [--build] [--runtime-dir <path>]

Deploys stack with GSM-resolved runtime env (secrets written to runtime dir, not repo).
USAGE
}

if [[ $# -lt 1 || $# -gt 4 ]]; then
  usage
  exit 1
fi

ENVIRONMENT="$1"
shift
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be dev or prod"
  exit 1
fi

BUILD_FLAG=""
RUNTIME_DIR="${LINKAUTOWORK_RUNTIME_DIR:-/opt/linktrend/runtime/linkautowork}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)
      BUILD_FLAG="--build"
      shift
      ;;
    --runtime-dir)
      RUNTIME_DIR="$2"
      shift 2
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/docker-compose.yml"
BASE_ENV_FILE="$ROOT_DIR/deploy/${ENVIRONMENT}/.env"
RUNTIME_ENV_FILE="$RUNTIME_DIR/${ENVIRONMENT}.env.runtime"

if [[ ! -f "$BASE_ENV_FILE" || ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing deploy files for environment: $ENVIRONMENT"
  exit 1
fi

"$SCRIPT_DIR/render-runtime-env-from-gsm.sh" "$ENVIRONMENT" --output "$RUNTIME_ENV_FILE"

if [[ "$ENVIRONMENT" == "prod" ]]; then
  python3 - "$RUNTIME_ENV_FILE" <<'PY'
import pathlib
import sys

runtime_env = pathlib.Path(sys.argv[1])
lines = runtime_env.read_text().splitlines()
values = {}
for line in lines:
    if not line or line.lstrip().startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key] = value

host = values.get("SUPABASE_DB_HOST", "")
pooler = values.get("SUPABASE_DB_SESSION_POOLER_HOST", "")
ipv4_host = values.get("SUPABASE_DB_HOST_IPV4", "")

replacement = ""
if pooler:
    replacement = pooler
elif ipv4_host:
    replacement = ipv4_host
elif host.endswith(".supabase.com") and ".pooler." not in host:
    replacement = host.replace(".", "-ipv4.", 1)

if replacement:
    updated = []
    replaced = False
    for line in lines:
        if line.startswith("SUPABASE_DB_HOST="):
            updated.append(f"SUPABASE_DB_HOST={replacement}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(f"SUPABASE_DB_HOST={replacement}")
    runtime_env.write_text("\n".join(updated) + "\n")
PY
fi

if [[ "$ENVIRONMENT" == "prod" ]]; then
  traefik_n8n_host="$(grep '^TRAEFIK_N8N_HOST=' "$BASE_ENV_FILE" 2>/dev/null | cut -d= -f2- || true)"
  if [[ -n "$traefik_n8n_host" ]]; then
    sed -i "s#^N8N_HOST=.*#N8N_HOST=${traefik_n8n_host}#" "$RUNTIME_ENV_FILE"
    sed -i "s#^N8N_PORT=.*#N8N_PORT=5678#" "$RUNTIME_ENV_FILE"
    sed -i "s#^N8N_PROTOCOL=.*#N8N_PROTOCOL=https#" "$RUNTIME_ENV_FILE"
    sed -i "s#^N8N_SECURE_COOKIE=.*#N8N_SECURE_COOKIE=true#" "$RUNTIME_ENV_FILE"
    sed -i "s#^N8N_EDITOR_BASE_URL=.*#N8N_EDITOR_BASE_URL=https://${traefik_n8n_host}#" "$RUNTIME_ENV_FILE"
    sed -i "s#^WEBHOOK_URL=.*#WEBHOOK_URL=https://${traefik_n8n_host}/#" "$RUNTIME_ENV_FILE"
  elif [[ -n "${N8N_TAILSCALE_IP:-}" ]]; then
    sed -i "s#^N8N_HOST=.*#N8N_HOST=${N8N_TAILSCALE_IP}#" "$RUNTIME_ENV_FILE"
    sed -i "s#^N8N_PROTOCOL=.*#N8N_PROTOCOL=http#" "$RUNTIME_ENV_FILE"
    sed -i "s#^N8N_EDITOR_BASE_URL=.*#N8N_EDITOR_BASE_URL=http://${N8N_TAILSCALE_IP}:5678#" "$RUNTIME_ENV_FILE"
    sed -i "s#^WEBHOOK_URL=.*#WEBHOOK_URL=http://${N8N_TAILSCALE_IP}:5678/#" "$RUNTIME_ENV_FILE"
  fi
fi

# Export vars required by compose substitutions without shell-sourcing values.
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
  export "$line"
done < "$RUNTIME_ENV_FILE"

docker compose --env-file "$BASE_ENV_FILE" -f "$COMPOSE_FILE" -p "$ENVIRONMENT" up -d $BUILD_FLAG
