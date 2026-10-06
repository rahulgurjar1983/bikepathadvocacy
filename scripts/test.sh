#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v uv >/dev/null 2>&1; then
  echo "test: uv is required" >&2
  exit 2
fi
scripts/install-gitleaks.sh >/dev/null
exec uv run --frozen pytest --cov --cov-report=term-missing:skip-covered --cov-fail-under=80 "$@"
