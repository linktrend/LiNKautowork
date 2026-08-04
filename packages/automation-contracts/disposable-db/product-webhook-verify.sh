#!/usr/bin/env bash
set -euo pipefail

compose_file="$1"
project_name="$2"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rest_port="$(docker compose -f "$compose_file" -p "$project_name" port postgrest 3000 2>/dev/null | sed 's/.*://')"
wait_for_postgrest_host() {
  for _ in $(seq 1 30); do
    if curl -fsS --connect-timeout 2 --max-time 5 "http://127.0.0.1:${rest_port}/" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo 'PostgREST did not become ready for Product API webhook verification' >&2
  return 1
}

[[ -n "$rest_port" ]] || { echo 'PostgREST has no published host port for Product API webhook verification' >&2; exit 1; }
wait_for_postgrest_host

DURABLE_POSTGREST_URL="http://127.0.0.1:${rest_port}" npx tsx "$script_dir/product-webhook-verify.ts"
