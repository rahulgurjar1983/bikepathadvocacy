#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
id="${1:?usage: snapshot-set.sh <region-id>}"
for tool in gh uv python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "snapshot-set: $tool is required" >&2
    exit 2
  fi
done
if [ ! -x /usr/bin/time ]; then
  echo "snapshot-set: /usr/bin/time is required" >&2
  exit 2
fi
date="$(sed -n 's/^ *osm_date: *"\([0-9-]*\)T.*/\1/p' "regions/$id.yaml")"
out="data/cache/$id/$date"
stamp="$(mktemp)"
trap 'rm -f "$stamp"' EXIT
/usr/bin/time -f "%e %M" -o "$stamp" uv run --frozen bikeplan snapshot fetch "regions/$id.yaml" --out "$out"
uv run --frozen bikeplan snapshot verify "$out"
uv run --frozen bikeplan snapshot publish "$out"
read -r seconds kilobytes <"$stamp"
uv run --frozen python scripts/record_run.py "$id" "$seconds" "$kilobytes"
