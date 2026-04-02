#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <dev|prod> [--build]"
  exit 1
fi

ENVIRONMENT="$1"
BUILD_FLAG="${2:-}"

if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be dev or prod"
  exit 1
fi
if [[ -n "$BUILD_FLAG" && "$BUILD_FLAG" != "--build" ]]; then
  echo "Only optional flag supported is --build"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "compose-up-gsm.sh is deprecated; forwarding to deploy-stack.sh"
"$SCRIPT_DIR/deploy-stack.sh" "$ENVIRONMENT" ${BUILD_FLAG:+$BUILD_FLAG}
