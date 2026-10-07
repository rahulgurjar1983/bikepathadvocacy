#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
tag="${1:?usage: release-report.sh <tag>}"
region=regions/au-nsw-bayside.yaml
if ! command -v gh >/dev/null 2>&1; then
  echo "release-report: gh is required" >&2
  exit 2
fi
read -r -a bikeplan <<<"${BIKEPLAN:-uv run --frozen bikeplan}"
id="$(sed -n 's/^id: *//p' "$region")"
date="$(sed -n 's/^ *osm_date: *"\([0-9-]*\)T.*/\1/p' "$region")"
manifest="snapshots/$id/$date/manifest.json"
if [ ! -f "$manifest" ]; then
  echo "release-report: no snapshot manifest at $manifest" >&2
  exit 2
fi
"${bikeplan[@]}" snapshot pull "$manifest"
out="$(mktemp -d)"
"${bikeplan[@]}" report "$region" --snapshot "data/cache/$id/$date" --out "$out"
(cd "$out" && sha256sum --check --strict SHA256SUMS)
files=("$out/SHA256SUMS")
while read -r _ name; do
  files+=("$out/$name")
done <"$out/SHA256SUMS"
if ! gh release view "$tag" >/dev/null 2>&1; then
  gh release create "$tag" --title "$tag" --notes "Bike path report built from main"
fi
gh release upload "$tag" "${files[@]}" --clobber
echo "release-report: uploaded ${#files[@]} files to $tag"
