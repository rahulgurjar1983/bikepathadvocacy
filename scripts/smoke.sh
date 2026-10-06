#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v docker >/dev/null 2>&1; then
  echo "smoke: docker is required" >&2
  exit 2
fi
docker build --quiet --tag bikeplan:smoke .
docker run --rm bikeplan:smoke --version
