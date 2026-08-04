#!/usr/bin/env bash
set -euo pipefail

# Reconciles only LiNKautowork's labelled disposable evaluator, contracts, and
# browser-proof resources. It intentionally never invokes Docker prune.
labels=(
  'com.linktrend.linkautowork.disposable-eval=true'
  'com.linktrend.linkautowork.disposable-contracts=true'
  'com.linktrend.linkautowork.disposable-browser=true'
)
legacy_volumes=(linkautowork-wp06-probe linkautowork-wp06-probe2)
legacy_networks=(linkautowork-contracts-db-64479_default linkautowork-contracts-db-69480_default)

missing_resource() { [[ "$1" == *'No such'* || "$1" == *'not found'* ]]; }
remove_if_unattached_volume() {
  local volume="$1" attached output
  docker volume inspect "$volume" >/dev/null 2>&1 || return 0
  attached="$(docker ps -aq --filter "volume=${volume}")"
  if [[ -n "$attached" ]]; then echo "Refusing in-use disposable volume: $volume" >&2; return 1; fi
  if ! output="$(docker volume rm "$volume" 2>&1)"; then missing_resource "$output" || { printf '%s\n' "$output" >&2; return 1; }; fi
  echo "Removed disposable volume: $volume"
}
remove_if_empty_network() {
  local network="$1" attached output
  docker network inspect "$network" >/dev/null 2>&1 || return 0
  attached="$(docker network inspect "$network" --format '{{len .Containers}}')"
  if [[ "$attached" != 0 ]]; then echo "Refusing non-empty disposable network: $network" >&2; return 1; fi
  if ! output="$(docker network rm "$network" 2>&1)"; then missing_resource "$output" || { printf '%s\n' "$output" >&2; return 1; }; fi
  echo "Removed disposable network: $network"
}

for label in "${labels[@]}"; do
  while IFS= read -r container; do
    [[ -z "$container" ]] || docker rm -f "$container" >/dev/null
  done < <(docker ps -aq --filter "label=${label}")
  while IFS= read -r volume; do
    [[ -z "$volume" ]] || remove_if_unattached_volume "$volume"
  done < <(docker volume ls -q --filter "label=${label}")
  while IFS= read -r network; do
    [[ -z "$network" ]] || remove_if_empty_network "$network"
  done < <(docker network ls -q --filter "label=${label}")
done

# One-time crash recovery is deliberately constrained to the exact legacy
# names observed before the common labels existed. New arbitrary resources are
# never selected by name or prefix.
for volume in "${legacy_volumes[@]}"; do remove_if_unattached_volume "$volume"; done
for network in "${legacy_networks[@]}"; do remove_if_empty_network "$network"; done
echo 'Reconciled only labelled LiNKautowork disposable resources and verified legacy crash leftovers.'
