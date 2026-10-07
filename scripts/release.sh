#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
tag="${1:?usage: release.sh <tag>}"
for tool in gh tar gzip sha256sum git; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "release: $tool is required" >&2
    exit 2
  fi
done
read -r -a bikeplan <<<"${BIKEPLAN:-uv run --frozen bikeplan}"
commit="$(git rev-parse HEAD)"
work="$(mktemp -d)"
if [ -n "${RELEASE_OUT:-}" ]; then
  out="$RELEASE_OUT"
  mkdir -p "$out"
  trap 'rm -rf "$work"' EXIT
else
  out="$(mktemp -d)"
  trap 'rm -rf "$out" "$work"' EXIT
fi

field() {
  sed -n "s/^$1: *//p" "$2" | head -n 1
}

snapshot_date() {
  sed -n 's/^ *osm_date: *"\([0-9-]*\)T.*/\1/p' "$1"
}

changed=1
if git rev-parse --verify -q HEAD^ >/dev/null; then
  if [ -z "$(git diff --name-only HEAD^ HEAD -- src regions profiles snapshots routes pyproject.toml uv.lock VOICE.md specs/13-public-report.md)" ]; then
    changed=0
  fi
fi

last=""
if [ "$changed" = 0 ]; then
  parent="$(git rev-parse HEAD^)"
  while read -r tag; do
    [ -n "$tag" ] || continue
    gh release download "$tag" --pattern index.html --dir "$work/index-$tag"
    if grep -q "$parent" "$work/index-$tag/index.html"; then
      last="$tag"
      break
    fi
  done < <(gh release list --limit 100 --json tagName --jq '.[].tagName | select(startswith("v"))')
  if [ -n "$last" ]; then
    gh release download "$last" --dir "$work/last"
  fi
fi

rows=""
count=0

check_copied() {
  local name="$1"
  if ! grep -q "  $name\$" "$work/last/SHA256SUMS"; then
    return 1
  fi
  (cd "$work/last" && grep "  $name\$" SHA256SUMS | sha256sum --check --strict -)
}

publish() {
  local kind="$1" id="$2" region="$3" snapshot="$4" folder="$5" html="$6" archive="$7"
  cp "$folder/report.html" "$out/$html"
  tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$folder" . | gzip -n >"$out/$archive"
  rows+="<tr><td>$kind</td><td><a href=\"$html\">$id</a></td><td>$region</td><td>$snapshot</td><td>$commit</td><td>built</td></tr>"$'\n'
  count=$((count + 1))
}

published() {
  [ -f "snapshots/$(field id "$1")/$(snapshot_date "$1")/manifest.json" ]
}

pull() {
  local region="$1"
  local rid date manifest
  rid="$(field id "$region")"
  date="$(snapshot_date "$region")"
  manifest="snapshots/$rid/$date/manifest.json"
  if [ ! -f "data/cache/$rid/$date/manifest.json" ]; then
    "${bikeplan[@]}" snapshot pull "$manifest"
  fi
}

build() {
  local kind="$1" id="$2" region="$3" html="$4" archive="$5"
  shift 5
  local rid date source
  rid="$(field id "$region")"
  date="$(snapshot_date "$region")"
  if [ -n "$last" ] && [ -f "$work/last/$html" ] && [ -f "$work/last/$archive" ]; then
    check_copied "$html"
    check_copied "$archive"
    cp "$work/last/$html" "$work/last/$archive" "$out/"
    rows+="<tr><td>$kind</td><td><a href=\"$html\">$id</a></td><td>$rid</td><td>$date</td><td>$commit</td><td>copied from release $last</td></tr>"$'\n'
    count=$((count + 1))
    return
  fi
  local folder="$work/$kind-$id"
  "${bikeplan[@]}" "$kind" "$@" --snapshot "data/cache/$rid/$date" --out "$folder"
  (cd "$folder" && sha256sum --check --strict SHA256SUMS)
  publish "$kind" "$id" "$rid" "$date" "$folder" "$html" "$archive"
}

for region in regions/*.yaml; do
  published "$region" || continue
  pull "$region"
  id="$(field id "$region")"
  build report "$id" "$region" "$id-report.html" "$id.tar.gz" "$region"
done

for review in routes/*/review.yaml; do
  [ -f "$review" ] || continue
  grep -q '^public: *true *$' "$review" || continue
  folder="$(dirname "$review")"
  id="$(basename "$folder")"
  region="$folder/$(field region "$review")"
  if ! published "$region"; then
    echo "release: no snapshot manifest for review $id" >&2
    exit 2
  fi
  pull "$region"
  build review "$id" "$region" "$id-review.html" "$id.tar.gz" "$folder/$(field route "$review")" --claims "$folder/$(field claims "$review")" --region "$region"
done

if [ "$count" = 0 ]; then
  echo "release: no report to build" >&2
  exit 2
fi

tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - artifacts | gzip -n >"$out/artifacts.tar.gz"
{
  echo "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Bike path reports</title></head><body><h1>Bike path reports</h1><table><tr><th>Kind</th><th>Report</th><th>Region</th><th>Snapshot</th><th>Commit</th><th>Source</th></tr>"
  printf '%s' "$rows"
  echo "</table><p><a href=\"artifacts.tar.gz\">artifacts.tar.gz</a></p></body></html>"
} >"$out/index.html"
(cd "$out" && sha256sum -- $(ls | grep -vx SHA256SUMS) >SHA256SUMS && sha256sum --check --strict SHA256SUMS)
files=("$out"/*)
if ! gh release view "$tag" >/dev/null 2>&1; then
  gh release create "$tag" --title "$tag" --notes "Bike path reports built from main"
fi
gh release upload "$tag" "${files[@]}" --clobber
echo "release: uploaded ${#files[@]} files to $tag"
