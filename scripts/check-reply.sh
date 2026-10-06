#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
source="${1:--}"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
if [ "$source" = "-" ]; then
  cat > "$tmp"
else
  cat -- "$source" > "$tmp"
fi
cd "$root"
uv run --frozen python -m gates.readability --reply "$tmp"
